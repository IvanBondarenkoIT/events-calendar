#!/usr/bin/env bash
# One-shot DEC reminder slot. Usage: ./run-slot.sh morning|evening
set -euo pipefail

SLOT="${1:-}"
if [[ "$SLOT" != "morning" && "$SLOT" != "evening" ]]; then
  echo "Usage: $0 morning|evening" >&2
  exit 2
fi

DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${DEC_IMAGE:-ghcr.io/ivanbondarenkoit/events-calendar:latest}"
ENV_FILE="${DEPLOY_DIR}/.env"
DATA_DIR="${DEPLOY_DIR}/data"
LOGS_DIR="${DEPLOY_DIR}/logs"

if [[ ! -f "$ENV_FILE" ]]; then
  echo ".env not found: $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$DATA_DIR" "$LOGS_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOGS_DIR}/dec-${SLOT}-${STAMP}.log"

docker_cmd() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sg docker -c "docker $(printf '%q ' "$@")"
  fi
}

echo "DeployDir=${DEPLOY_DIR} Image=${IMAGE} Slot=${SLOT} Log=${LOG_FILE}"

set +e
docker_cmd run --rm \
  --env-file "$ENV_FILE" \
  -e TZ=Asia/Tbilisi \
  -e PYTHONPATH=/app/src \
  -e IDEMPOTENCY_PATH=/app/data/alert_state.json \
  -v "${DATA_DIR}:/app/data" \
  "$IMAGE" \
  python -m dec_calendar run-once --slot "$SLOT" 2>&1 | tee "$LOG_FILE"
CODE=${PIPESTATUS[0]}
set -e

if [[ "$CODE" -ne 0 ]]; then
  echo "dec-calendar run-once --slot ${SLOT} failed (${CODE}), see ${LOG_FILE}" >&2
  exit "$CODE"
fi

echo "OK slot=${SLOT}"
exit 0
