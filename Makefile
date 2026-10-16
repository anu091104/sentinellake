PY      ?= python3
DT      ?= $(shell date -u +%F)
COMPOSE  = docker compose

.PHONY: help setup test demo replay stream evaluate bench charts serve hive-local \
        up down batch-up mapreduce hive cassandra-demo mongo-demo logs clean

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

# ---------- laptop mode (no Docker) ----------
setup:           ## create .venv and install Python dependencies (needs Java 17 for Spark)
	$(PY) -m venv .venv && .venv/bin/pip install -r requirements.txt

test:            ## run the test suite
	.venv/bin/python -m pytest

replay:          ## simulate 6 hours of API traffic into data/landing
	.venv/bin/python -m sentinellake.generator replay --hours 6 --out data/landing --corrupt

stream:          ## run the Spark streaming job over data/landing (local files, local serving store)
	rm -rf data/lake && .venv/bin/python -m sentinellake.streaming.job --source files \
	  --input data/landing --lake data/lake --serving local --once --files-per-trigger 6

evaluate:        ## score the detector against the injected failures
	.venv/bin/python -m benchmarks.evaluate_detection
	.venv/bin/python -m benchmarks.detection_robustness

bench:           ## storage / query / partition / combiner benchmarks -> results/benchmarks.json
	.venv/bin/python -m benchmarks.run_benchmarks

charts:          ## redraw figures in docs/img from results/
	.venv/bin/python -m benchmarks.make_charts

hive-local:      ## run the HiveQL reports on Spark SQL over the local lake
	.venv/bin/python -m hive.run_local

serve:           ## dashboard on http://localhost:8000 using the local serving store
	SENTINEL_BACKEND=local .venv/bin/uvicorn api.main:app --port 8000

demo: replay stream evaluate serve   ## the whole pipeline end to end, then open the dashboard

# ---------- cluster mode (Docker) ----------
up:              ## start the streaming stack: Kafka, HDFS, Spark, Cassandra, MongoDB, API
	$(COMPOSE) up -d --build

batch-up:        ## add YARN, MapReduce history server and Hive
	$(COMPOSE) --profile batch up -d --build

mapreduce:       ## run the 3 MapReduce jobs on YARN for day DT (default: today UTC)
	$(COMPOSE) exec namenode bash /opt/sentinellake/mapreduce/run_hadoop.sh $(DT)

hive:            ## create Hive tables and run the analytics queries
	$(COMPOSE) exec hive beeline -u jdbc:hive2://localhost:10000 -f /opt/sentinellake/hive/01_tables.hql
	$(COMPOSE) exec hive beeline -u jdbc:hive2://localhost:10000 -f /opt/sentinellake/hive/02_analytics.hql

cassandra-demo:  ## CQL walkthrough: queries, counters, TTL, collections, COPY
	$(COMPOSE) exec cassandra cqlsh -f /opt/sentinellake/storage/cassandra/queries.cql

mongo-demo:      ## MongoDB walkthrough: find, aggregate, arrays, cursors, indexes, mapReduce
	$(COMPOSE) exec mongo mongosh --quiet /opt/sentinellake/storage/mongo/queries.js

logs:            ## follow the streaming job's log (incidents show up here)
	$(COMPOSE) logs -f stream

down:            ## stop everything (data volumes are kept)
	$(COMPOSE) --profile batch down

clean:           ## stop everything and delete all data
	$(COMPOSE) --profile batch down -v; rm -rf data results/_work
