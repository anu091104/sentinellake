"""Re-run the detector on several independently generated datasets (different seeds).

One good score could be luck. This simulates N separate 6-hour days, computes the
1-minute endpoint metrics in plain Python (exact percentiles, no Spark), and scores
each day with benchmarks.evaluate_detection.

  python -m benchmarks.detection_robustness --seeds 1 2 3 4 5 --out results/detection_seeds.json
"""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from sentinellake.generator import DEFAULT_SCENARIOS, TrafficModel, iter_replay

from .evaluate_detection import evaluate

START = datetime(2026, 10, 12, 6, tzinfo=timezone.utc)


def simulate(seed: int, workdir: Path, minutes: int = 360) -> dict:
    model = TrafficModel(6000, DEFAULT_SCENARIOS, seed=seed)
    rows = []
    for i, events in iter_replay(model, START, minutes):
        groups = defaultdict(list)
        for e in events:
            groups[(e["service"], f'{e["method"]} {e["route"]}')].append(e)
        ws = (START + timedelta(minutes=i)).replace(tzinfo=None).isoformat()
        for (svc, ep), evs in groups.items():
            lat = np.array([e["latency_ms"] for e in evs])
            n, e5 = len(evs), sum(e["status"] >= 500 for e in evs)
            rows.append({"window_start": ws, "service": svc, "endpoint": ep, "requests": n,
                         "errors_5xx": e5, "errors_4xx": 0, "error_rate": e5 / n,
                         "p50_ms": float(np.percentile(lat, 50, method="inverted_cdf")),
                         "p95_ms": float(np.percentile(lat, 95, method="inverted_cdf")),
                         "p99_ms": float(np.percentile(lat, 99, method="inverted_cdf"))})
    metrics, truth = workdir / f"m{seed}.jsonl", workdir / f"t{seed}.json"
    metrics.write_text("\n".join(json.dumps(r) for r in rows))
    truth.write_text(json.dumps({"scenarios": [
        {**asdict(s), "start_ts": (START + timedelta(minutes=s.start_min)).isoformat(),
         "end_ts": (START + timedelta(minutes=s.start_min + s.duration_min)).isoformat()}
        for s in DEFAULT_SCENARIOS]}))
    return evaluate(metrics, truth)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--out", default="results/detection_seeds.json")
    a = p.parse_args()
    runs = []
    with tempfile.TemporaryDirectory() as tmp:
        for s in a.seeds:
            r = simulate(s, Path(tmp))
            runs.append({"seed": s, "detected": r["scenarios_detected"], "injected": r["scenarios_injected"],
                         "false_positives": r["false_positives"],
                         "ttd_min": {x["scenario"]: x["time_to_detect_min"] for x in r["scenarios"]}})
            print(runs[-1])
    summary = {
        "days_simulated": len(runs),
        "scenarios_detected": sum(r["detected"] for r in runs),
        "scenarios_injected": sum(r["injected"] for r in runs),
        "false_positives": sum(r["false_positives"] for r in runs),
        "ttd_range_min": {k: [min(r["ttd_min"][k] for r in runs), max(r["ttd_min"][k] for r in runs)]
                          for k in runs[0]["ttd_min"]},
        "runs": runs,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(summary, indent=2))
    print({k: v for k, v in summary.items() if k != "runs"})


if __name__ == "__main__":
    main()
