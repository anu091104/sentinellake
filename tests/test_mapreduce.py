import json
import subprocess
import sys
import zlib
from collections import defaultdict
from pathlib import Path

from mapreduce import local_runner as mr

JOBS = Path(mr.__file__).parent / "jobs"


def expected_hotspots(events):
    agg = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for e in events:
        a = agg[(e["service"], f'{e["method"]} {e["route"]}')]
        a[0] += 1
        a[1] += e["status"] >= 500
        a[2] += e["latency_ms"]
        a[3] = max(a[3], e["latency_ms"])
    return agg


def read_parts(d: Path):
    rows = {}
    for p in sorted(d.glob("part-*")):
        for line in p.read_text().splitlines():
            s, ep, req, err, rate, avg, mx = line.split("\t")
            rows[(s, ep)] = (int(req), int(err), float(avg), float(mx), p.name)
    return rows


def test_hotspots_matches_direct_computation(landing_dir, sample_events, tmp_path):
    stats = mr.hotspots(sorted(landing_dir.glob("*.jsonl")), tmp_path / "h", reducers=3)
    got = read_parts(tmp_path / "h")
    want = expected_hotspots(sample_events)
    assert set(got) == set(want)
    for k, (req, err, s, mx) in want.items():
        assert got[k][0] == req and got[k][1] == err
        assert abs(got[k][2] - s / req) < 0.02
        assert abs(got[k][3] - mx) < 0.01
    assert stats["map_output_records"] == len(sample_events)


def test_combiner_changes_traffic_not_answer(landing_dir, tmp_path):
    files = sorted(landing_dir.glob("*.jsonl"))
    with_c = mr.hotspots(files, tmp_path / "a", 3, use_combiner=True)
    without = mr.hotspots(files, tmp_path / "b", 3, use_combiner=False)
    a, b = read_parts(tmp_path / "a"), read_parts(tmp_path / "b")
    assert a.keys() == b.keys()
    for k in a:
        assert a[k][:2] == b[k][:2] and a[k][3] == b[k][3]
        assert abs(a[k][2] - b[k][2]) <= 0.011          # last-digit rounding only
    assert with_c["shuffle_bytes"] < without["shuffle_bytes"] / 50


def test_partitioner_keeps_each_service_on_one_reducer(landing_dir, tmp_path):
    mr.hotspots(sorted(landing_dir.glob("*.jsonl")), tmp_path / "h", reducers=3)
    where = defaultdict(set)
    for (service, _), v in read_parts(tmp_path / "h").items():
        where[service].add(v[4])
    assert all(len(parts) == 1 for parts in where.values())
    for service, parts in where.items():
        assert parts == {f"part-{zlib.crc32(service.encode()) % 3:05d}"}


def test_rank_is_sorted_descending(landing_dir, tmp_path):
    mr.hotspots(sorted(landing_dir.glob("*.jsonl")), tmp_path / "h", reducers=2)
    lines = mr.rank(tmp_path / "h", tmp_path / "r", by="avg_ms")
    keys = [float(line.split("\t")[0]) for line in lines]
    assert keys == sorted(keys, reverse=True)


def test_search_filters_exactly(landing_dir, sample_events, tmp_path):
    n = mr.search(sorted(landing_dir.glob("*.jsonl")), tmp_path / "s", "service=payments,status>=500")
    assert n == sum(1 for e in sample_events if e["service"] == "payments" and e["status"] >= 500)
    trace = sample_events[123]["trace_id"]
    assert mr.search(sorted(landing_dir.glob("*.jsonl")), tmp_path / "t", f"trace_id={trace}") >= 1


def test_mapper_reports_malformed_records_as_counter():
    bad = b'{"service":"x"}\nnot json\n'
    res = subprocess.run([sys.executable, str(JOBS / "hotspots_mapper.py")], input=bad, capture_output=True)
    assert res.stdout == b""
    assert res.stderr.count(b"reporter:counter:SentinelLake,MalformedRecords,1") == 2


def test_hive_udf_bands():
    script = Path(__file__).resolve().parents[1] / "hive" / "udf" / "latency_band.py"
    rows = "auth\t50\t200\nauth\t500\t200\nauth\t50\t503\nauth\t5000\t200\n"
    out = subprocess.run([sys.executable, str(script)], input=rows.encode(), capture_output=True,
                         check=True).stdout.decode().split()
    assert out[1::2] == ["satisfied", "tolerating", "frustrated", "frustrated"]
