"""SentinelLake API + on-call dashboard (FastAPI).

  uvicorn api.main:app --port 8000          # SENTINEL_BACKEND=local|live

"Now" is the newest window in the store, not the wall clock, so a replayed
historical dataset looks exactly like live data.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sentinellake.catalog import SERVICES

from .repository import Repository, from_env

STATIC = Path(__file__).parent / "static"
DOWN_ERROR_RATE = 0.05

app = FastAPI(title="SentinelLake API", version="1.0.0",
              description="Reliability metrics and incidents for the monitored API estate.")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_repo: Repository | None = None


def repo() -> Repository:
    global _repo
    if _repo is None:
        _repo = from_env()
    return _repo


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _incident_out(d: dict, as_of: datetime | None) -> dict:
    # an incident lasts from its first bad minute to the end of its last bad minute
    last = d["last_seen"] if d["status"] == "resolved" else (as_of or d["last_seen"])
    end = last + timedelta(minutes=1)
    return {
        "id": d["_id"], "service": d["service"], "endpoint": d["endpoint"], "type": d["type"],
        "severity": d["severity"], "status": d["status"], "reason": d.get("reason"),
        "opened_at": _iso(d["opened_at"]), "detected_at": _iso(d.get("detected_at")),
        "last_seen": _iso(d["last_seen"]), "resolved_at": _iso(d.get("resolved_at")),
        "duration_min": round((end - d["opened_at"]).total_seconds() / 60),
    }


APP = STATIC / "app"           # React build (source in ui/); the original console stays at /classic


@app.get("/", include_in_schema=False)
def dashboard():
    built = APP / "index.html"
    return FileResponse(built if built.exists() else STATIC / "index.html")


@app.get("/classic", include_in_schema=False)
def classic_dashboard():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    r = repo()
    latest = r.latest_window()
    # SENTINEL_MODE=demo marks a hosted copy that serves a replayed dataset (see render.yaml)
    return {"status": "ok", "backend": r.backend, "mode": os.getenv("SENTINEL_MODE", "laptop"),
            "latest_window": _iso(latest)}


@app.get("/api/overview")
def overview(minutes: int = Query(60, ge=5, le=1440)):
    """Totals, per-service health and a minute-by-minute heartbeat for each service."""
    r = repo()
    as_of = r.latest_window()
    if as_of is None:
        return {"as_of": None, "minutes": minutes, "services": [], "totals": None}
    since = as_of - timedelta(minutes=minutes - 1)
    rows = r.metrics_since(since)
    incidents = r.incidents(limit=500)
    open_inc = [i for i in incidents if i["status"] == "open"]

    per_min: dict[str, dict[datetime, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    per_svc: dict[str, dict] = defaultdict(lambda: {"requests": 0, "errors": 0, "p95_weighted": 0.0})
    for m in rows:
        cell = per_min[m["service"]][m["window_start"]]
        cell[0] += m["requests"]
        cell[1] += m["errors_5xx"]
        s = per_svc[m["service"]]
        s["requests"] += m["requests"]
        s["errors"] += m["errors_5xx"]
        s["p95_weighted"] += m["p95_ms"] * m["requests"]

    minutes_axis = [since + timedelta(minutes=i) for i in range(minutes)]
    services = []
    for name in SERVICES:
        svc_inc = [i for i in incidents if i["service"] == name]
        beats = []
        for t in minutes_axis:
            req, err = per_min[name].get(t, (0, 0))
            rate = err / req if req else None
            covered = any(i["opened_at"] <= t <= i["last_seen"] for i in svc_inc)
            state = ("nodata" if req == 0 else "down" if rate >= DOWN_ERROR_RATE
                     else "degraded" if covered else "ok")
            beats.append({"t": _iso(t), "requests": req, "error_rate": rate, "state": state})
        s = per_svc[name]
        opened = [i for i in open_inc if i["service"] == name]
        services.append({
            "service": name,
            "requests": s["requests"],
            "error_rate": s["errors"] / s["requests"] if s["requests"] else 0.0,
            "p95_ms": s["p95_weighted"] / s["requests"] if s["requests"] else None,
            "status": ("down" if any(i["severity"] == "critical" for i in opened)
                       else "degraded" if opened else "healthy"),
            "open_incidents": len(opened),
            "heartbeat": beats,
        })

    total_req = sum(s["requests"] for s in services)
    total_err = sum(per_svc[s]["errors"] for s in per_svc)
    return {
        "as_of": _iso(as_of), "minutes": minutes,
        "totals": {"requests": total_req, "error_rate": total_err / total_req if total_req else 0.0,
                   "open_incidents": len(open_inc),
                   "incidents_in_range": sum(1 for i in incidents if i["last_seen"] >= since)},
        "services": services,
    }


@app.get("/api/services/{service}/timeseries")
def timeseries(service: str, minutes: int = Query(60, ge=5, le=1440)):
    """Per-endpoint p95 latency, 5xx rate and volume for one service, minute by minute."""
    if service not in SERVICES:
        raise HTTPException(404, f"unknown service '{service}'")
    r = repo()
    as_of = r.latest_window()
    if as_of is None:
        return {"service": service, "endpoints": {}}
    since = as_of - timedelta(minutes=minutes - 1)
    series: dict[str, list] = defaultdict(list)
    for m in sorted(r.metrics_since(since, service), key=lambda m: m["window_start"]):
        series[m["endpoint"]].append({"t": _iso(m["window_start"]), "requests": m["requests"],
                                      "error_rate": m["error_rate"], "p50_ms": m["p50_ms"],
                                      "p95_ms": m["p95_ms"], "p99_ms": m["p99_ms"]})
    return {"service": service, "as_of": _iso(as_of), "endpoints": series}


@app.get("/api/incidents")
def list_incidents(status: str | None = Query(None, pattern="^(open|resolved)$"),
                   limit: int = Query(50, ge=1, le=500)):
    r = repo()
    as_of = r.latest_window()
    return [_incident_out(d, as_of) for d in r.incidents(status, limit)]


def _weighted(rows: list[dict]) -> dict:
    req = sum(m["requests"] for m in rows)
    err = sum(m["errors_5xx"] for m in rows)
    return {"requests": req, "errors": err,
            "error_rate": err / req if req else 0.0,
            # request-weighted mean of per-endpoint p95s (an exact fleet p95 needs the raw events)
            "p95_ms": sum(m["p95_ms"] * m["requests"] for m in rows) / req if req else None}


@app.get("/api/fleet")
def fleet(minutes: int = Query(60, ge=5, le=1440), service: str | None = None):
    """Whole-fleet (or one service) minute series, the previous period for comparison,
    and per-endpoint totals for the 'slowest endpoints' table."""
    if service is not None and service not in SERVICES:
        raise HTTPException(404, f"unknown service '{service}'")
    r = repo()
    as_of = r.latest_window()
    if as_of is None:
        return {"as_of": None, "minutes": minutes, "series": [], "current": None, "previous": None, "endpoints": []}
    since = as_of - timedelta(minutes=minutes - 1)
    prev_since = since - timedelta(minutes=minutes)
    rows = r.metrics_since(prev_since)
    cur = [m for m in rows if m["window_start"] >= since]
    prev = [m for m in rows if m["window_start"] < since]

    scoped = [m for m in cur if service is None or m["service"] == service]
    by_min: dict[datetime, list[dict]] = defaultdict(list)
    for m in scoped:
        by_min[m["window_start"]].append(m)
    series = []
    for i in range(minutes):
        t = since + timedelta(minutes=i)
        w = _weighted(by_min.get(t, []))
        series.append({"t": _iso(t), "requests": w["requests"], "errors": w["errors"],
                       "error_rate": w["error_rate"], "p95_ms": w["p95_ms"]})

    by_ep: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for m in cur:
        by_ep[(m["service"], m["endpoint"])].append(m)
    endpoints = []
    for (svc, ep), ms in by_ep.items():
        w = _weighted(ms)
        endpoints.append({"service": svc, "endpoint": ep, "requests": w["requests"],
                          "error_rate": w["error_rate"], "p95_ms": w["p95_ms"],
                          "p99_ms": max(m["p99_ms"] for m in ms)})
    endpoints.sort(key=lambda e: e["p95_ms"] or 0, reverse=True)

    prev_scoped = [m for m in prev if service is None or m["service"] == service]
    return {"as_of": _iso(as_of), "minutes": minutes, "service": service, "series": series,
            "current": _weighted(scoped), "previous": _weighted(prev_scoped) if prev_scoped else None,
            "endpoints": endpoints}


LAKE_ZONES = (("raw", "Raw zone", "JSON, as received"), ("curated", "Curated zone", "Parquet, partitioned dt/hr"),
              ("quarantine", "Quarantine", "malformed records"), ("serving", "Serving store", "minute metrics + incidents"))


@app.get("/api/lake")
def lake():
    """Size of each data-lake zone. Laptop mode reads the local lake folder; in cluster mode the
    lake lives in HDFS (see the NameNode UI on :9870), so this reports it as unavailable."""
    r = repo()
    snapshot = os.getenv("SENTINEL_LAKE_SNAPSHOT")
    if snapshot:                      # hosted demo: sizes recorded when the dataset was produced
        import json
        return {**json.loads(Path(snapshot).read_text()), "snapshot": True}
    if r.backend != "local":
        return {"available": False, "backend": r.backend, "zones": []}
    root = Path(os.getenv("SENTINEL_LAKE_DIR") or Path(os.getenv("SENTINEL_LOCAL_DIR", "data/lake/serving")).parent)
    zones = []
    for key, name, desc in LAKE_ZONES:
        files = [f for f in (root / key).rglob("*") if f.is_file() and "_spark_metadata" not in f.parts
                 and not f.name.startswith(".")] if (root / key).exists() else []
        zones.append({"zone": key, "name": name, "description": desc,
                      "bytes": sum(f.stat().st_size for f in files), "files": len(files),
                      "partitions": len({f.parent for f in files})})
    return {"available": True, "backend": r.backend, "root": str(root), "zones": zones}
