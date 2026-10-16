"""Incident detection on finalised one-minute endpoint windows.

The detector is deliberately plain Python (no Spark) so it is easy to unit test
and easy to explain:

1. Each (service, endpoint) keeps EWMA baselines of p95 latency, 5xx error
   rate and request volume. Latency has two: a fast one (~10 min memory) that
   catches sudden spikes and a slow one (~50 min memory) that catches slow drift.
2. A window is compared against its baseline with a z-score plus an absolute
   guard rail, so a quiet endpoint can't page anyone over noise.
3. Anomalous windows do NOT update the baseline - otherwise a long outage would
   slowly become "the new normal".
4. A signal must fire in two consecutive windows before an incident opens
   (critical error bursts open immediately). This removes one-minute blips.
5. Alerts are de-duplicated into incidents: one incident per
   (service, endpoint, type) stays open while the problem persists and resolves
   after three consecutive healthy windows.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

WARMUP_WINDOWS = 10      # windows of history needed before z-scores are trusted
ALPHA = 0.1              # fast EWMA smoothing (~10-minute memory)
SLOW_ALPHA = 0.02        # slow EWMA smoothing (~50-minute memory)
PENDING_WINDOWS = 2      # consecutive firing windows before an incident opens
RESOLVE_AFTER = 3        # healthy windows before an incident auto-resolves
MIN_REQUESTS = 20        # ignore windows with too little traffic to judge

IncidentType = Literal["ERROR_BURST", "LATENCY_SPIKE", "LATENCY_DRIFT", "TRAFFIC_DROP"]


@dataclass
class Ewma:
    alpha: float = ALPHA
    mean: float = 0.0
    var: float = 0.0
    n: int = 0

    def update(self, x: float) -> None:
        if self.n == 0:
            self.mean = x
        else:
            diff = x - self.mean
            incr = self.alpha * diff
            self.mean += incr
            self.var = (1 - self.alpha) * (self.var + diff * incr)
        self.n += 1

    @property
    def std(self) -> float:
        return math.sqrt(self.var)

    def z(self, x: float, floor: float) -> float:
        """z-score with a minimum std so a perfectly flat baseline can't explode."""
        return (x - self.mean) / max(self.std, floor)


@dataclass
class Baseline:
    p95: Ewma = field(default_factory=Ewma)
    p95_slow: Ewma = field(default_factory=lambda: Ewma(alpha=SLOW_ALPHA))
    err: Ewma = field(default_factory=Ewma)
    rpm: Ewma = field(default_factory=Ewma)

    @property
    def warm(self) -> bool:
        return self.p95.n >= WARMUP_WINDOWS


@dataclass
class Signal:
    type: IncidentType
    severity: Literal["warning", "critical"]
    value: float
    expected: float
    zscore: float
    reason: str


def evaluate(window: dict, base: Baseline) -> list[Signal]:
    """Return the problems visible in one window, given the endpoint's baseline."""
    signals: list[Signal] = []
    req, p95, err = window["requests"], window["p95_ms"], window["error_rate"]

    # 5xx errors: an absolute rule works from the first minute, z-score once warm
    if req >= MIN_REQUESTS and window["errors_5xx"] >= 5:
        z = base.err.z(err, floor=0.005) if base.warm else 0.0
        if err >= 0.05 or (base.warm and z >= 6 and err >= 0.02):
            signals.append(Signal(
                "ERROR_BURST", "critical" if err >= 0.10 else "warning", err, base.err.mean, z,
                f"5xx rate {err:.1%} vs normal {base.err.mean:.1%}"))

    if not base.warm:
        return signals

    if req >= MIN_REQUESTS:
        z = base.p95.z(p95, floor=0.05 * base.p95.mean)
        ratio = p95 / base.p95.mean if base.p95.mean else 1.0
        if z >= 5 and ratio >= 1.5:
            signals.append(Signal(
                "LATENCY_SPIKE", "critical" if ratio >= 3 else "warning", p95, base.p95.mean, z,
                f"p95 {p95:.0f} ms is {ratio:.1f}x the usual {base.p95.mean:.0f} ms"))
        else:
            # slow burn: each minute looks only slightly worse than the last, so the
            # fast baseline keeps up - but the slow baseline remembers the old normal
            slow_ratio = p95 / base.p95_slow.mean if base.p95_slow.mean else 1.0
            if slow_ratio >= 1.8:
                signals.append(Signal(
                    "LATENCY_DRIFT", "critical" if slow_ratio >= 3 else "warning", p95,
                    base.p95_slow.mean, base.p95_slow.z(p95, floor=0.05 * base.p95_slow.mean),
                    f"p95 has drifted to {p95:.0f} ms, {slow_ratio:.1f}x the {base.p95_slow.mean:.0f} ms "
                    f"of the last hour"))

    z = base.rpm.z(req, floor=0.05 * base.rpm.mean)
    if base.rpm.mean >= 50 and z <= -5 and req <= 0.5 * base.rpm.mean:
        signals.append(Signal(
            "TRAFFIC_DROP", "critical" if req <= 0.2 * base.rpm.mean else "warning",
            req, base.rpm.mean, z,
            f"{req} req/min vs usual {base.rpm.mean:.0f} - upstream may be failing silently"))
    return signals


