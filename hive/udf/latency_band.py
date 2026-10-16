#!/usr/bin/env python3
"""Hive TRANSFORM script: (service, latency_ms, status) -> (service, band).

Bands follow the Apdex idea used by APM tools: a request is "satisfied" if it is
fast, "tolerating" if slow but usable, and "frustrated" if very slow or failed.
"""
import sys

SATISFIED_MS = 300
TOLERATING_MS = 1200


def band(latency_ms: float, status: int) -> str:
    if status >= 500 or latency_ms > TOLERATING_MS:
        return "frustrated"
    if latency_ms > SATISFIED_MS:
        return "tolerating"
    return "satisfied"


for line in sys.stdin:
    service, latency, status = line.rstrip("\n").split("\t")
    try:
        print(f"{service}\t{band(float(latency), int(status))}")
    except ValueError:
        print(f"{service}\tunknown")
