# Demo dataset

Output of one laptop-mode run (`.\sl demo`): 6 simulated hours, 2.37 million requests, 4 injected failures.

- `serving/endpoint_metrics.jsonl` - per-endpoint, per-minute metrics written by the Spark job
- `serving/incidents.jsonl` - incident events written by the detector
- `lake.json` - sizes of the lake zones from that run (the raw lake itself is ~600 MB and not committed)

The hosted dashboard (see `render.yaml`) serves these files. To refresh them after a new run:
copy `data/lake/serving/*.jsonl` here.
