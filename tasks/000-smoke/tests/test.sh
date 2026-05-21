#!/bin/bash
set -u

mkdir -p /logs/verifier /logs/verifier/network

# --- Snapshot network logs from agent container ---
if [ -d /logs/agent/network ]; then
  cp -r /logs/agent/network/* /logs/verifier/network/ 2>/dev/null || true
fi

# --- Summarize egress by host (if log exists) ---
if [ -f /logs/verifier/network/egress.jsonl ]; then
  python3 - <<'PY' > /logs/verifier/network/egress-summary.txt 2>&1
import json, collections, pathlib
p = pathlib.Path("/logs/verifier/network/egress.jsonl")
counts = collections.Counter()
errors = collections.Counter()
for line in p.read_text().splitlines():
    try:
        ev = json.loads(line)
    except Exception:
        continue
    host = ev.get("host") or ev.get("method")
    port = ev.get("port", "")
    key = f"{host}:{port}" if port else str(host)
    if ev.get("error"):
        errors[key] += 1
    else:
        counts[key] += 1
print("--- successful connections ---")
for k, v in counts.most_common():
    print(f"  {v:5d}  {k}")
print()
print("--- failed connections ---")
for k, v in errors.most_common():
    print(f"  {v:5d}  {k}")
PY
fi

# --- Reward logic ---
if [ -f /app/hello.txt ] && [ "$(cat /app/hello.txt)" = "hello" ]; then
  echo 1 > /logs/verifier/reward.txt
  echo "PASS: /app/hello.txt contains 'hello'" > /logs/verifier/result.txt
else
  echo 0 > /logs/verifier/reward.txt
  {
    echo "FAIL"
    echo "exists=$([ -f /app/hello.txt ] && echo yes || echo no)"
    echo "content=$(cat /app/hello.txt 2>/dev/null || echo MISSING)"
  } > /logs/verifier/result.txt
fi

echo "--- reward ---"
cat /logs/verifier/reward.txt
echo "--- result ---"
cat /logs/verifier/result.txt
echo "--- network log files ---"
ls -la /logs/verifier/network/ 2>&1
echo "--- egress summary ---"
cat /logs/verifier/network/egress-summary.txt 2>/dev/null || echo "(no summary)"
