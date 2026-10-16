# Design notes

Why SentinelLake is built the way it is, and what each choice costs.

## 1. The problem

A company running microservices needs two different things from the same logs:

- **On-call engineers** need to know *now* that payments started failing, ideally before customers complain. They care about the last few minutes, and speed matters more than completeness.
- **Analysts and managers** need to know *how reliable were we last week*: SLO reports, error budgets, the slowest endpoints. They care about all history, and completeness matters more than speed.

One storage system is bad at one of these. So the data takes two paths from the same stream.

## 2. Lambda architecture: a batch layer and a speed layer

| | Batch layer | Speed layer |
|---|---|---|
| Stores | HDFS (raw JSON + curated Parquet) | Cassandra (minute metrics) + MongoDB (incidents) |
| Holds | everything, forever | last 7 days (TTL) |
| Answers | "p95 of every endpoint last month" | "last 60 minutes of payments" |
| Engines | MapReduce, Hive (on YARN) | Spark Structured Streaming, FastAPI |
| Freshness | minutes to hours | ~1–3 minutes |

Both layers are fed by the same Spark job, so they never disagree about what was received.

## 3. Ingestion: Kafka keyed by service

Kafka is a durable, replayable buffer between producers and Spark. If Spark is down for 10 minutes, nothing is lost; it resumes from its checkpointed offsets.

Messages are **keyed by service name**. Kafka's partitioner hashes the key, so every event of `payments` lands in the same partition and keeps its order. This is the same idea as the MapReduce partitioner later in the pipeline.

