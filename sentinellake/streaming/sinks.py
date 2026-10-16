"""Serving-layer writers called from ``foreachBatch``.

Production ("live") mode writes metrics to Cassandra and incidents to MongoDB.
Local mode writes the same records to JSONL files so the whole pipeline can be
run on a laptop without containers. Both implement the same two methods.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol

from ..detection import Incident


class ServingSink(Protocol):
    def write_metrics(self, rows: list[dict]) -> None: ...
    def write_incidents(self, events: Iterable[tuple[str, Incident]]) -> None: ...


def _json_default(o):
    if isinstance(o, datetime):
        return o.astimezone(timezone.utc).isoformat() if o.tzinfo else o.isoformat()
    raise TypeError(type(o))


class LocalSink:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.metrics_path = self.root / "endpoint_metrics.jsonl"
        self.incidents_path = self.root / "incidents.jsonl"

    def write_metrics(self, rows: list[dict]) -> None:
        with open(self.metrics_path, "a", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, default=_json_default) + "\n")

    def write_incidents(self, events: Iterable[tuple[str, Incident]]) -> None:
        # append-only event log; readers keep the latest version per _id (like an upsert)
        with open(self.incidents_path, "a", newline="\n") as f:
            for action, inc in events:
                f.write(json.dumps({"action": action, **inc.to_doc()}, default=_json_default) + "\n")


class CassandraMongoSink:
    """Metrics -> Cassandra (fast time-series writes), incidents -> MongoDB (rich documents)."""

    def __init__(self) -> None:
        from cassandra.cluster import Cluster
        from pymongo import MongoClient

        hosts = os.getenv("CASSANDRA_HOSTS", "cassandra").split(",")
        self.session = Cluster(hosts).connect("sentinel")
        self.insert_metric = self.session.prepare("""
            INSERT INTO endpoint_metrics (service, day, window_start, endpoint, requests,
                errors_5xx, errors_4xx, error_rate, p50_ms, p95_ms, p99_ms, avg_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""")
        self.bump_counter = self.session.prepare("""
            UPDATE service_daily_counters SET requests = requests + ?, errors_5xx = errors_5xx + ?
            WHERE service = ? AND day = ?""")
        mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://mongo:27017"))
        self.incidents = mongo["sentinel"]["incidents"]

    def write_metrics(self, rows: list[dict]) -> None:
        from cassandra.concurrent import execute_concurrent_with_args

        params = [(r["service"], r["window_start"].date(), r["window_start"], r["endpoint"],
                   r["requests"], r["errors_5xx"], r["errors_4xx"], r["error_rate"],
                   r["p50_ms"], r["p95_ms"], r["p99_ms"], r["avg_bytes"]) for r in rows]
        # INSERT is an upsert on the primary key -> replaying a batch is harmless
        execute_concurrent_with_args(self.session, self.insert_metric, params, concurrency=32)

        totals: dict[tuple, list[int]] = {}
        for r in rows:
            t = totals.setdefault((r["service"], r["window_start"].date()), [0, 0])
            t[0] += r["requests"]
            t[1] += r["errors_5xx"]
        # counters are NOT idempotent: a replayed batch double-counts (at-least-once)
        execute_concurrent_with_args(self.session, self.bump_counter,
                                     [(a, b, s, d) for (s, d), (a, b) in totals.items()])

    def write_incidents(self, events: Iterable[tuple[str, Incident]]) -> None:
        from pymongo import UpdateOne

        ops = []
        for action, inc in events:
            doc = inc.to_doc()
            _id = doc.pop("_id")
            ops.append(UpdateOne(
                {"_id": _id},
                {"$set": doc,
                 "$push": {"timeline": {"$each": [{"at": inc.last_seen, "action": action}],
                                        "$slice": -100}}},
                upsert=True))
        if ops:
            self.incidents.bulk_write(ops, ordered=True)
