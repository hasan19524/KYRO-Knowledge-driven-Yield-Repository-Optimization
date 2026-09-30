#!/usr/bin/env bash
# Verifies the partition-key strategy (decisions 3/4):
#   - same repository id -> always the same partition (strict per-repo ordering)
#   - different repository ids CAN land on different partitions (parallelism)
# Produces 5 keyed test events (repo 100 x3, 200, 300) and prints the observed
# key -> partition mapping. Only records tagged with this run's marker are
# inspected, so results are independent of whatever else is in the topic.
set -euo pipefail

# When run from Git Bash/MSYS on Windows, stop it from rewriting
# container paths like /opt/kafka/bin/... into Windows paths.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

TOPIC="kyro.github.push"
MARKER="verify-partition-key-$$"

{
  printf '100|{"event":{"id":"%s-a1","type":"push"},"repository":{"github_id":100}}\n' "$MARKER"
  printf '100|{"event":{"id":"%s-a2","type":"push"},"repository":{"github_id":100}}\n' "$MARKER"
  printf '100|{"event":{"id":"%s-a3","type":"push"},"repository":{"github_id":100}}\n' "$MARKER"
  printf '200|{"event":{"id":"%s-b1","type":"push"},"repository":{"github_id":200}}\n' "$MARKER"
  printf '300|{"event":{"id":"%s-c1","type":"push"},"repository":{"github_id":300}}\n' "$MARKER"
} | docker exec -i kyro-kafka /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 --topic "$TOPIC" \
    --property parse.key=true --property key.separator='|' >/dev/null

sleep 1
echo "=== consumed records for this run (partition, key, value) ==="
docker exec kyro-kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic "$TOPIC" --from-beginning --timeout-ms 8000 \
  --property print.partition=true --property print.offset=true \
  --property print.key=true --property key-separator=' > ' 2>/dev/null |
  grep "$MARKER"

echo
echo "=== key -> partition mapping (this run) ==="
docker exec kyro-kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic "$TOPIC" --from-beginning --timeout-ms 8000 \
  --property print.partition=true --property print.key=true --property key-separator=' > ' 2>/dev/null |
  grep "$MARKER" |
  awk '{
    key=""; part="";
    for (i = 1; i <= NF; i++) {
      if ($i == "key:")  key = $(i+1);
      if ($i == "partition:") part = $(i+1);
    }
    if (key != "") print key" -> partition "part;
  }' | sort -u
