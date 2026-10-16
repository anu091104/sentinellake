"""Run the Hadoop Streaming scripts locally, reproducing MapReduce's data flow.

This is a teaching / testing harness, not a replacement for Hadoop. It runs the
exact same scripts that run_hadoop.sh ships to the cluster and makes every phase
visible:

  split -> map -> (sort + combine per split) -> partition -> shuffle/sort -> reduce

  python -m mapreduce.local_runner hotspots --input data/landing --out results/mr --reducers 3

Each input file is treated as one split (one map task). The partitioner hashes
only the first key field (like KeyFieldBasedPartitioner -k1,1), so every endpoint
of a service lands on the same reducer.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import zlib
from pathlib import Path

JOBS = Path(__file__).parent / "jobs"
PY = sys.executable


def run(script: str, data: bytes, *args: str, env: dict | None = None) -> bytes:
    out = subprocess.run([PY, str(JOBS / script), *args], input=data, capture_output=True,
                         check=True, env=env).stdout
    return out.replace(b"\r\n", b"\n")   # Windows text-mode stdout writes CRLF; Hadoop is LF


def sort_lines(data: bytes, key_fields: int, numeric_desc: bool = False) -> bytes:
    lines = [ln for ln in data.split(b"\n") if ln]
    if numeric_desc:
        lines.sort(key=lambda ln: -float(ln.split(b"\t", 1)[0]))
    else:
        lines.sort(key=lambda ln: ln.split(b"\t")[:key_fields])
    return b"\n".join(lines) + (b"\n" if lines else b"")


def partition(data: bytes, reducers: int) -> list[bytes]:
    parts: list[list[bytes]] = [[] for _ in range(reducers)]
    for ln in data.split(b"\n"):
        if ln:
            parts[zlib.crc32(ln.split(b"\t", 1)[0]) % reducers].append(ln)
    return [b"\n".join(p) + (b"\n" if p else b"") for p in parts]


def hotspots(inputs: list[Path], out: Path, reducers: int, use_combiner: bool = True) -> dict:
    stats = {"map_tasks": len(inputs), "reducers": reducers, "combiner": use_combiner}
    t0 = time.perf_counter()
    map_outputs, map_records, shuffled = [], 0, 0
    for split in inputs:
        mapped = run("hotspots_mapper.py", split.read_bytes())
        map_records += mapped.count(b"\n")
        if use_combiner:
            mapped = run("hotspots_reducer.py", sort_lines(mapped, 2))
        shuffled += len(mapped)
        map_outputs.append(mapped)
    stats["map_output_records"] = map_records
    stats["shuffle_bytes"] = shuffled

    out.mkdir(parents=True, exist_ok=True)
    buckets = partition(b"".join(map_outputs), reducers)
    for i, bucket in enumerate(buckets):
        result = run("hotspots_reducer.py", sort_lines(bucket, 2), "--final")
        (out / f"part-{i:05d}").write_bytes(result)
    stats["seconds"] = round(time.perf_counter() - t0, 2)
    return stats


def rank(hotspots_dir: Path, out: Path, by: str = "error_rate") -> list[str]:
    data = b"".join(p.read_bytes() for p in sorted(hotspots_dir.glob("part-*")))
    import os
    mapped = run("rank_mapper.py", data, env={**os.environ, "RANK_BY": by})
    ranked = sort_lines(mapped, 1, numeric_desc=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "part-00000").write_bytes(ranked)
    return ranked.decode().splitlines()


def search(inputs: list[Path], out: Path, flt: str) -> int:
    import os
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for i, split in enumerate(inputs):  # map-only: one output file per map task
        res = run("search_mapper.py", split.read_bytes(), env={**os.environ, "FILTER": flt})
        (out / f"part-m-{i:05d}").write_bytes(res)
        total += res.count(b"\n")
    return total


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("job", choices=["hotspots", "rank", "search", "all"])
    p.add_argument("--input", default="data/landing")
    p.add_argument("--out", default="results/mapreduce")
    p.add_argument("--reducers", type=int, default=3)
    p.add_argument("--filter", default="service=payments,status>=500")
    p.add_argument("--no-combiner", action="store_true")
    a = p.parse_args()

    inputs = sorted(Path(a.input).glob("*.jsonl"))
    out = Path(a.out)
    if a.job in ("hotspots", "all"):
        print(json.dumps(hotspots(inputs, out / "hotspots", a.reducers, not a.no_combiner), indent=2))
    if a.job in ("rank", "all"):
        for line in rank(out / "hotspots", out / "ranked")[:10]:
            print(line)
    if a.job in ("search", "all"):
        print(f"search '{a.filter}': {search(inputs, out / 'search', a.filter)} matches")


if __name__ == "__main__":
    main()
