import json
from collections import defaultdict

import numpy as np
import pytest

pytest.importorskip("pyspark")

from sentinellake.streaming import transforms as T  # noqa: E402
from sentinellake.streaming.job import ServingWriter  # noqa: E402


@pytest.fixture(scope="module")
def raw(spark, landing_dir):
    return spark.read.text(str(landing_dir)).withColumnRenamed("value", "json")


def test_invalid_rows_go_to_quarantine(raw, sample_events):
    parsed = T.parse_logs(raw)
    assert T.curated(parsed).count() == len(sample_events)
    assert T.quarantine(parsed).count() == 2


def test_curated_has_partition_columns(raw):
    row = T.curated(T.parse_logs(raw)).first()
    assert row.dt == "2026-10-12" and row.hr == 6
    assert row.endpoint == f"{row.method} {row.route}"


def test_minute_metrics_match_numpy(raw, sample_events):
    metrics = T.endpoint_minute_metrics(T.curated(T.parse_logs(raw)), watermark=None).collect()
    groups = defaultdict(list)
    for e in sample_events:
        groups[(e["ts"][:16], e["service"], f'{e["method"]} {e["route"]}')].append(e)
    assert len(metrics) == len(groups)
    for m in metrics:
        evs = groups[(m.window_start.strftime("%Y-%m-%dT%H:%M"), m.service, m.endpoint)]
        assert m.requests == len(evs)
        assert m.errors_5xx == sum(e["status"] >= 500 for e in evs)
        # percentile_approx returns a real data point (nearest rank), like numpy's inverted_cdf
        exact = np.percentile([e["latency_ms"] for e in evs], 95, method="inverted_cdf")
        assert abs(m.p95_ms - exact) / exact < 0.02


def test_serving_writer_feeds_sink_and_detector(raw):
    class Memory:
        def __init__(self):
            self.metrics, self.events = [], []
        def write_metrics(self, rows):
            self.metrics.extend(rows)
        def write_incidents(self, events):
            self.events.extend(events)

    sink = Memory()
    batch = T.endpoint_minute_metrics(T.curated(T.parse_logs(raw)), watermark=None)
    ServingWriter(sink)(batch, 0)
    assert len(sink.metrics) == batch.count()
    starts = [r["window_start"] for r in sink.metrics]
    assert starts == sorted(starts)
    json.dumps(sink.metrics[0], default=str)   # serialisable for the sinks
