-- SentinelLake - reliability analytics in HiveQL
-- Run: docker compose exec hive beeline -u jdbc:hive2://localhost:10000 -f /opt/sentinellake/hive/02_analytics.hql
-- Every query below is also executed by tests/test_hive_queries.py (on Spark SQL) so it is known to work.
USE sentinel;

-- Q1. SLO report per service and hour.
-- SLO (Service Level Objective) here: 99% of requests succeed and p95 latency under 800 ms.
SELECT service,
       dt,
       hr,
       COUNT(*)                                                     AS requests,
       ROUND(100 * AVG(CASE WHEN status < 500 THEN 1 ELSE 0 END), 3) AS availability_pct,
       ROUND(PERCENTILE_APPROX(latency_ms, 0.95), 1)                AS p95_ms,
       CASE WHEN AVG(CASE WHEN status < 500 THEN 1 ELSE 0 END) >= 0.99
             AND PERCENTILE_APPROX(latency_ms, 0.95) < 800
            THEN 'MET' ELSE 'BREACHED' END                          AS slo
FROM api_logs
GROUP BY service, dt, hr
ORDER BY service, dt, hr;

-- Q2. Error budget for the day. A 99% availability target allows 1% of requests
-- to fail; this shows how much of that allowance each service has spent.
SELECT service,
       COUNT(*)                                                       AS requests,
       SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END)                 AS failed,
       ROUND(COUNT(*) * 0.01)                                         AS budget,
       ROUND(100 * SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) / (COUNT(*) * 0.01), 1)
                                                                      AS budget_used_pct
FROM api_logs
GROUP BY service
ORDER BY budget_used_pct DESC;

-- Q3. Slowest endpoints, ranked inside each service with a window function.
SELECT * FROM (
  SELECT service,
         endpoint,
         COUNT(*)                                      AS requests,
         ROUND(PERCENTILE_APPROX(latency_ms, 0.95), 1) AS p95_ms,
         RANK() OVER (PARTITION BY service ORDER BY PERCENTILE_APPROX(latency_ms, 0.95) DESC) AS rnk
  FROM api_logs
  GROUP BY service, endpoint
) t
WHERE rnk <= 2
ORDER BY p95_ms DESC;

-- Q4. Worst 5-minute periods for 5xx errors (what an on-call engineer looks at first).
SELECT service,
       endpoint,
       FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(event_time) / 300) * 300) AS bucket_5min,
       COUNT(*)                                                     AS requests,
       SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END)               AS errors,
       ROUND(100 * AVG(CASE WHEN status >= 500 THEN 1 ELSE 0 END), 2) AS error_pct
FROM api_logs
GROUP BY service, endpoint, FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(event_time) / 300) * 300)
HAVING COUNT(*) >= 100
ORDER BY error_pct DESC
LIMIT 10;

-- Q5. Regional traffic and latency mix.
SELECT region,
       COUNT(*)                                               AS requests,
       ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)       AS share_pct,
       ROUND(PERCENTILE_APPROX(latency_ms, 0.5), 1)           AS p50_ms,
       ROUND(PERCENTILE_APPROX(latency_ms, 0.95), 1)          AS p95_ms
FROM api_logs
GROUP BY region
ORDER BY requests DESC;

-- Q6. Partition pruning: this reads only the dt/hr folder it needs.
--     Compare with EXPLAIN on a query without the WHERE clause.
SELECT status_class, COUNT(*) AS requests
FROM api_logs
WHERE dt = '2026-10-12' AND hr = 7
GROUP BY status_class
ORDER BY status_class;
