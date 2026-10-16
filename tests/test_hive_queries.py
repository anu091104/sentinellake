"""Execute every query in hive/02_analytics.hql on Spark SQL's HiveQL dialect.

This doesn't replace running them on HiveServer2, but it proves the SQL is valid,
uses only functions both engines share, and returns sensible numbers.
"""
import re
from pathlib import Path

import pytest

pytest.importorskip("pyspark")

from sentinellake.streaming import transforms as T  # noqa: E402

HQL = Path(__file__).resolve().parents[1] / "hive" / "02_analytics.hql"


def queries():
    text = re.sub(r"--[^\n]*", "", HQL.read_text())
    stmts = [s.strip() for s in text.split(";") if s.strip()]
    return [s for s in stmts if s.upper().startswith("SELECT")]


@pytest.fixture(scope="module")
def api_logs(spark, landing_dir):
    raw = spark.read.text(str(landing_dir)).withColumnRenamed("value", "json")
    T.curated(T.parse_logs(raw)).createOrReplaceTempView("api_logs")
    return spark


def test_file_has_six_queries():
    assert len(queries()) == 6


@pytest.mark.parametrize("idx", range(6))
def test_query_runs(api_logs, idx):
    rows = api_logs.sql(queries()[idx]).collect()
    assert rows, f"query {idx + 1} returned nothing"


def test_slo_report_values(api_logs):
    rows = api_logs.sql(queries()[0]).collect()
    assert {r.slo for r in rows} <= {"MET", "BREACHED"}
    assert all(90 <= r.availability_pct <= 100 for r in rows)
