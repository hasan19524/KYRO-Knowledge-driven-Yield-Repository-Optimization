#!/usr/bin/env bash
# PRODUCTION topic creation - 3 brokers, RF=3. Not for the local 1-broker cluster.
#
#   Topics:     kyro.github.push (live) + kyro.github.backfill (initial sync)
#   Partitions: 5 each
#   RF:         3  (replicas on all 3 brokers; leader elected from ISR)
#   minISR:     2  (matches broker min.insync.replicas; acks=all succeeds with
#                   1 broker down, fails with 2 down rather than losing data)
#   Retention:  7 days
#
# Partition key is NOT set here: keys are assigned by the producer
# (repository.github_id). Kafka hashes the key -> partition, so the same
# repository always lands on the same partition (ordering) while different
# repositories spread across partitions (concurrency).
set -euo pipefail

BOOTSTRAP="${BOOTSTRAP:-kyro-kafka-1:9092}"

for TOPIC in kyro.github.push kyro.github.backfill; do
  docker exec kyro-kafka-1 /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists \
    --topic "$TOPIC" \
    --partitions 5 \
    --replication-factor 3 \
    --config retention.ms=604800000 \
    --config min.insync.replicas=2

  docker exec kyro-kafka-1 /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP" \
    --describe --topic "$TOPIC"
done
