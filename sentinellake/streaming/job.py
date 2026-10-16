"""SentinelLake streaming job (Spark Structured Streaming).

One source, three outputs:

  raw zone      JSON text exactly as received, partitioned by date   -> MapReduce, Hive SerDe
  curated zone  typed Parquet, partitioned by date/hour              -> Hive, Spark SQL
  serving       1-minute endpoint metrics + incidents                -> Cassandra, MongoDB

Run with Kafka (Docker stack):
  spark-submit ... -m sentinellake.streaming.job --source kafka \
      --lake hdfs://namenode:8020/sentinellake --serving live

Run locally on files:
  python -m sentinellake.streaming.job --source files --input data/landing \
      --lake data/lake --serving local --once
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):        # not available on Windows; timestamps are handled in UTC anyway
    time.tzset()
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)

from pyspark.sql import DataFrame, SparkSession  # noqa: E402

from ..detection import IncidentManager  # noqa: E402
from . import transforms as T  # noqa: E402
from .sinks import CassandraMongoSink, LocalSink, ServingSink  # noqa: E402

log = logging.getLogger("sentinellake.stream")


def build_spark(app: str = "sentinellake-stream", local: bool = False) -> SparkSession:
    b = (SparkSession.builder.appName(app)
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.sql.shuffle.partitions", os.getenv("SHUFFLE_PARTITIONS", "4"))
         .config("spark.sql.streaming.metricsEnabled", "true"))
    if local:
        # laptop mode: bind to loopback, which avoids hostname/VPN problems on Windows
        b = (b.master(os.getenv("SPARK_MASTER", "local[*]"))
             .config("spark.driver.host", "127.0.0.1").config("spark.driver.bindAddress", "127.0.0.1"))
    return b.getOrCreate()


def read_source(spark: SparkSession, args: argparse.Namespace) -> DataFrame:
    if args.source == "kafka":
        return (spark.readStream.format("kafka")
                .option("kafka.bootstrap.servers", args.bootstrap)
                .option("subscribe", args.topic)
                .option("startingOffsets", "earliest")
                .option("maxOffsetsPerTrigger", args.max_per_trigger)
                .option("failOnDataLoss", "false")
                .load()
                .selectExpr("CAST(value AS STRING) AS json"))
    return (spark.readStream.option("maxFilesPerTrigger", args.files_per_trigger)
            .text(args.input).withColumnRenamed("value", "json"))


class ServingWriter:
    """foreachBatch handler: finalised windows -> metrics store + incident detector."""

    def __init__(self, sink: ServingSink):
        self.sink = sink
        self.detector = IncidentManager()
        self.windows_seen = 0

    def __call__(self, batch: DataFrame, batch_id: int) -> None:
        rows = [r.asDict() for r in batch.orderBy("window_start", "service", "endpoint").collect()]
        if not rows:
            return
        self.sink.write_metrics(rows)
        events = [e for r in rows for e in self.detector.process(r)]
        self.sink.write_incidents(events)
        self.windows_seen += len(rows)
        for action, inc in events:
            if action != "updated":
                log.warning("incident %s: %s %s %s - %s", action, inc.type, inc.service,
                            inc.endpoint, inc.reason)
        log.info("batch %d: %d windows (%d total), %d incident events",
                 batch_id, len(rows), self.windows_seen, len(events))


def start(args: argparse.Namespace):
    spark = build_spark(local=args.source == "files")
    spark.sparkContext.setLogLevel("WARN")
    lake, ckpt = args.lake.rstrip("/"), (args.checkpoint or f"{args.lake.rstrip('/')}/_checkpoints")

    parsed = T.parse_logs(read_source(spark, args))
    trigger = {"availableNow": True} if args.once else {"processingTime": args.trigger}

    def sink_query(df: DataFrame, name: str, fmt: str, path: str, partition_by: list[str]):
        w = (df.writeStream.queryName(name).format(fmt).outputMode("append")
             .option("path", path).option("checkpointLocation", f"{ckpt}/{name}")
             .trigger(**trigger))
        return w.partitionBy(*partition_by).start() if partition_by else w.start()

    queries = [
        sink_query(parsed.filter("is_valid").select("json", "dt"), "raw_zone", "text",
                   f"{lake}/raw/api_logs", ["dt"]),
        sink_query(T.curated(parsed), "curated_zone", "parquet",
                   f"{lake}/curated/api_logs", ["dt", "hr"]),
        sink_query(T.quarantine(parsed), "quarantine", "json", f"{lake}/quarantine", []),
    ]

    sink: ServingSink = CassandraMongoSink() if args.serving == "live" else LocalSink(f"{lake}/serving")
    metrics = T.endpoint_minute_metrics(T.curated(parsed))
    queries.append(metrics.writeStream.queryName("serving").outputMode("append")
                   .option("checkpointLocation", f"{ckpt}/serving")
                   .foreachBatch(ServingWriter(sink)).trigger(**trigger).start())
    return spark, queries


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", choices=["kafka", "files"], default="kafka")
    p.add_argument("--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"))
    p.add_argument("--topic", default="api-logs")
    p.add_argument("--input", default="data/landing", help="directory of JSONL files (files source)")
    p.add_argument("--lake", default="data/lake", help="lake root: local path or hdfs://...")
    p.add_argument("--checkpoint", default=None)
    p.add_argument("--serving", choices=["live", "local"], default="local")
    p.add_argument("--trigger", default="10 seconds")
    p.add_argument("--max-per-trigger", type=int, default=50_000)
    p.add_argument("--files-per-trigger", type=int, default=3)
    p.add_argument("--once", action="store_true", help="process what is available, then stop")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    spark, queries = start(args)
    if args.once:
        for q in queries:
            q.awaitTermination()
    else:
        spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
