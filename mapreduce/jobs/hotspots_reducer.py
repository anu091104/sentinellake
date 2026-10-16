#!/usr/bin/env python3
"""COMBINER and REDUCER - error hotspots job.

The same script does both jobs because the partial aggregates are "algebraic":
counts and sums add up, maxima take the max. That is exactly what makes a
combiner legal - it can pre-aggregate on the map side without changing the
answer, and it cuts the data shuffled across the network.

  combiner:  hotspots_reducer.py            (emits the mapper's format)
  reducer :  hotspots_reducer.py --final    (emits the report)

Final output: service, endpoint, requests, errors_5xx, error_rate, avg_ms, max_ms

Note: a p95 can NOT be computed this way - percentiles are not combinable.
That is why the streaming layer uses Spark's approximate percentile sketch.
"""
import sys


def emit(key, count, errors, lat_sum, lat_max, final):
    service, endpoint = key
    if final:
        sys.stdout.write(f"{service}\t{endpoint}\t{count}\t{errors}\t{errors / count:.5f}\t"
                         f"{lat_sum / count:.2f}\t{lat_max:.2f}\n")
    else:
        sys.stdout.write(f"{service}\t{endpoint}\t{count}\t{errors}\t{lat_sum:.3f}\t{lat_max:.2f}\n")


def main() -> None:
    final = "--final" in sys.argv
    current, count, errors, lat_sum, lat_max = None, 0, 0, 0.0, 0.0
    # Hadoop guarantees input arrives sorted by key, so one pass with a running total is enough
    for line in sys.stdin:
        service, endpoint, c, e, s, m = line.rstrip("\n").split("\t")
        key = (service, endpoint)
        if key != current:
            if current is not None:
                emit(current, count, errors, lat_sum, lat_max, final)
            current, count, errors, lat_sum, lat_max = key, 0, 0, 0.0, 0.0
        count += int(c)
        errors += int(e)
        lat_sum += float(s)
        lat_max = max(lat_max, float(m))
    if current is not None:
        emit(current, count, errors, lat_sum, lat_max, final)


if __name__ == "__main__":
    main()
