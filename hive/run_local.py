"""Run the HiveQL reports on Spark SQL, over the local curated zone (no Hive server needed).

  python -m hive.run_local                     # all queries in hive/02_analytics.hql
  python -m hive.run_local --lake data/lake

Spark SQL understands HiveQL, so this shows the same results the Hive cluster gives.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)

from pyspark.sql import SparkSession  # noqa: E402

HQL = Path(__file__).parent / "02_analytics.hql"


def queries() -> list[tuple[str, str]]:
    """(title, sql) for every SELECT, with the -- Qn comment above it as the title."""
    out = []
    for block in HQL.read_text().split(";"):
        titles = re.findall(r"--\s*(Q\d+\..*)", block)
        sql = re.sub(r"--[^\n]*", "", block).strip()
        if sql.upper().startswith("SELECT"):
            out.append((titles[0] if titles else "query", sql))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lake", default="data/lake")
    a = p.parse_args()
    spark = (SparkSession.builder.master("local[*]").appName("sentinellake-hive-local")
             .config("spark.sql.session.timeZone", "UTC").config("spark.ui.enabled", "false")
             .config("spark.driver.host", "127.0.0.1").config("spark.driver.bindAddress", "127.0.0.1")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    spark.read.parquet(f"{a.lake}/curated/api_logs").createOrReplaceTempView("api_logs")
    for title, sql in queries():
        print(f"\n=== {title}")
        spark.sql(sql).show(60, truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
