-- SentinelLake - Hive tables over the HDFS lake
-- Run: docker compose exec hive beeline -u jdbc:hive2://localhost:10000 -f /opt/sentinellake/hive/01_tables.hql

CREATE DATABASE IF NOT EXISTS sentinel;
USE sentinel;

-- 1) Raw zone: the JSON text exactly as it arrived. A SerDe (Serializer/Deserializer)
--    tells Hive how to turn each line into columns - here, by parsing JSON.
--    EXTERNAL = Hive only stores the schema; dropping the table never deletes the data.
CREATE EXTERNAL TABLE IF NOT EXISTS api_logs_raw (
  ts          STRING,
  trace_id    STRING,
  service     STRING,
  method      STRING,
  route       STRING,
  status      INT,
  latency_ms  DOUBLE,
  bytes       BIGINT,
  region      STRING,
  instance    STRING,
  client_id   STRING
)
PARTITIONED BY (dt STRING)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.JsonSerDe'
STORED AS TEXTFILE
LOCATION '/sentinellake/raw/api_logs';

-- 2) Curated zone: typed Parquet written by Spark. Columnar + compressed, so a query
--    reads only the columns it needs. Partitioned by day and hour, so a query on
--    one hour skips every other directory (partition pruning).
CREATE EXTERNAL TABLE IF NOT EXISTS api_logs (
  event_time    TIMESTAMP,
  trace_id      STRING,
  service       STRING,
  endpoint      STRING,
  method        STRING,
  route         STRING,
  status        INT,
  status_class  STRING,
  latency_ms    DOUBLE,
  bytes         BIGINT,
  region        STRING,
  instance      STRING,
  client_id     STRING
)
PARTITIONED BY (dt STRING, hr INT)
STORED AS PARQUET
LOCATION '/sentinellake/curated/api_logs';

-- Spark creates the partition folders; register them with the metastore.
-- (ignore Spark's _spark_metadata folder, which is not a partition)
SET hive.msck.path.validation=ignore;
MSCK REPAIR TABLE api_logs_raw;
MSCK REPAIR TABLE api_logs;

-- 3) Same data stored as ORC (Hive's native columnar format) for the
--    file-format comparison in 03_udf_transform.hql.
CREATE TABLE IF NOT EXISTS api_logs_orc
STORED AS ORC
TBLPROPERTIES ('orc.compress' = 'ZLIB')
AS SELECT * FROM api_logs;

SHOW PARTITIONS api_logs;
