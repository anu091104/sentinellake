from collections import Counter
from datetime import timedelta

from sentinellake.generator import DEFAULT_SCENARIOS, Scenario, TrafficModel

from .conftest import START

FIELDS = {"ts", "trace_id", "service", "method", "route", "status", "latency_ms",
          "bytes", "region", "instance", "client_id"}


def test_events_have_full_schema_and_are_time_ordered(sample_events):
    assert sample_events, "generator produced nothing"
    assert all(set(e) == FIELDS for e in sample_events)
    ts = [e["ts"] for e in sample_events]
    assert ts == sorted(ts)


def test_same_seed_same_traffic():
    a = TrafficModel(600, DEFAULT_SCENARIOS, seed=1).minute_events(START, 0)
    b = TrafficModel(600, DEFAULT_SCENARIOS, seed=1).minute_events(START, 0)
    assert a == b


def test_baseline_error_rate_is_low(sample_events):
    rate = sum(e["status"] >= 500 for e in sample_events) / len(sample_events)
    assert 0.001 < rate < 0.01


def _minute(model, scenario_minute):
    return model.minute_events(START + timedelta(minutes=scenario_minute), scenario_minute)


def test_error_burst_scenario_raises_5xx_on_target_only():
    s = Scenario("t", "error_burst", "payments", "POST /v1/charge", 0, 5, 0.5)
    events = _minute(TrafficModel(6000, (s,), seed=2), 1)
    target = [e for e in events if e["service"] == "payments" and e["route"] == "/v1/charge"]
    others = [e for e in events if e["service"] != "payments"]
    assert sum(e["status"] >= 500 for e in target) / len(target) > 0.35
    assert sum(e["status"] >= 500 for e in others) / len(others) < 0.02


def test_traffic_drop_scenario_cuts_volume():
    s = Scenario("t", "traffic_drop", "inventory", "GET /v1/stock", 0, 5, 0.1)
    def count(events):
        return Counter(f'{e["method"]} {e["route"]}' for e in events)["GET /v1/stock"]
    before = count(_minute(TrafficModel(6000, (s,), seed=2), 10))
    during = count(_minute(TrafficModel(6000, (s,), seed=2), 1))
    assert during < before * 0.25
