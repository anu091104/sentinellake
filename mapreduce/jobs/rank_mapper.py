#!/usr/bin/env python3
"""MAPPER - ranking job (sorting).

Input : output of the hotspots job
Output: <metric> <TAB> service <TAB> endpoint <TAB> requests <TAB> error_rate <TAB> avg_ms

Putting the metric first makes it the key, so Hadoop's shuffle does the sorting.
With KeyFieldBasedComparator (-k1,1nr) the key is compared numerically and in
reverse; with a single reducer the result is one globally sorted file.

RANK_BY=error_rate (default) or avg_ms - passed with -cmdenv.
"""
import os
import sys

COLUMNS = {"error_rate": 4, "avg_ms": 5}


def main() -> None:
    col = COLUMNS[os.environ.get("RANK_BY", "error_rate")]
    for line in sys.stdin:
        f = line.rstrip("\n").split("\t")
        if len(f) != 7:
            continue
        sys.stdout.write(f"{f[col]}\t{f[0]}\t{f[1]}\t{f[2]}\t{f[4]}\t{f[5]}\n")


if __name__ == "__main__":
    main()