def incident_id(service: str, endpoint: str, type_: str, opened_at: datetime) -> str:
    """Deterministic id, so a replayed micro-batch upserts instead of duplicating."""
    raw = f"{service}|{endpoint}|{type_}|{opened_at.isoformat()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


@dataclass
class Incident:
    id: str
    service: str
    endpoint: str
    type: IncidentType
    severity: str
    opened_at: datetime      # start of the first anomalous window
    detected_at: datetime    # when the alert could fire (end of the confirming window)
    last_seen: datetime
    reason: str
    peak_value: float
    expected: float
    windows: int = 1
    healthy_streak: int = 0
    status: Literal["open", "resolved"] = "open"
    resolved_at: datetime | None = None

    def to_doc(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "healthy_streak"}
        d["_id"] = d.pop("id")
        return d


class IncidentManager:
    """Keeps baselines and open incidents; turns windows into incident events."""

    def __init__(self) -> None:
        self.baselines: dict[tuple[str, str], Baseline] = {}
        self.open: dict[tuple[str, str, str], Incident] = {}
        # signals seen but not yet confirmed: key -> (consecutive windows, first window)
        self.pending: dict[tuple[str, str, str], tuple[int, datetime]] = {}

    def process(self, window: dict) -> list[tuple[str, Incident]]:
        """Feed one finalised window. Returns (action, incident) pairs where action
        is 'opened', 'updated' or 'resolved'."""
        key = (window["service"], window["endpoint"])
        base = self.baselines.setdefault(key, Baseline())
        ts: datetime = window["window_start"]
        signals = evaluate(window, base)
        firing = {s.type: s for s in signals}
        events: list[tuple[str, Incident]] = []

        for type_, sig in firing.items():
            ikey = (*key, type_)
            inc = self.open.get(ikey)
            if inc is None:
                streak, first = self.pending.get(ikey, (0, ts))
                streak += 1
                urgent = type_ == "ERROR_BURST" and sig.severity == "critical"
                if streak < PENDING_WINDOWS and not urgent:
                    self.pending[ikey] = (streak, first)
                    continue
                self.pending.pop(ikey, None)
                inc = Incident(incident_id(*key, type_, first), *key, type_, sig.severity,
                               first, ts + timedelta(minutes=1), ts,
                               sig.reason, sig.value, sig.expected, windows=streak)
                self.open[ikey] = inc
                events.append(("opened", inc))
            else:
                inc.last_seen, inc.windows, inc.healthy_streak = ts, inc.windows + 1, 0
                worse = sig.value < inc.peak_value if type_ == "TRAFFIC_DROP" else sig.value > inc.peak_value
                if worse:
                    inc.peak_value, inc.reason = sig.value, sig.reason
                if sig.severity == "critical":
                    inc.severity = "critical"
                events.append(("updated", inc))

        for ikey in [k for k in self.pending if k[:2] == key and k[2] not in firing]:
            del self.pending[ikey]
        for ikey in [k for k in self.open if k[:2] == key and k[2] not in firing]:
            inc = self.open[ikey]
            inc.healthy_streak += 1
            if inc.healthy_streak >= RESOLVE_AFTER:
                inc.status, inc.resolved_at = "resolved", ts
                del self.open[ikey]
                events.append(("resolved", inc))

        # only learn from windows that look normal
        if not signals and window["requests"] > 0:
            base.p95.update(window["p95_ms"])
            base.p95_slow.update(window["p95_ms"])
            base.err.update(window["error_rate"])
            base.rpm.update(window["requests"])
        return events
