"""Score the incident detector against the failures the generator injected.

Replays the 1-minute endpoint metrics produced by the streaming job through a
fresh IncidentManager and compares the incidents with ground_truth.json.

  python -m benchmarks.evaluate_detection --metrics data/lake/serving/endpoint_metrics.jsonl \
      --truth data/ground_truth.json --out results/detection.json

A detection counts as a hit when an incident opens on the injected endpoint while
the scenario is active. Anything else is a false positive. Time-to-detect is
measured in event time from the scenario start to the alert (end of the
confirming window), so it includes the 2-window confirmation rule.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from sentinellake.detection import IncidentManager


def load_windows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    for r in rows:
        r["window_start"] = datetime.fromisoformat(r["window_start"].replace("Z", ""))
    rows.sort(key=lambda r: (r["window_start"], r["service"], r["endpoint"]))
    return rows


def evaluate(metrics: Path, truth_path: Path) -> dict:
    truth = json.loads(truth_path.read_text())
    mgr = IncidentManager()
    opened = []
    for w in load_windows(metrics):
        for action, inc in mgr.process(w):
            if action == "opened":
                opened.append(inc)

    scenarios = []
    matched_ids: set[str] = set()
    for s in truth["scenarios"]:
        start = datetime.fromisoformat(s["start_ts"]).replace(tzinfo=None)
        end = datetime.fromisoformat(s["end_ts"]).replace(tzinfo=None)
        hits = [i for i in opened
                if i.service == s["service"] and i.endpoint == s["endpoint"]
                and start <= i.opened_at < end + timedelta(minutes=2)]
        matched_ids.update(i.id for i in hits)
        first = min(hits, key=lambda i: i.detected_at, default=None)
        scenarios.append({
            "scenario": s["name"], "kind": s["kind"],
            "target": f'{s["service"]} {s["endpoint"]}',
            "duration_min": s["duration_min"],
            "detected": first is not None,
            "incident_type": first.type if first else None,
            "time_to_detect_min": round((first.detected_at - start).total_seconds() / 60, 1) if first else None,
            "reason": first.reason if first else None,
        })

    false_pos = [{"type": i.type, "target": f"{i.service} {i.endpoint}",
                  "opened_at": i.opened_at.isoformat(), "reason": i.reason}
                 for i in opened if i.id not in matched_ids]
    detected = [s for s in scenarios if s["detected"]]
    windows = sum(1 for _ in metrics.open())
    return {
        "windows_evaluated": windows,
        "scenarios_injected": len(scenarios),
        "scenarios_detected": len(detected),
        "recall": round(len(detected) / len(scenarios), 3),
        "incidents_opened": len(opened),
        "false_positives": len(false_pos),
        "precision": round(len(matched_ids) / len(opened), 3) if opened else None,
        "mean_time_to_detect_min": round(sum(s["time_to_detect_min"] for s in detected) / len(detected), 1)
        if detected else None,
        "scenarios": scenarios,
        "false_positive_details": false_pos,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics", default="data/lake/serving/endpoint_metrics.jsonl")
    p.add_argument("--truth", default="data/ground_truth.json")
    p.add_argument("--out", default="results/detection.json")
    a = p.parse_args()
    report = evaluate(Path(a.metrics), Path(a.truth))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ("scenarios", "false_positive_details")}, indent=2))
    for s in report["scenarios"]:
        print(f'  {s["scenario"]:<28} detected={s["detected"]!s:<5} ttd={s["time_to_detect_min"]} min '
              f'type={s["incident_type"]}')
    for f in report["false_positive_details"]:
        print(f'  FP {f["type"]} {f["target"]} at {f["opened_at"]}: {f["reason"]}')


if __name__ == "__main__":
    main()
