"""Draw the figures used in the README, slides and report from the results files.

  python -m benchmarks.make_charts
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

INK, INK2, RULE = "#1A2430", "#566372", "#CDD5DD"
ACCENT, MUTED, INCIDENT = "#2F5DA8", "#9AA7B4", "#B3261E"
OUT = Path("docs/img")

plt.rcParams.update({
    "font.family": ["Inter", "DejaVu Sans"], "font.size": 11, "text.color": INK,
    "axes.labelcolor": INK2, "axes.edgecolor": RULE, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#E6EAEE",
    "grid.linewidth": 0.8, "axes.axisbelow": True, "figure.dpi": 200, "savefig.bbox": "tight",
})


def detection_timeline(metrics: Path, truth: Path, detection: Path) -> None:
    rows = [json.loads(line) for line in metrics.read_text().splitlines()]
    t = json.loads(truth.read_text())
    det = {s["scenario"]: s for s in json.loads(detection.read_text())["scenarios"]}
    panels = [  # scenario, metric, y label, scale
        ("payment-gateway-outage", "error_rate", "5xx rate (%)", 100),
        ("search-index-rebuild", "p95_ms", "p95 latency (ms)", 1),
        ("inventory-silent-failure", "requests", "requests / min", 1),
        ("auth-db-pool-exhaustion", "p95_ms", "p95 latency (ms)", 1),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.2))
    for ax, (name, key, label, scale) in zip(axes.flat, panels):
        s = next(x for x in t["scenarios"] if x["name"] == name)
        start = datetime.fromisoformat(s["start_ts"]).replace(tzinfo=None)
        end = datetime.fromisoformat(s["end_ts"]).replace(tzinfo=None)
        lo, hi = start - timedelta(minutes=45), end + timedelta(minutes=25)
        pts = sorted((datetime.fromisoformat(r["window_start"]), r[key] * scale) for r in rows
                     if r["service"] == s["service"] and r["endpoint"] == s["endpoint"]
                     and lo <= datetime.fromisoformat(r["window_start"]) <= hi)
        ax.axvspan(start, end, color=INCIDENT, alpha=0.09, lw=0)
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=ACCENT, lw=1.8)
        d = det[name]
        if d["detected"]:
            at = start + timedelta(minutes=d["time_to_detect_min"])
            ax.axvline(at, color=INCIDENT, lw=1.4, ls=(0, (3, 2)))
            ax.set_title(f'{d["incident_type"]}, alert after {d["time_to_detect_min"]:.0f} min',
                         loc="right", fontsize=10, color=INCIDENT, pad=8)
        ax.set_title(f'{s["service"]} {s["endpoint"]}', loc="left", fontsize=11.5, fontweight="bold", pad=8)
        ax.set_ylabel(label)
        ax.set_ylim(bottom=0)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))
    fig.text(0.01, -0.01, "Shaded: when the failure was injected.  Dashed: when SentinelLake raised the alert.",
             color=INK2, fontsize=10)
    fig.tight_layout(h_pad=2.2, w_pad=2.5)
    fig.savefig(OUT / "detection_timeline.png", facecolor="white")
    plt.close(fig)


def storage(bench: dict) -> None:
    mb = bench["storage"]["mb"]
    order = ["JSON (raw)", "JSON + gzip", "Parquet + snappy", "Parquet + gzip", "Parquet + zstd", "ORC + zlib"]
    vals = [mb[k] for k in order]
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    colors = [ACCENT if k == "Parquet + snappy" else MUTED for k in order]
    bars = ax.barh(order[::-1], vals[::-1], color=colors[::-1], height=0.62)
    for b, v in zip(bars, vals[::-1]):
        ax.text(v + 6, b.get_y() + b.get_height() / 2, f"{v:.0f} MB", va="center", fontsize=10, color=INK)
    ax.set_xlabel(f'size of the same {bench["storage"]["rows"]:,} log records')
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(vals) * 1.15)
    ax.tick_params(axis="y", length=0)
    fig.savefig(OUT / "storage_formats.png", facecolor="white")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bench = json.loads(Path("results/benchmarks.json").read_text())
    storage(bench)
    detection_timeline(Path("data/lake/serving/endpoint_metrics.jsonl"), Path("data/ground_truth.json"),
                       Path("results/detection.json"))
    print("charts written to", OUT)


if __name__ == "__main__":
    main()
