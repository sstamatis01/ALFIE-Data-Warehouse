#!/usr/bin/env bash
# Start N concept-drift consumer processes (same consumer group, parallel partitions).
# Usage: ./scripts/run_concept_drift_workers.sh [N]
#   N defaults to 3. Uses .venv-concept-drift/bin/python unless PYTHON is set.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

WORKERS="${1:-3}"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv-concept-drift}"
PYTHON="${PYTHON:-$VENV_DIR/bin/python}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs}"
mkdir -p "$LOG_DIR"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python not found at $PYTHON"
  echo "Create the venv: python3 -m venv .venv-concept-drift && source .venv-concept-drift/bin/activate && pip install -r requirements.txt"
  echo "Or set PYTHON=/path/to/python"
  exit 1
fi

: "${KAFKA_BOOTSTRAP_SERVERS:?Set KAFKA_BOOTSTRAP_SERVERS}"
: "${API_BASE:?Set API_BASE}"

export KAFKA_CONCEPT_DRIFT_CONSUMER_GROUP="${KAFKA_CONCEPT_DRIFT_CONSUMER_GROUP:-concept-drift-consumer}"

echo "Starting $WORKERS concept-drift worker(s) group=$KAFKA_CONCEPT_DRIFT_CONSUMER_GROUP python=$PYTHON"

for i in $(seq 1 "$WORKERS"); do
  export CONCEPT_DRIFT_WORKER_ID="$i"
  LOG_FILE="$LOG_DIR/concept_drift_${i}.log"
  nohup "$PYTHON" kafka_concept_drift_consumer_example.py >>"$LOG_FILE" 2>&1 &
  echo "  worker $i pid=$! log=$LOG_FILE"
done

echo "Done. Tail logs: tail -f $LOG_DIR/concept_drift_*.log"
