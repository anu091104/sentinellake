# Spark 3.5 (master, worker and the streaming driver) with the Kafka connector baked in,
# so nothing is downloaded at job start.
FROM spark:3.5.3-scala2.12-java17-python3-ubuntu

USER root
ARG MAVEN=https://repo1.maven.org/maven2
RUN cd /opt/spark/jars \
 && curl -fsSLO $MAVEN/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.3/spark-sql-kafka-0-10_2.12-3.5.3.jar \
 && curl -fsSLO $MAVEN/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.3/spark-token-provider-kafka-0-10_2.12-3.5.3.jar \
 && curl -fsSLO $MAVEN/org/apache/kafka/kafka-clients/3.4.1/kafka-clients-3.4.1.jar \
 && curl -fsSLO $MAVEN/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar

RUN pip install --no-cache-dir cassandra-driver==3.29.2 pymongo==4.10.1

COPY sentinellake /opt/sentinellake/sentinellake
ENV PYTHONPATH=/opt/sentinellake TZ=UTC
WORKDIR /opt/sentinellake
USER spark
