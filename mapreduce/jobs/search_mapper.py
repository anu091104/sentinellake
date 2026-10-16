#!/usr/bin/env python3
"""MAPPER - log search job (map-only, zero reducers).

Finds every log line matching a filter - for example all requests of one trace,
or every 5xx from the payments service in an hour. With no reducer, each mapper
writes its matches straight to HDFS, so the search scales with the cluster.

FILTER is passed with -cmdenv, as comma-separated conditions:
  FILTER="trace_id=3f9a1c22b7d04e10"
  FILTER="service=payments,status>=500"
Supported operators: =  !=  >=  <=  >  <
"""
import json
import os
import re
import sys

COND = re.compile(r"^\s*(\w+)\s*(>=|<=|!=|=|>|<)\s*(.+?)\s*$")
OPS = {
    "=": lambda a, b: a == b, "!=": lambda a, b: a != b,
    ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b, "<": lambda a, b: a < b,
}


def parse(expr: str):
    conds = []
    for part in filter(None, expr.split(",")):
        m = COND.match(part)
        if not m:
            raise SystemExit(f"bad condition: {part!r}")
        field, op, raw = m.groups()
        try:
            value = float(raw)
        except ValueError:
            value = raw
        conds.append((field, OPS[op], value))
    return conds


def matches(record: dict, conds) -> bool:
    for field, op, value in conds:
        actual = record.get(field)
        if actual is None:
            return False
        if isinstance(value, float):
            try:
                actual = float(actual)
            except (TypeError, ValueError):
                return False
        elif not isinstance(actual, str):
            actual = str(actual)
        if not op(actual, value):
            return False
    return True


def main() -> None:
    conds = parse(os.environ.get("FILTER", ""))
    for line in sys.stdin:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if matches(record, conds):
            sys.stdout.write(line if line.endswith("\n") else line + "\n")


if __name__ == "__main__":
    main()
