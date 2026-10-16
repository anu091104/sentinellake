#!/usr/bin/env bash
# Run the three SentinelLake MapReduce jobs on the Hadoop/YARN cluster.
# Execute inside the namenode container:  docker compose exec namenode bash /opt/sentinellake/mapreduce/run_hadoop.sh 2026-10-12
set -euo pipefail

DT="${1:?usage: run_hadoop.sh <yyyy-mm-dd> [trace_id]}"
TRACE="${2:-}"
JOBS="$(cd "$(dirname "$0")/jobs" && pwd)"
LAKE="/sentinellake"
IN="$LAKE/raw/api_logs/dt=$DT"
OUT="$LAKE/mapreduce/dt=$DT"
STREAMING_JAR="$(ls "$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar)"

hdfs dfs -rm -r -f -skipTrash "$OUT" >/dev/null
echo ">> input: $(hdfs dfs -du -s -h "$IN")"

echo ">> job 1/3  error hotspots  (mapper + combiner + partitioner + reducer, compressed shuffle)"
hadoop jar "$STREAMING_JAR" \
  -D mapreduce.job.name="sentinellake-hotspots-$DT" \
  -D stream.num.map.output.key.fields=2 \
  -D mapreduce.partition.keypartitioner.options=-k1,1 \
  -D mapreduce.job.reduces=3 \
  -D mapreduce.map.output.compress=true \
  -D mapreduce.map.output.compress.codec=org.apache.hadoop.io.compress.SnappyCodec \
  -D mapreduce.output.fileoutputformat.compress=true \
  -D mapreduce.output.fileoutputformat.compress.codec=org.apache.hadoop.io.compress.GzipCodec \
  -files "$JOBS/hotspots_mapper.py,$JOBS/hotspots_reducer.py" \
  -mapper  "python3 hotspots_mapper.py" \
  -combiner "python3 hotspots_reducer.py" \
  -reducer "python3 hotspots_reducer.py --final" \
  -partitioner org.apache.hadoop.mapred.lib.KeyFieldBasedPartitioner \
  -input "$IN" -output "$OUT/hotspots"

echo ">> job 2/3  rank endpoints by error rate  (total sort, numeric descending)"
hadoop jar "$STREAMING_JAR" \
  -D mapreduce.job.name="sentinellake-rank-$DT" \
  -D stream.num.map.output.key.fields=1 \
  -D mapreduce.job.output.key.comparator.class=org.apache.hadoop.mapred.lib.KeyFieldBasedComparator \
  -D mapreduce.partition.keycomparator.options=-k1,1nr \
  -D mapreduce.job.reduces=1 \
  -files "$JOBS/rank_mapper.py" \
  -cmdenv RANK_BY=error_rate \
  -mapper "python3 rank_mapper.py" -reducer /bin/cat \
  -input "$OUT/hotspots" -output "$OUT/ranked_by_error_rate"

if [[ -n "$TRACE" ]]; then
  FILTER="trace_id=$TRACE"
else
  FILTER="service=payments,status>=500"
fi
echo ">> job 3/3  search  (map-only, FILTER=$FILTER)"
hadoop jar "$STREAMING_JAR" \
  -D mapreduce.job.name="sentinellake-search-$DT" \
  -D mapreduce.job.reduces=0 \
  -files "$JOBS/search_mapper.py" \
  -cmdenv FILTER="$FILTER" \
  -mapper "python3 search_mapper.py" \
  -input "$IN" -output "$OUT/search"

echo
echo "== Top 10 endpoints by 5xx error rate =="
printf "%-10s %-10s %-24s %9s\n" "rate" "service" "endpoint" "requests"
hdfs dfs -cat "$OUT/ranked_by_error_rate/part-*" | head -10 | awk -F'\t' '{printf "%-10s %-10s %-24s %9s\n", $1, $2, $3, $4}'
echo
echo "search matches: $(hdfs dfs -cat "$OUT/search/part-*" | wc -l)"
