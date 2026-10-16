# One image for every Hadoop-side role: HDFS, YARN, MapReduce history server and Hive.
# The role is chosen by the container command (see entrypoint.sh).
FROM eclipse-temurin:8-jre-jammy

ARG HADOOP_VERSION=3.3.6
ARG HIVE_VERSION=4.0.1
ARG APACHE_MIRROR=https://archive.apache.org/dist

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 curl procps netcat-openbsd \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "$APACHE_MIRROR/hadoop/common/hadoop-$HADOOP_VERSION/hadoop-$HADOOP_VERSION.tar.gz" \
      | tar -xz -C /opt \
 && ln -s "/opt/hadoop-$HADOOP_VERSION" /opt/hadoop \
 && rm -rf /opt/hadoop/share/doc

RUN curl -fsSL "$APACHE_MIRROR/hive/hive-$HIVE_VERSION/apache-hive-$HIVE_VERSION-bin.tar.gz" \
      | tar -xz -C /opt \
 && ln -s "/opt/apache-hive-$HIVE_VERSION-bin" /opt/hive

ENV HADOOP_HOME=/opt/hadoop \
    HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop \
    HIVE_HOME=/opt/hive \
    HDFS_NAMENODE_USER=root HDFS_DATANODE_USER=root \
    YARN_RESOURCEMANAGER_USER=root YARN_NODEMANAGER_USER=root
ENV PATH="$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$HIVE_HOME/bin:$PATH"

COPY conf/core-site.xml conf/hdfs-site.xml conf/yarn-site.xml conf/mapred-site.xml $HADOOP_CONF_DIR/
COPY conf/hive-site.xml $HIVE_HOME/conf/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /opt/sentinellake
ENTRYPOINT ["/entrypoint.sh"]
