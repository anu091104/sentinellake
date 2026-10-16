import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)

from sentinellake.generator import DEFAULT_SCENARIOS, TrafficModel, iter_replay  # noqa: E402

START = datetime(2026, 10, 12, 6, 50, tzinfo=timezone.utc)   # spans hours 6 and 7


@pytest.fixture(scope="session")
def sample_events():
    """20 simulated minutes at a low rate - small enough for fast tests."""
    model = TrafficModel(rpm=1500, scenarios=DEFAULT_SCENARIOS, seed=3)
    return [e for _, evs in iter_replay(model, START, 20) for e in evs]


@pytest.fixture(scope="session")
def landing_dir(tmp_path_factory, sample_events):
    d = tmp_path_factory.mktemp("landing")
    half = len(sample_events) // 2
    for i, chunk in enumerate((sample_events[:half], sample_events[half:])):
        (d / f"api-{i}.jsonl").write_text("".join(json.dumps(e) + "\n" for e in chunk))
    (d / "api-bad.jsonl").write_text('{"ts":"nope","service":"auth"}\nnot json at all\n')
    return d


@pytest.fixture(scope="session")
def spark():
    pyspark = pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    s = (SparkSession.builder.master("local[2]").appName("sentinellake-tests")
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.sql.shuffle.partitions", "2")
         .config("spark.ui.enabled", "false")
         .config("spark.driver.host", "127.0.0.1").config("spark.driver.bindAddress", "127.0.0.1")
         .getOrCreate())
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()
