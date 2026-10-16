#!/usr/bin/env python3
"""MAPPER - error hotspots job.

Input : raw JSON access logs, one per line (the lake's raw zone)
Output: service <TAB> endpoint <TAB> count <TAB> errors_5xx <TAB> latency_sum <TAB> latency_max

The first two fields are the key (stream.num.map.output.key.fields=2).
Malformed lines are skipped and counted with a Hadoop counter instead of
failing the task.
"""
import json
import sys


def main() -> None:
    for line in sys.stdin:
        try:
            r = json.loads(line)
            service, endpoint = r["service"], f'{r["method"]} {r["route"]}'
            status, latency = int(r["status"]), float(r["latency_ms"])
        except (ValueError, KeyError, TypeError):
            sys.stderr.write("reporter:counter:SentinelLake,MalformedRecords,1\n")
            continue
        sys.stdout.write(f"{service}\t{endpoint}\t1\t{int(status >= 500)}\t{latency:.2f}\t{latency:.2f}\n")


if __name__ == "__main__":
    main()
