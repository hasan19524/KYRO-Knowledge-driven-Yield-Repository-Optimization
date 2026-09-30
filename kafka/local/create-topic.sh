#!/usr/bin/env bash
# Creates / normalizes the local KYRO topics on the single-broker dev cluster.
#   Topics:      kyro.github.push (live) + kyro.github.backfill (initial sync)
#   Partitions:  5 each (key = repository.github_id -> same repo, same partition)
#   RF:          1  (single local broker - RF=3 is NOT valid here)
#   Retention:   7 days (Kafka is a buffer, PostgreSQL+ChromaDB are persistent)
#   minISR:      1  (must be <= RF on a 1-broker cluster)
# Idempotent: safe to run repeatedly. Never touches other topics.
set -euo pipefail

# When run from Git Bash/MSYS on Windows, stop it from rewriting
# container paths like /opt/kafka/bin/... into Windows paths.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

PARTITIONS=5
RETENTION_MS=604800000
KC="docker exec kyro-kafka /opt/kafka/bin"
BOOTSTRAP="localhost:9092"

create_one() {
  local TOPIC="$1"

  $KC/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists \
    --topic "$TOPIC" \
    --partitions "$PARTITIONS" \
    --replication-factor 1 \
    --config "retention.ms=$RETENTION_MS" \
    --config "min.insync.replicas=1" >/dev/null || true

  local CURRENT
  CURRENT=$($KC/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" \
    --describe --topic "$TOPIC" | sed -n 's/.*PartitionCount: \([0-9]*\).*/\1/p')
  if [ -n "$CURRENT" ] && [ "$CURRENT" -lt "$PARTITIONS" ]; then
    $KC/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" \
      --alter --topic "$TOPIC" --partitions "$PARTITIONS"
  fi

  # Enforce agreed configs even if the topic pre-existed with other values.
  # (kafka-topics --alter --add-config was removed in Kafka 4.x -> kafka-configs)
  $KC/kafka-configs.sh --bootstrap-server "$BOOTSTRAP" \
    --entity-type topics --entity-name "$TOPIC" --alter \
    --add-config "retention.ms=$RETENTION_MS,min.insync.replicas=1" >/dev/null

  $KC/kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --describe --topic "$TOPIC"
}

create_one "kyro.github.push"
create_one "kyro.github.backfill"
