#!/bin/bash
# Starts the egress-logging proxy in the background, then execs whatever
# command Harbor wants to run (typically a long-lived sleep or the agent CLI).

set -u

NET_LOG_DIR=/logs/agent/network
mkdir -p "${NET_LOG_DIR}"
SETUP_LOG="${NET_LOG_DIR}/setup.log"

{
  echo "=== entrypoint.sh starting at $(date -Iseconds) ==="
  echo "PROXY_LOG=${PROXY_LOG:-/logs/agent/network/egress.jsonl}"
  echo "HTTPS_PROXY=${HTTPS_PROXY:-unset}"

  PROXY_LOG="${NET_LOG_DIR}/egress.jsonl" \
    python3 /opt/proxy.py >> "${NET_LOG_DIR}/proxy.stdout" 2>> "${NET_LOG_DIR}/proxy.stderr" &
  PROXY_PID=$!
  echo "proxy started, pid=${PROXY_PID}"
  disown ${PROXY_PID} 2>/dev/null || true

  for i in 1 2 3 4 5; do
    if (echo > /dev/tcp/127.0.0.1/8080) 2>/dev/null; then
      echo "proxy: listening on 127.0.0.1:8080"
      break
    fi
    sleep 0.2
  done

  echo "=== entrypoint.sh setup complete ==="
} >> "${SETUP_LOG}" 2>&1

exec "$@"