KRaft mode (Kafka's built-in Raft consensus) is used instead of ZooKeeper; ZooKeeper support was removed in Kafka 4.0.

## 4. Lake zones

| Zone | Format | Why |
|---|---|---|
| raw | JSON text, partitioned by `dt` | the exact bytes received; can always be reprocessed; MapReduce and Hive's JSON SerDe read it |
| curated | Parquet (snappy), partitioned by `dt` and `hr` | typed, columnar, ~7× smaller; queries read only the columns and hours they need |
| quarantine | JSON | rows that failed validation are kept for debugging instead of crashing the job or vanishing |

Snappy is Spark's default Parquet codec because it decompresses fast. zstd would make the curated zone about 40% smaller (47 MB vs 77 MB) at some CPU cost, which is the right trade for data older than a few days.

## 5. Streaming: event time, windows and the watermark

Every log carries its own timestamp (event time). Spark groups events into **1-minute tumbling windows** per (service, endpoint) by event time, not by arrival time, so a late-arriving event still counts in the right minute.

The **watermark** (2 minutes) tells Spark how long to wait for late events. Once the watermark passes the end of a window, the window is final and is emitted exactly once (append mode). The detector therefore never sees a half-filled minute, which would look like a traffic drop. The price is latency: a minute is reported up to ~3 minutes after it starts.

p95/p99 use `percentile_approx`, a sketch with bounded memory. An exact percentile needs every value of the window in memory, and percentiles can't be merged from partial results (see §8).

## 6. The detector

Per (service, endpoint), plain Python in the Spark driver:

1. **EWMA baselines** (exponentially weighted moving average) of p95 latency, 5xx rate and request volume. A new minute nudges the average by 10% (fast baseline) or 2% (slow baseline).
2. **z-score** = how many standard deviations this minute is from the baseline, plus an **absolute guard** (e.g. latency must also be ≥1.5× normal) so a very stable endpoint can't page someone over a 3 ms wobble.
3. **Warm-up**: no z-score rules for the first 10 minutes of an endpoint's life. The 5xx rule (≥5% errors) works from minute one.
4. **Learn only from healthy minutes.** During an outage the baseline is frozen.
5. **Confirmation**: a signal must fire in 2 consecutive minutes before an incident opens. A critical error burst (≥10% 5xx) skips this.
6. **De-duplication and auto-resolve**: one open incident per (service, endpoint, type); it closes after 3 healthy minutes.

| Incident type | Fires when | Catches |
|---|---|---|
| ERROR_BURST | 5xx rate ≥5%, or z ≥ 6 and ≥2% | outages, bad deploys |
| LATENCY_SPIKE | p95 z ≥ 5 vs fast baseline and ≥1.5× | sudden slowdowns |
| LATENCY_DRIFT | p95 ≥1.8× the slow baseline | slow degradation (connection-pool exhaustion, memory leaks) |
| TRAFFIC_DROP | volume z ≤ −5 and ≤50% of normal | silent failures upstream: nothing errors, requests just stop arriving |

The drift rule exists because the first version missed the auth scenario entirely: latency rose a little each minute, the fast baseline kept up, and no single minute looked abnormal. The slow baseline remembers the last hour.

**Measured**: 4/4 detected with 0 false positives on the main replay; 20/20 with 0 false positives across 5 seeds. Without the 2-window confirmation, the low-traffic refund endpoint (~30 requests/minute) produced 2 false positives on the same data.

## 7. Serving stores: why Cassandra and MongoDB

**Cassandra for metrics.** The access pattern is fixed and write-heavy: "every minute, write 13 rows" and "give me service X between t1 and t2". Cassandra is designed around the query: partition key `(service, day)` puts one service-day on one node; clustering key `window_start DESC` stores rows already sorted newest-first, so the dashboard's query is one sequential read. Day bucketing keeps partitions bounded. TTL deletes old rows automatically, and TimeWindowCompactionStrategy drops whole expired files instead of rewriting them.

**MongoDB for incidents.** Incidents are few, nested (a timeline array) and queried in varied ways (by status, by service, aggregated for MTTR). That is a document workload. A JSON-schema validator still rejects malformed documents.

**CAP and BASE.** Under a network partition Cassandra stays available and may serve slightly stale data (AP; consistency is tunable per query). MongoDB elects a single primary and refuses writes on the minority side (CP). For live metrics, a slightly stale chart is better than no chart; for incidents, a lost or duplicated update would be confusing. Both are BASE systems at heart: basically available, soft state, eventually consistent.

## 8. Exactly-once, at-least-once, and idempotency

Spark's checkpoint guarantees each micro-batch is processed at least once; after a crash the last batch may be replayed. So every write must be safe to repeat:

- Cassandra `INSERT` on the same primary key overwrites: **idempotent**.
- MongoDB incident ids are a hash of (service, endpoint, type, first minute): replaying upserts the same document. **Idempotent**.
- Parquet/text file sinks use Spark's `_spark_metadata` commit log: **exactly-once**.
- Cassandra **counters are not idempotent**. A replayed batch adds twice. They are kept deliberately, as a working example of the trade-off, and the minute table remains the source of truth.

## 9. MapReduce design

**Combiner.** Counts, sums and maxima are *algebraic*: partial results combine into the full result. So the reducer script can also run as the combiner on each mapper's output. Measured: each mapper's ~33,000 records shrink to about 13 lines (one per endpoint), and the data shuffled falls from 97 MB to 46 KB.

Percentiles are *holistic*: the p95 of two halves is not the p95 of the whole. That is why the MapReduce job reports average and maximum, and the streaming layer uses an approximate percentile sketch.

**Partitioner.** `KeyFieldBasedPartitioner -k1,1` hashes only the service field, so all endpoints of a service go to the same reducer and land in the same output file.

**Sorting.** The ranking job puts the metric first so it becomes the key, and `KeyFieldBasedComparator -k1,1nr` sorts it numerically, descending. One reducer gives one globally sorted file.

**Searching.** A map-only job (`reduces=0`): each mapper filters its split and writes straight to HDFS. No shuffle, so it scales linearly.

**Compression.** Map output is compressed with Snappy (fast, for the shuffle) and final output with Gzip (smaller, for storage).

## 10. What I would change for production

- Persist detector baselines (Cassandra) so a restart doesn't need a 10-minute warm-up.
- Replication factor 3 everywhere; a standalone Hive metastore on PostgreSQL instead of embedded Derby.
- Alert routing (Slack, PagerDuty) on `opened` events, with severity-based escalation.
- Schema registry (Avro or Protobuf) on the Kafka topic so producers can't break the parser.
- Compact the curated zone daily (many small Parquet files from streaming) and move cold days to zstd.
