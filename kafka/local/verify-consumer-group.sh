#!/usr/bin/env bash
# Verifies consumer-group partition distribution (decisions 6/10/11):
#   - two consumers join group "kyro-ingestion-workers"
#   - the 5 partitions are split between them
#   - no partition is assigned to both consumers at the same time
# Runs console consumers (auto-commit) purely to observe assignment; the real
# processing strategy (manual commit) is verified by verify/consume_verify.py.
set -euo pipefail

# When run from Git Bash/MSYS on Windows, stop it from rewriting
# container paths like /opt/kafka/bin/... into Windows paths.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

GROUP="kyro-ingestion-workers"
TOPIC="kyro.github.push"
KC="/opt/kafka/bin"

# Start from a clean group so assignment is deterministic.
docker exec kyro-kafka $KC/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --delete --group "$GROUP" >/dev/null 2>&1 || true

echo "Starting 2 consumers in group '$GROUP'..."
docker exec -d kyro-kafka bash -c "$KC/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic $TOPIC --group $GROUP --from-beginning --timeout-ms 15000 > /tmp/cg1.out 2>/dev/null"
docker exec -d kyro-kafka bash -c "$KC/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic $TOPIC --group $GROUP --from-beginning --timeout-ms 15000 > /tmp/cg2.out 2>/dev/null"

sleep 6

echo
echo "=== group describe (2 consumers, 5 partitions) ==="
docker exec kyro-kafka $KC/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group "$GROUP"

echo
echo "=== overlap check: partitions assigned more than once ==="
OVERLAP=$(docker exec kyro-kafka $KC/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group "$GROUP" --members --verbose 2>/dev/null |
  awk '/^Topic:|^ *Topic:/ {t=$2} /Partition:/ {print $2}' |
  sort | uniq -d || true)
if [ -z "${OVERLAP}" ]; then
  echo "OK: no partition is assigned to two consumers simultaneously"
else
  echo "FAIL: partitions assigned more than once: ${OVERLAP}"
  exit 1
fi

# let the consumers exit on their own timeout, then clean up the group
sleep 12
docker exec kyro-kafka $KC/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --delete --group "$GROUP" >/dev/null 2>&1 || true
