#!/bin/bash
# Phase 1 verifier: install grader deps, render the agent's HTML, run grader.
# Reward is the grader's composite score (SSIM × anticheat multiplier).
#
# Note: stderr is intentionally NOT swallowed on the install steps so a failed
# apt-get / playwright install is diagnosable on the first Modal run.
set -u

mkdir -p /logs/verifier /logs/verifier/network /logs/verifier/grading

# ---- 0. Environment forensics (detect Harbor env stripping, etc.) ----
{
  echo "=== verifier env snapshot ==="
  printenv | sort
  echo
  echo "=== uname ==="
  uname -a
  echo
  echo "=== /etc/os-release ==="
  cat /etc/os-release 2>/dev/null || echo "(none)"
} > /logs/verifier/env-snapshot.txt 2>&1

# ---- 1. Snapshot the agent's network log into the verifier output ----
if [ -d /logs/agent/network ]; then
  cp -r /logs/agent/network/* /logs/verifier/network/ 2>/dev/null || true
fi

# ---- 2. Snapshot the agent's filesystem output ----
mkdir -p /logs/verifier/agent_output
cp -r /app/* /logs/verifier/agent_output/ 2>/dev/null || true

# ---- 3. Install grader dependencies (stderr visible) ----
{
  echo "=== apt-get install ==="
  apt-get update
  apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv curl ca-certificates
} > /logs/verifier/install.log 2>&1

python3 -m venv /opt/grader-venv
. /opt/grader-venv/bin/activate

# Pin Playwright AND its bundled Chromium for reproducibility. The reference
# PNG must have been rendered with this same version (enforced by build script).
{
  echo "=== pip install ==="
  pip install --quiet \
      playwright==1.49.0 \
      scikit-image==0.24.0 \
      pillow==11.0.0 \
      numpy==2.1.3 \
      scipy==1.14.1 \
      anthropic==0.70.0
  echo "=== playwright install ==="
  playwright install --with-deps chromium
} >> /logs/verifier/install.log 2>&1
PW_EXIT=$?

if [ ${PW_EXIT} -ne 0 ]; then
  echo "WARNING: playwright install --with-deps exited ${PW_EXIT}; trying without deps" >> /logs/verifier/install.log 2>&1
  playwright install chromium >> /logs/verifier/install.log 2>&1
fi

# ---- 4. Run the grader against pre-built reference artifacts ----
# /tests/reference_truth/ holds reference PNGs + .dom.json sidecars built by
# pipeline/build_task.py once. /tests/build_manifest.json records the source
# HTML SHA256s + chromium version used; we surface it to the logs for audit.
cp /tests/build_manifest.json /logs/verifier/grading/build_manifest.json 2>/dev/null || true

python3 /tests/grade.py \
    --agent-html /app \
    --reference-dir /tests/reference_truth \
    --output-dir /logs/verifier/grading \
    --reward-file /logs/verifier/reward.txt \
    --render \
    > /logs/verifier/grading/stdout.log 2>&1

GRADE_EXIT=$?

# ---- 5. Defensive fallback ----
if [ ! -f /logs/verifier/reward.txt ]; then
  echo 0.0 > /logs/verifier/reward.txt
  echo "GRADER_CRASHED exit=${GRADE_EXIT}" > /logs/verifier/grading/CRASH
fi

# ---- 6. Surface results ----
echo "--- reward ---"
cat /logs/verifier/reward.txt
echo
echo "--- grading/subscores.json ---"
cat /logs/verifier/grading/subscores.json 2>/dev/null || echo "(missing)"
echo
echo "--- grading/anticheat.json ---"
cat /logs/verifier/grading/anticheat.json 2>/dev/null || echo "(missing)"
echo
echo "--- agent output files ---"
ls -la /logs/verifier/agent_output/ 2>&1 | head -20
echo
echo "--- egress summary (proxy log) ---"
if [ -f /logs/verifier/network/egress.jsonl ]; then
  python3 - <<'PY'
import json, collections, pathlib
p = pathlib.Path("/logs/verifier/network/egress.jsonl")
counts = collections.Counter()
for line in p.read_text().splitlines():
    try:
        ev = json.loads(line)
    except Exception:
        continue
    host = ev.get("host") or ev.get("method")
    port = ev.get("port", "")
    key = f"{host}:{port}" if port else str(host)
    counts[key] += 1
for k, v in counts.most_common():
    print(f"  {v:5d}  {k}")
PY
else
  echo "(no egress log)"
fi
