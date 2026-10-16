"""Pure DataFrame transformations used by the streaming job.

Kept separate from I/O so the same logic runs on a stream in production and on
a static DataFrame in tests.
"""
from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (DoubleType, IntegerType, LongType, StringType,
                               StructField, StructType)

LOG_SCHEMA = StructType([
    StructField("ts", StringType()),
    StructField("trace_id", StringType()),
    StructField("service", StringType()),
    StructField("method", StringType()),
    StructField("route", StringType()),
    StructField("status", IntegerType()),
    StructField("latency_ms", DoubleType()),
    StructField("bytes", LongType()),
    StructField("region", StringType()),
    StructField("instance", StringType()),
    StructField("client_id", StringType()),
])

WINDOW = "1 minute"
WATERMARK = "2 minutes"


def parse_logs(raw: DataFrame) -> DataFrame:
    """raw: one column ``json`` (string). Adds typed columns plus ``is_valid``."""
    parsed = raw.withColumn("r", F.from_json("json", LOG_SCHEMA))
    event_time = F.to_timestamp(F.col("ts"), "yyyy-MM-dd'T'HH:mm:ss.SSSX")
    return (parsed
            .select("json", "r.*")
            .withColumn("event_time", event_time)
            .withColumn("is_valid",
                        F.col("event_time").isNotNull() & F.col("service").isNotNull()
                        & F.col("status").isNotNull() & F.col("latency_ms").isNotNull())
            .withColumn("endpoint", F.concat_ws(" ", "method", "route"))
            .withColumn("status_class", F.concat((F.col("status") / 100).cast("int"), F.lit("xx")))
            .withColumn("dt", F.date_format("event_time", "yyyy-MM-dd"))
            .withColumn("hr", F.hour("event_time")))


def curated(parsed: DataFrame) -> DataFrame:
    """Typed, validated rows for the Parquet zone (what Hive and Spark SQL query)."""
    return (parsed.filter("is_valid")
            .select("event_time", "trace_id", "service", "endpoint", "method", "route",
                    "status", "status_class", "latency_ms", "bytes", "region", "instance",
                    "client_id", "dt", "hr"))


def quarantine(parsed: DataFrame) -> DataFrame:
    """Rows that failed validation, kept as-is for debugging (dead-letter queue)."""
    return parsed.filter(~F.col("is_valid")).select("json", F.current_timestamp().alias("received_at"))


def endpoint_minute_metrics(valid: DataFrame, watermark: str | None = WATERMARK) -> DataFrame:
    """One row per (1-minute window, service, endpoint) with volume, errors and latency."""
    df = valid.withWatermark("event_time", watermark) if watermark else valid
    return (df.groupBy(F.window("event_time", WINDOW), "service", "endpoint")
            .agg(F.count(F.lit(1)).alias("requests"),
                 F.sum((F.col("status") >= 500).cast("int")).alias("errors_5xx"),
                 F.sum(((F.col("status") >= 400) & (F.col("status") < 500)).cast("int")).alias("errors_4xx"),
                 F.percentile_approx("latency_ms", F.array(F.lit(0.5), F.lit(0.95), F.lit(0.99)), 1000)
                  .alias("pct"),
                 F.avg("bytes").alias("avg_bytes"))
            # TIMESTAMP_NTZ: collected as a plain UTC datetime, whatever the laptop's time zone
            .select(F.col("window.start").cast("timestamp_ntz").alias("window_start"),
                    "service", "endpoint", "requests", "errors_5xx", "errors_4xx",
                    (F.col("errors_5xx") / F.col("requests")).alias("error_rate"),
                    F.col("pct")[0].alias("p50_ms"),
                    F.col("pct")[1].alias("p95_ms"),
                    F.col("pct")[2].alias("p99_ms"),
                    F.round("avg_bytes", 1).alias("avg_bytes")))
