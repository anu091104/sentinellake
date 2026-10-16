import json
from datetime import datetime, timedelta

import mongomock
import pytest
from fastapi.testclient import TestClient

from sentinellake.detection import Incident
from sentinellake.streaming.sinks import CassandraMongoSink, LocalSink

T0 = datetime(2026, 10, 12, 9, 0)


def incident(status="open", last=6):
    return Incident("inc1", "payments", "POST /v1/charge", "ERROR_BURST", "critical",
                    T0 + timedelta(minutes=2), T0 + timedelta(minutes=3), T0 + timedelta(minutes=last),
                    "5xx rate 18.0% vs normal 0.5%", 0.18, 0.005, status=status)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    sink = LocalSink(str(tmp_path))
    rows = []
    for m in range(30):
        for svc, ep in (("payments", "POST /v1/charge"), ("search", "GET /v1/search")):
            bad = svc == "payments" and 2 <= m <= 6
            rows.append({"window_start": T0 + timedelta(minutes=m), "service": svc, "endpoint": ep,
                         "requests": 200, "errors_5xx": 40 if bad else 1, "errors_4xx": 3,
                         "error_rate": 0.2 if bad else 0.005, "p50_ms": 50.0, "p95_ms": 120.0,
                         "p99_ms": 200.0, "avg_bytes": 900.0})
    sink.write_metrics(rows)
    sink.write_incidents([("opened", incident()), ("resolved", incident("resolved", last=6))])
    monkeypatch.setenv("SENTINEL_BACKEND", "local")
    monkeypatch.setenv("SENTINEL_LOCAL_DIR", str(tmp_path))
    import api.main as main
    main._repo = None
    return TestClient(main.app)


def test_health(client):
    body = client.get("/health").json()
    assert body["backend"] == "local" and body["latest_window"] == "2026-10-12T09:29:00Z"


def test_overview_heartbeat_marks_bad_minutes(client):
    d = client.get("/api/overview?minutes=30").json()
    pay = next(s for s in d["services"] if s["service"] == "payments")
    states = [b["state"] for b in pay["heartbeat"]]
    assert states[2:7] == ["down"] * 5
    assert states[0] == "ok" and states[10] == "ok"
    assert d["totals"]["requests"] == 30 * 400
    assert d["totals"]["open_incidents"] == 0          # latest event for inc1 is 'resolved'


def test_timeseries_and_unknown_service(client):
    d = client.get("/api/services/search/timeseries?minutes=10").json()
    assert len(d["endpoints"]["GET /v1/search"]) == 10
    assert client.get("/api/services/nope/timeseries").status_code == 404


def test_incidents_endpoint(client):
    inc = client.get("/api/incidents").json()
    assert len(inc) == 1 and inc[0]["status"] == "resolved" and inc[0]["duration_min"] == 5
    assert client.get("/api/incidents?status=open").json() == []
    assert client.get("/api/incidents?status=bogus").status_code == 422


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "SentinelLake" in r.text


def test_mongo_upsert_is_idempotent():
    sink = CassandraMongoSink.__new__(CassandraMongoSink)      # skip real connections
    sink.incidents = mongomock.MongoClient().db.incidents
    events = [("opened", incident())]
    sink.write_incidents(events)
    sink.write_incidents(events)                                # replayed micro-batch
    assert sink.incidents.count_documents({}) == 1
    sink.write_incidents([("resolved", incident("resolved", last=6))])
    doc = sink.incidents.find_one({"_id": "inc1"})
    assert doc["status"] == "resolved" and len(doc["timeline"]) == 3


def test_local_sink_writes_jsonl(tmp_path):
    sink = LocalSink(str(tmp_path))
    sink.write_incidents([("opened", incident())])
    line = json.loads((tmp_path / "incidents.jsonl").read_text())
    assert line["action"] == "opened" and line["_id"] == "inc1"


def test_fleet_series_endpoints_and_previous_period(client):
    d = client.get("/api/fleet?minutes=10").json()
    assert len(d["series"]) == 10 and d["series"][-1]["requests"] == 400
    assert d["current"]["requests"] == 4000 and d["previous"]["requests"] == 4000
    assert {e["endpoint"] for e in d["endpoints"]} == {"POST /v1/charge", "GET /v1/search"}
    one = client.get("/api/fleet?minutes=30&service=payments").json()
    assert one["current"]["errors"] == 5 * 40 + 25 * 1          # the 5 bad minutes are in range
    assert client.get("/api/fleet?service=nope").status_code == 404


def test_lake_zone_sizes(client, tmp_path, monkeypatch):
    lake = tmp_path / "lake"
    (lake / "curated" / "dt=2026-10-12" / "hr=9").mkdir(parents=True)
    (lake / "curated" / "dt=2026-10-12" / "hr=9" / "part-0.parquet").write_bytes(b"x" * 100)
    (lake / "curated" / "_spark_metadata").mkdir()
    (lake / "curated" / "_spark_metadata" / "0").write_bytes(b"y" * 50)   # bookkeeping, not data
    monkeypatch.setenv("SENTINEL_LAKE_DIR", str(lake))
    zones = {z["zone"]: z for z in client.get("/api/lake").json()["zones"]}
    assert zones["curated"]["bytes"] == 100 and zones["curated"]["files"] == 1
    assert zones["raw"]["bytes"] == 0


def test_classic_console_still_served(client):
    assert "SentinelLake" in client.get("/classic").text


def test_hosted_demo_uses_lake_snapshot(client, tmp_path, monkeypatch):
    snap = tmp_path / "lake.json"
    snap.write_text(json.dumps({"available": True, "backend": "local", "zones": [{"zone": "raw", "bytes": 7}]}))
    monkeypatch.setenv("SENTINEL_LAKE_SNAPSHOT", str(snap))
    monkeypatch.setenv("SENTINEL_MODE", "demo")
    d = client.get("/api/lake").json()
    assert d["snapshot"] is True and d["zones"][0]["bytes"] == 7
    assert client.get("/health").json()["mode"] == "demo"
