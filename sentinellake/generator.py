"""Synthetic API access-log generator.

Produces realistic gateway logs for the services in ``catalog.py`` and injects
known failures ("scenarios") so the detectors can be scored against ground truth.

Two modes:
  replay  - simulate N hours of traffic as fast as possible into JSONL files
            (used for local runs, benchmarks and Hadoop batch jobs)
  live    - stream events in real time to a Kafka topic, keyed by service

Examples:
  python -m sentinellake.generator replay --hours 6 --out data/landing
  python -m sentinellake.generator live --bootstrap localhost:9094 --rps 150
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from . import catalog
from .catalog import Endpoint


@dataclass(frozen=True)
class Scenario:
    """A failure we deliberately inject, and later expect to detect."""
    name: str
    kind: str              # error_burst | latency_spike | traffic_drop | latency_ramp
    service: str
    endpoint: str
    start_min: int         # minutes after the simulation start
    duration_min: int
    magnitude: float

    def active(self, minute: float) -> bool:
        return self.start_min <= minute < self.start_min + self.duration_min

    def progress(self, minute: float) -> float:
        return (minute - self.start_min) / self.duration_min


DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("payment-gateway-outage", "error_burst", "payments", "POST /v1/charge", 90, 12, 0.18),
    Scenario("search-index-rebuild", "latency_spike", "search", "GET /v1/search", 180, 15, 5.0),
    Scenario("inventory-silent-failure", "traffic_drop", "inventory", "GET /v1/stock", 260, 10, 0.10),
    Scenario("auth-db-pool-exhaustion", "latency_ramp", "auth", "POST /v1/token", 300, 20, 3.0),
)


class TrafficModel:
    def __init__(self, rpm: int, scenarios: tuple[Scenario, ...], seed: int = 7):
        self.rpm = rpm
        self.scenarios = scenarios
        self.rng = random.Random(seed)
        total = sum(e.weight for e in catalog.ENDPOINTS)
        self.endpoints = catalog.ENDPOINTS
        self.weights = [e.weight / total for e in self.endpoints]

    def _diurnal(self, ts: datetime) -> float:
        # gentle day/night swing peaking around 13:00 UTC, +/- 25%
        hour = ts.hour + ts.minute / 60
        return 1.0 + 0.25 * math.sin((hour - 7) / 24 * 2 * math.pi)

    def _active(self, ep: Endpoint, minute: float) -> list[Scenario]:
        return [s for s in self.scenarios
                if s.service == ep.service and s.endpoint == ep.name and s.active(minute)]

    def minute_events(self, minute_start: datetime, minute_index: int) -> list[dict]:
        rng = self.rng
        expected = self.rpm * self._diurnal(minute_start)
        events: list[dict] = []
        for ep, w in zip(self.endpoints, self.weights):
            lam = expected * w
            active = self._active(ep, minute_index)
            for s in active:
                if s.kind == "traffic_drop":
                    lam *= s.magnitude
            n = max(0, int(rng.gauss(lam, math.sqrt(lam))))
            for _ in range(n):
                events.append(self._event(ep, minute_start + timedelta(seconds=rng.random() * 60),
                                          active, minute_index))
        events.sort(key=lambda e: e["ts"])
        return events

    def _event(self, ep: Endpoint, ts: datetime, active: list[Scenario], minute: int) -> dict:
        rng = self.rng
        p5xx, latency_mult = ep.p5xx, 1.0
        for s in active:
            if s.kind == "error_burst":
                p5xx = s.magnitude
            elif s.kind == "latency_spike":
                latency_mult *= s.magnitude
            elif s.kind == "latency_ramp":
                latency_mult *= 1 + (s.magnitude - 1) * s.progress(minute)

        roll = rng.random()
        if roll < p5xx:
            status = rng.choices(catalog.SERVER_5XX, catalog.SERVER_5XX_WEIGHTS)[0]
        elif roll < p5xx + ep.p4xx:
            status = rng.choices(catalog.CLIENT_4XX, catalog.CLIENT_4XX_WEIGHTS)[0]
        else:
            status = 200 if ep.method == "GET" else rng.choice((200, 201))

        latency = rng.lognormvariate(math.log(ep.median_ms * latency_mult), 0.45)
        if status == 504:
            latency = max(latency, 3000 + rng.random() * 2000)   # gateway timeout
        elif status in (401, 404, 429):
            latency *= 0.3                                       # rejected early

        method, path = ep.method, ep.path
        return {
            "ts": ts.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "trace_id": uuid.UUID(int=rng.getrandbits(128)).hex[:16],
            "service": ep.service,
            "method": method,
            "route": path,
            "status": status,
            "latency_ms": round(latency, 2),
            "bytes": int(rng.lognormvariate(7.5, 0.8)) if status < 400 else rng.randint(80, 400),
            "region": rng.choices(catalog.REGIONS, catalog.REGION_WEIGHTS)[0],
            "instance": f"{ep.service}-{rng.randint(1, 4)}",
            "client_id": f"c{rng.randint(1, 500):04d}",
        }


def iter_replay(model: TrafficModel, start: datetime, minutes: int) -> Iterator[tuple[int, list[dict]]]:
    for m in range(minutes):
        yield m, model.minute_events(start + timedelta(minutes=m), m)


def run_replay(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    model = TrafficModel(args.rpm, DEFAULT_SCENARIOS, seed=args.seed)
    minutes = int(args.hours * 60)

    total, chunk, chunk_start = 0, [], 0
    for m, events in iter_replay(model, start, minutes):
        chunk.extend(events)
        if (m + 1) % args.file_minutes == 0 or m == minutes - 1:
            name = (start + timedelta(minutes=chunk_start)).strftime("api-%Y%m%dT%H%M.jsonl")
            with open(out / name, "w", newline="\n") as f:
                f.writelines(json.dumps(e, separators=(",", ":")) + "\n" for e in chunk)
            total += len(chunk)
            chunk, chunk_start = [], m + 1
    if args.corrupt:
        # a few malformed lines, the way real pipelines receive them
        with open(out / "api-zz-malformed.jsonl", "w", newline="\n") as f:
            f.write('{"ts": "not-a-date", "service": "auth"}\n{broken json\n')

    truth = {
        "simulation_start": start.isoformat(),
        "minutes": minutes,
        "rpm": args.rpm,
        "scenarios": [
            {**asdict(s),
             "start_ts": (start + timedelta(minutes=s.start_min)).isoformat(),
             "end_ts": (start + timedelta(minutes=s.start_min + s.duration_min)).isoformat()}
            for s in DEFAULT_SCENARIOS
        ],
    }
    (out.parent / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(f"wrote {total:,} events over {minutes} simulated minutes to {out}")


def run_live(args: argparse.Namespace) -> None:
    from confluent_kafka import Producer   # only needed in live mode

    producer = Producer({"bootstrap.servers": args.bootstrap, "linger.ms": 50,
                         "compression.type": "lz4", "acks": "all"})
    scenarios = DEFAULT_SCENARIOS
    if args.demo:
        # compressed schedule for a live demo: first failure after the
        # detectors have ~12 minutes of baseline, then one every 10 minutes
        scenarios = tuple(replace(s, start_min=12 + i * 10, duration_min=min(s.duration_min, 8))
                          for i, s in enumerate(DEFAULT_SCENARIOS))
        args.cycle_min = 55
    model = TrafficModel(args.rps * 60, scenarios, seed=args.seed)
    t0 = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    minute = 0
    print(f"streaming ~{args.rps} events/s to {args.topic}; scenarios repeat every "
          f"{args.cycle_min} min (Ctrl+C to stop)")
    try:
        while True:
            scenario_clock = minute % args.cycle_min
            events = model.minute_events(t0 + timedelta(minutes=minute), scenario_clock)
            minute_wall_start = time.monotonic()
            for i, e in enumerate(events):
                # pace sends across the minute so event time ~ wall time
                target = minute_wall_start + 60 * i / max(len(events), 1)
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                e["ts"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                producer.produce(args.topic, key=e["service"], value=json.dumps(e))
                producer.poll(0)
            minute += 1
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush(10)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)

    r = sub.add_parser("replay", help="simulate historical traffic into JSONL files")
    r.add_argument("--hours", type=float, default=6)
    r.add_argument("--rpm", type=int, default=6000, help="average requests per minute")
    r.add_argument("--start", default="2026-10-12T06:00:00")
    r.add_argument("--out", default="data/landing")
    r.add_argument("--file-minutes", type=int, default=5)
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--corrupt", action="store_true", help="also write a malformed file")
    r.set_defaults(func=run_replay)

    l_ = sub.add_parser("live", help="stream events to Kafka in real time")
    l_.add_argument("--bootstrap", default="localhost:9094")
    l_.add_argument("--topic", default="api-logs")
    l_.add_argument("--rps", type=int, default=100)
    l_.add_argument("--cycle-min", type=int, default=360,
                    help="scenario schedule repeats every N minutes")
    l_.add_argument("--demo", action="store_true",
                    help="compressed schedule: first incident after 12 minutes")
    l_.add_argument("--seed", type=int, default=7)
    l_.set_defaults(func=run_live)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
