"""Reproducible benchmarks for SentinelLake (single machine, Spark local mode).

  python -m benchmarks.run_benchmarks --landing data/landing --lake data/lake --out results

Measures:
  1. storage formats  - size of the same 2.4M records as JSON, gzip JSON, Parquet, ORC
  2. format speed     - one analytical query on JSON vs Parquet
  3. partitioning     - one hour with partition pruning vs a full scan
  4. combiner         - MapReduce shuffle volume and time with and without a combiner
  5. streaming        - end-to-end replay throughput (optional, --stream)

All numbers depend on the machine; results.json records its CPU count and RAM so
they can be read in context. Run on the Docker cluster for distributed numbers.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)


def ram_gb() -> float | None:
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except (AttributeError, ValueError, OSError):   # Windows has no sysconf
        return None

from pyspark.sql import SparkSession, functions as F  # noqa: E402

from mapreduce import local_runner  # noqa: E402
from sentinellake.streaming.transforms import LOG_SCHEMA  # noqa: E402


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.name.startswith((".", "_")))


def timed(fn, runs=3):
    out = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    return round(statistics.median(out), 2)


def query(df):
    return (df.groupBy("service", "endpoint")
            .agg(F.count(F.lit(1)).alias("n"),
                 F.avg((F.col("status") >= 500).cast("int")).alias("err"),
                 F.percentile_approx("latency_ms", 0.95).alias("p95"))
            .collect())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--landing", default="data/landing")
    p.add_argument("--lake", default="data/lake")
    p.add_argument("--out", default="results")
    p.add_argument("--stream", action="store_true", help="also time a full streaming replay")
    a = p.parse_args()
    landing, lake, out = Path(a.landing), Path(a.lake), Path(a.out)
    work = out / "_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    res: dict = {"machine": {"cpus": os.cpu_count(), "python": platform.python_version(),
                             "ram_gb": ram_gb()}}

    if a.stream:
        shutil.rmtree(lake, ignore_errors=True)
        t = time.perf_counter()
        subprocess.run([sys.executable, "-m", "sentinellake.streaming.job", "--source", "files",
                        "--input", str(landing), "--lake", str(lake), "--serving", "local", "--once",
                        "--files-per-trigger", "6"], check=True, capture_output=True)
        secs = time.perf_counter() - t
        events = sum(1 for f in landing.glob("*.jsonl") for _ in f.open())
        res["streaming"] = {"events": events, "seconds": round(secs, 1),
                            "events_per_sec": round(events / secs),
                            "note": "file source, 4 concurrent queries (raw, curated, quarantine, serving)"}
        print("streaming", res["streaming"])

    spark = (SparkSession.builder.master(f"local[{os.cpu_count()}]").appName("sentinellake-bench")
             .config("spark.sql.session.timeZone", "UTC").config("spark.driver.memory", "3g")
             .config("spark.sql.shuffle.partitions", "8").config("spark.ui.enabled", "false")
             .config("spark.driver.host", "127.0.0.1").config("spark.driver.bindAddress", "127.0.0.1").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    # ---- 1. storage formats -------------------------------------------------
    curated_path = lake / "curated" / "api_logs"
    curated = spark.read.parquet(str(curated_path))
    rows = curated.count()
    json_bytes = sum(f.stat().st_size for f in landing.glob("api-2*.jsonl"))
    gz_bytes = 0
    for f in landing.glob("api-2*.jsonl"):
        with open(f, "rb") as src:
            gz_bytes += len(gzip.compress(src.read(), compresslevel=6))
    sizes = {"JSON (raw)": json_bytes, "JSON + gzip": gz_bytes,
             "Parquet + snappy": dir_size(curated_path)}
    for codec in ("gzip", "zstd"):
        path = work / f"parquet_{codec}"
        curated.write.option("compression", codec).parquet(str(path))
        sizes[f"Parquet + {codec}"] = dir_size(path)
    curated.write.option("compression", "zlib").orc(str(work / "orc_zlib"))
    sizes["ORC + zlib"] = dir_size(work / "orc_zlib")
    res["storage"] = {"rows": rows, "bytes": sizes,
                      "mb": {k: round(v / 2**20, 1) for k, v in sizes.items()},
                      "ratio_vs_json": {k: round(json_bytes / v, 1) for k, v in sizes.items()}}
    print("storage", res["storage"]["mb"])

    # ---- 2. JSON vs Parquet for the same query --------------------------------
    js = (spark.read.schema(LOG_SCHEMA).json(str(landing / "api-2*.jsonl"))
          .withColumn("endpoint", F.concat_ws(" ", "method", "route")))
    pq = spark.read.parquet(str(curated_path))
    query(js), query(pq)                                   # warm-up (JIT, file listing)
    res["query"] = {"description": "count, 5xx rate and p95 per endpoint over all rows",
                    "json_seconds": timed(lambda: query(js)),
                    "parquet_seconds": timed(lambda: query(pq))}
    res["query"]["speedup"] = round(res["query"]["json_seconds"] / res["query"]["parquet_seconds"], 1)
    print("query", res["query"])

    # ---- 3. partition pruning ----------------------------------------------------
    hours = sorted(r.hr for r in pq.select("hr").distinct().collect())
    one_hour = hours[len(hours) // 2]
    full = lambda: pq.groupBy("status_class").count().collect()                        # noqa: E731
    pruned = lambda: pq.where(f"dt = '2026-10-12' AND hr = {one_hour}").groupBy("status_class").count().collect()  # noqa: E731
    full(), pruned()
    plan = pq.where(f"dt = '2026-10-12' AND hr = {one_hour}")._jdf.queryExecution().executedPlan().toString()
    res["partitioning"] = {"partitions_total": len(hours), "partitions_read": 1,
                           "full_scan_seconds": timed(full), "pruned_seconds": timed(pruned),
                           "plan_shows_partition_filter": "PartitionFilters: [isnotnull(dt" in plan}
    res["partitioning"]["speedup"] = round(res["partitioning"]["full_scan_seconds"]
                                           / res["partitioning"]["pruned_seconds"], 1)
    print("partitioning", res["partitioning"])
    spark.stop()

    # ---- 4. MapReduce combiner -----------------------------------------------------
    files = sorted(landing.glob("*.jsonl"))
    with_c = local_runner.hotspots(files, work / "mr_with", 3, use_combiner=True)
    without = local_runner.hotspots(files, work / "mr_without", 3, use_combiner=False)
    res["mapreduce"] = {"map_tasks": with_c["map_tasks"], "map_output_records": with_c["map_output_records"],
                        "shuffle_bytes_with_combiner": with_c["shuffle_bytes"],
                        "shuffle_bytes_without_combiner": without["shuffle_bytes"],
                        "shuffle_reduction_pct": round(100 * (1 - with_c["shuffle_bytes"] / without["shuffle_bytes"]), 3),
                        "seconds_with_combiner": with_c["seconds"],
                        "seconds_without_combiner": without["seconds"],
                        "note": "local runner (single machine) - shows the data-flow effect, not cluster speed"}
    print("mapreduce", res["mapreduce"])

    shutil.rmtree(work, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmarks.json").write_text(json.dumps(res, indent=2))
    print(f"wrote {out / 'benchmarks.json'}")


if __name__ == "__main__":
    main()
