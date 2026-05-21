#!/bin/bash
# Render a reference PNG inside the SAME environment the verifier uses
# (Ubuntu 24.04 + Playwright 1.49.0 + pinned Chromium + same font stack).
#
# This eliminates the macOS↔Linux font-rendering drift that would otherwise
# make the oracle score < 1.0 against a macOS-rendered reference.
#
# Usage:
#   pipeline/build-reference.sh <html_path> <output_png> [viewport]
#
# Example:
#   pipeline/build-reference.sh \
#     reference_sites/001-landing/index.html \
#     reference_sites/001-landing/screenshots/index.desktop.png \
#     1440x900
set -euo pipefail

HTML="$1"
PNG="$2"
VIEWPORT="${3:-1440x900}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HTML_REL="${HTML#${REPO_ROOT}/}"
PNG_REL="${PNG#${REPO_ROOT}/}"

echo ">> rendering ${HTML_REL} → ${PNG_REL}  (viewport ${VIEWPORT})"
echo ">> using Ubuntu 24.04 + Playwright 1.49.0 (matches verifier exactly)"

# Pin platform to linux/amd64 so the reference matches what runs on Modal.
docker run --rm --platform linux/amd64 \
  -v "${REPO_ROOT}:/work" -w /work \
  ubuntu:24.04 bash -c "
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive

    apt-get update -qq
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv ca-certificates > /dev/null

    python3 -m venv /opt/venv
    . /opt/venv/bin/activate

    pip install --quiet \
        playwright==1.49.0 \
        pillow==11.0.0 \
        numpy==2.1.3

    playwright install --with-deps chromium > /dev/null

    python /work/pipeline/render.py \
        '/work/${HTML_REL}' \
        '/work/${PNG_REL}' \
        --viewport '${VIEWPORT}' \
        --meta '/work/${PNG_REL%.png}.meta.json'
  "

echo ">> done. PNG: ${PNG}"
ls -la "${PNG}" "${PNG%.png}.meta.json"
