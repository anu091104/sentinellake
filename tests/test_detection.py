import random
from datetime import datetime, timedelta

from sentinellake.detection import (PENDING_WINDOWS, RESOLVE_AFTER, WARMUP_WINDOWS,
                                    IncidentManager, incident_id)

T0 = datetime(2026, 10, 12, 6, 0)
rng = random.Random(0)


def window(i, requests=400, p95=100.0, error_rate=0.004, endpoint="GET /v1/search"):
    return {"window_start": T0 + timedelta(minutes=i), "service": "search", "endpoint": endpoint,
            "requests": requests, "errors_5xx": round(requests * error_rate),
            "error_rate": error_rate, "p95_ms": p95}


def normal(i):
    return window(i, requests=int(rng.gauss(400, 15)), p95=rng.gauss(100, 4),
                  error_rate=max(0.0, rng.gauss(0.004, 0.001)))


def warm(mgr, n=30):
    for i in range(n):
        assert mgr.process(normal(i)) == []
    return n


def test_normal_traffic_never_alerts():
    mgr = IncidentManager()
    for i in range(300):
        assert mgr.process(normal(i)) == []


def test_critical_error_burst_opens_immediately_and_resolves():
    mgr = IncidentManager()
    i = warm(mgr)
    ev = mgr.process(window(i, error_rate=0.2))
    assert [(a, inc.type, inc.severity) for a, inc in ev] == [("opened", "ERROR_BURST", "critical")]
    assert mgr.process(window(i + 1, error_rate=0.25))[0][0] == "updated"
    actions = [a for k in range(RESOLVE_AFTER) for a, _ in mgr.process(normal(i + 2 + k))]
    assert actions == ["resolved"]


def test_error_rule_works_before_warmup():
    mgr = IncidentManager()
    ev = mgr.process(window(0, error_rate=0.3))
    assert ev and ev[0][1].type == "ERROR_BURST"


def test_latency_spike_needs_confirmation_window():
    mgr = IncidentManager()
    i = warm(mgr)
    assert mgr.process(window(i, p95=600)) == []                 # one bad minute: pending only
    ev = mgr.process(window(i + 1, p95=650))
    assert [(a, inc.type) for a, inc in ev] == [("opened", "LATENCY_SPIKE")]
    inc = ev[0][1]
    assert inc.opened_at == T0 + timedelta(minutes=i)             # dated to the first bad minute
    assert inc.windows == PENDING_WINDOWS


def test_single_blip_is_ignored():
    mgr = IncidentManager()
    i = warm(mgr)
    assert mgr.process(window(i, p95=600)) == []
    assert mgr.process(normal(i + 1)) == []
    assert mgr.process(window(i + 2, p95=600)) == []             # streak was reset


def test_outage_does_not_become_the_new_normal():
    mgr = IncidentManager()
    i = warm(mgr)
    before = mgr.baselines[("search", "GET /v1/search")].p95.mean
    for k in range(20):
        mgr.process(window(i + k, p95=900))
    after = mgr.baselines[("search", "GET /v1/search")].p95.mean
    assert abs(after - before) < 1e-9


def test_slow_drift_is_caught_by_slow_baseline():
    mgr = IncidentManager()
    i = warm(mgr, 60)
    opened = []
    for k in range(25):                                           # +10% per minute, like the auth scenario
        for a, inc in mgr.process(window(i + k, p95=100 * (1 + 0.10 * k))):
            if a == "opened":
                opened.append(inc.type)
    assert "LATENCY_DRIFT" in opened


def test_traffic_drop_detected():
    mgr = IncidentManager()
    i = warm(mgr)
    mgr.process(window(i, requests=30))
    ev = mgr.process(window(i + 1, requests=25))
    assert ev and ev[0][1].type == "TRAFFIC_DROP"


def test_low_traffic_window_cannot_trigger_latency():
    mgr = IncidentManager()
    i = warm(mgr)
    for k in range(3):
        ev = mgr.process(window(i + k, requests=10, p95=5000, error_rate=0.0))
        assert all(inc.type == "TRAFFIC_DROP" for _, inc in ev)


def test_incident_id_is_deterministic():
    assert incident_id("a", "b", "c", T0) == incident_id("a", "b", "c", T0)
    assert incident_id("a", "b", "c", T0) != incident_id("a", "b", "c", T0 + timedelta(minutes=1))


def test_warmup_constant_is_respected():
    mgr = IncidentManager()
    for i in range(WARMUP_WINDOWS - 1):
        mgr.process(normal(i))
    # latency rule is not active yet, so even a huge p95 can't open an incident
    assert mgr.process(window(WARMUP_WINDOWS, p95=5000)) == []
