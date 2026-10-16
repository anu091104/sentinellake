"""Read side of the serving layer.

LiveRepository reads Cassandra (metrics) and MongoDB (incidents).
LocalRepository reads the JSONL files the streaming job writes in local mode.
Both return plain dicts so the API code doesn't care which one it talks to.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol


def _parse_ts(v):
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    return datetime.fromisoformat(str(v).replace("Z", "")).replace(tzinfo=None)


class Repository(Protocol):
    backend: str
    def latest_window(self) -> datetime | None: ...
    def metrics_since(self, since: datetime, service: str | None = None) -> list[dict]: ...
    def incidents(self, status: str | None = None, limit: int = 100) -> list[dict]: ...


class LocalRepository:
    backend = "local"

    def __init__(self, root: str):
        self.root = Path(root)
        self._cache: dict[str, tuple[float, list[dict]]] = {}

    def _load(self, name: str) -> list[dict]:
        path = self.root / name
        if not path.exists():
            return []
        mtime = path.stat().st_mtime
        hit = self._cache.get(name)
        if hit and hit[0] == mtime:
            return hit[1]
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        self._cache[name] = (mtime, rows)
        return rows

    def _metrics(self) -> list[dict]:
        rows = self._load("endpoint_metrics.jsonl")
        for r in rows:
            r["window_start"] = _parse_ts(r["window_start"])
        return rows

    def latest_window(self):
        rows = self._metrics()
        return max((r["window_start"] for r in rows), default=None)

    def metrics_since(self, since, service=None):
        return [r for r in self._metrics()
                if r["window_start"] >= since and (service is None or r["service"] == service)]

    def incidents(self, status=None, limit=100):
        latest: dict[str, dict] = {}
        for ev in self._load("incidents.jsonl"):          # event log -> latest state per id
            latest[ev["_id"]] = ev
        docs = sorted(latest.values(), key=lambda d: d["opened_at"], reverse=True)
        if status:
            docs = [d for d in docs if d["status"] == status]
        for d in docs:
            for k in ("opened_at", "detected_at", "last_seen", "resolved_at"):
                if d.get(k):
                    d[k] = _parse_ts(d[k])
        return docs[:limit]


class LiveRepository:
    backend = "cassandra+mongodb"

    def __init__(self):
        from cassandra.cluster import Cluster
        from pymongo import MongoClient

        from sentinellake.catalog import SERVICES

        self.services = SERVICES
        self.session = Cluster(os.getenv("CASSANDRA_HOSTS", "cassandra").split(",")).connect("sentinel")
        self.q_latest = self.session.prepare(
            "SELECT window_start FROM endpoint_metrics WHERE service = ? AND day = ? LIMIT 1")
        self.q_range = self.session.prepare(
            "SELECT * FROM endpoint_metrics WHERE service = ? AND day = ? AND window_start >= ?")
        self.mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://mongo:27017"))["sentinel"]["incidents"]

    def latest_window(self):
        today = datetime.now(timezone.utc).date()
        best = None
        for day in (today, today - timedelta(days=1)):
            for s in self.services:
                row = self.session.execute(self.q_latest, (s, day)).one()
                if row and (best is None or row.window_start > best):
                    best = row.window_start
            if best:
                break
        return best

    def metrics_since(self, since, service=None):
        days = {since.date(), (since + timedelta(days=1)).date()}
        rows = []
        for s in [service] if service else self.services:
            for d in days:
                rows.extend(r._asdict() for r in self.session.execute(self.q_range, (s, d, since)))
        return rows

    def incidents(self, status=None, limit=100):
        q = {"status": status} if status else {}
        docs = list(self.mongo.find(q, {"timeline": 0}).sort("opened_at", -1).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs


def from_env() -> Repository:
    if os.getenv("SENTINEL_BACKEND", "local") == "live":
        return LiveRepository()
    return LocalRepository(os.getenv("SENTINEL_LOCAL_DIR", "data/lake/serving"))
