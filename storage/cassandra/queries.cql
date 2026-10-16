-- SentinelLake - Cassandra CQL walkthrough (CRUD, collections, counters, TTL, system tables)
-- Run: docker compose exec cassandra cqlsh -f /opt/sentinellake/storage/cassandra/queries.cql
USE sentinel;

-- READ: latest 10 windows for the payments service today (hits exactly one partition)
SELECT window_start, endpoint, requests, error_rate, p95_ms
FROM endpoint_metrics
WHERE service = 'payments' AND day = '2026-10-12'
LIMIT 10;

-- READ: a time range inside the partition (range on the clustering column)
SELECT window_start, endpoint, p95_ms
FROM endpoint_metrics
WHERE service = 'search' AND day = '2026-10-12'
  AND window_start >= '2026-10-12 09:00:00+0000' AND window_start < '2026-10-12 09:20:00+0000';

-- This would FAIL without ALLOW FILTERING: endpoint is not part of the partition key,
-- so Cassandra would have to scan every node. That is the point of query-first design.
-- SELECT * FROM endpoint_metrics WHERE endpoint = 'GET /v1/search';

-- COUNTERS
SELECT service, day, requests, errors_5xx FROM service_daily_counters WHERE service = 'payments';

-- TTL: how many seconds this row has left before it disappears
SELECT endpoint, TTL(p95_ms) AS seconds_left, WRITETIME(p95_ms) AS written_us
FROM endpoint_metrics WHERE service = 'auth' AND day = '2026-10-12' LIMIT 3;

-- CREATE / UPDATE / DELETE on a small table that uses COLLECTIONS (set, map)
CREATE TABLE IF NOT EXISTS service_owners (
  service     text PRIMARY KEY,
  team        text,
  oncall      set<text>,
  slo_targets map<text, double>
);

INSERT INTO service_owners (service, team, oncall, slo_targets)
VALUES ('payments', 'payments-platform', {'riya@corp.example'}, {'availability': 99.9, 'p95_ms': 800});

UPDATE service_owners SET oncall = oncall + {'arjun@corp.example'} WHERE service = 'payments';
UPDATE service_owners SET slo_targets['p95_ms'] = 600 WHERE service = 'payments';
-- write with a per-row TTL (a temporary on-call override for 24 hours)
INSERT INTO service_owners (service, team) VALUES ('search', 'discovery') USING TTL 86400;

SELECT * FROM service_owners;

-- ALTER: add a column without downtime or rewriting existing rows
ALTER TABLE service_owners ADD runbook_url text;
UPDATE service_owners SET runbook_url = 'https://runbooks.example/payments' WHERE service = 'payments';

DELETE oncall FROM service_owners WHERE service = 'search';

-- SYSTEM TABLES: Cassandra describes itself in ordinary tables
SELECT keyspace_name, table_name, default_time_to_live
FROM system_schema.tables WHERE keyspace_name = 'sentinel';
SELECT cluster_name, release_version, data_center FROM system.local;

-- EXPORT / IMPORT with cqlsh COPY
COPY sentinel.endpoint_metrics (service, day, window_start, endpoint, requests, error_rate, p95_ms)
  TO '/tmp/endpoint_metrics.csv' WITH HEADER = TRUE;
COPY sentinel.service_owners TO '/tmp/service_owners.csv' WITH HEADER = TRUE;
TRUNCATE service_owners;
COPY sentinel.service_owners FROM '/tmp/service_owners.csv' WITH HEADER = TRUE;
