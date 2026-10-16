-- SentinelLake - Cassandra schema (serving layer for time-series metrics)
-- Applied automatically by the cassandra-init container.

CREATE KEYSPACE IF NOT EXISTS sentinel
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
-- (production: NetworkTopologyStrategy with replication_factor 3 per datacenter)

USE sentinel;

-- One row per endpoint per minute.
-- Cassandra tables are designed around the query, not the entity:
--   "give me the last N minutes of service X"  ->  partition key (service, day)
--   newest first                               ->  clustering by window_start DESC
-- Bucketing by day keeps every partition bounded (~13 endpoints x 1440 minutes).
CREATE TABLE IF NOT EXISTS endpoint_metrics (
  service       text,
  day           date,
  window_start  timestamp,
  endpoint      text,
  requests      int,
  errors_5xx    int,
  errors_4xx    int,
  error_rate    double,
  p50_ms        double,
  p95_ms        double,
  p99_ms        double,
  avg_bytes     double,
  PRIMARY KEY ((service, day), window_start, endpoint)
) WITH CLUSTERING ORDER BY (window_start DESC, endpoint ASC)
  AND default_time_to_live = 604800      -- TTL: rows expire automatically after 7 days
  AND compaction = {'class': 'TimeWindowCompactionStrategy',
                    'compaction_window_unit': 'HOURS', 'compaction_window_size': 6};

-- Running daily totals using Cassandra's distributed COUNTER type.
-- Counters can only be incremented/decremented, and live in their own table.
CREATE TABLE IF NOT EXISTS service_daily_counters (
  service     text,
  day         date,
  requests    counter,
  errors_5xx  counter,
  PRIMARY KEY ((service), day)
) WITH CLUSTERING ORDER BY (day DESC);
