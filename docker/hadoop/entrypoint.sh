#!/usr/bin/env bash
set -euo pipefail

wait_for() {  # host port
  until nc -z "$1" "$2"; do echo "waiting for $1:$2"; sleep 3; done
}

case "${1:-}" in
  namenode)
    if [[ ! -d /data/namenode/current ]]; then
      hdfs namenode -format -force -nonInteractive -clusterId sentinellake
    fi
    exec hdfs namenode
    ;;
  datanode)
    wait_for namenode 8020
    exec hdfs datanode
    ;;
  hdfs-init)
    wait_for namenode 8020
    until hdfs dfsadmin -safemode get | grep -q OFF; do sleep 2; done
    hdfs dfs -mkdir -p /sentinellake/raw /sentinellake/curated /sentinellake/checkpoints \
                       /sentinellake/mapreduce /tmp /user/hive/warehouse /mr-history
    hdfs dfs -chmod -R 777 /sentinellake /tmp /user /mr-history
    echo "HDFS layout ready"; hdfs dfs -ls /sentinellake
    ;;
  resourcemanager)
    wait_for namenode 8020
    exec yarn resourcemanager
    ;;
  nodemanager)
    wait_for resourcemanager 8031
    exec yarn nodemanager
    ;;
  historyserver)
    wait_for namenode 8020
    exec mapred historyserver
    ;;
  hiveserver2)
    wait_for namenode 8020
    if [[ ! -d /data/metastore_db ]]; then
      schematool -dbType derby -initSchema
    fi
    exec hiveserver2 --hiveconf hive.root.logger=WARN,console
    ;;
  *)
    exec "$@"
    ;;
esac
