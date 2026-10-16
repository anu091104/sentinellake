-- SentinelLake - a custom function in Hive using TRANSFORM (streaming UDF)
-- Hive pipes each row to the Python script's stdin as tab-separated text and
-- reads the script's stdout back as new columns.
USE sentinel;

ADD FILE /opt/sentinellake/hive/udf/latency_band.py;

-- Classify every request into a user-experience band, then count per service.
SELECT service, band, COUNT(*) AS requests
FROM (
  SELECT TRANSFORM (service, latency_ms, status)
         USING 'python3 latency_band.py'
         AS (service STRING, band STRING)
  FROM api_logs
  WHERE dt = '2026-10-12'
) banded
GROUP BY service, band
ORDER BY service, band;

-- File formats: same rows, different storage. Compare the "totalSize" values.
DESCRIBE FORMATTED api_logs_orc;
