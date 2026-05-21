"""VLM-as-judge metric — Claude Sonnet 4.6 scoring (reference, candidate) PNG pairs.

Restored for validation: we want to compare VLM scores against structured
metrics on real candidates and let a human decide whether VLM is calibrated
well enough to keep as a graded metric. See key_decisions.md R11.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path


VLM_MODEL = "claude-sonnet-4-6"
VLM_TIMEOUT_SEC = 30.0
VLM_MAX_TOKENS = 256


_VLM_PROMPT = """You are evaluating whether a candidate webpage screenshot replicates a reference webpage screenshot.

The first image is the REFERENCE (what the page should look like).
The second image is the CANDIDATE (what an AI agent produced trying to replicate the reference).

Score visual similarity from 0.0 to 1.0:
  1.0 = visually identical
  0.8 = clearly the same design, minor differences
  0.5 = recognizably similar but different in obvious ways
  0.2 = related but very different
  0.0 = unrelated

Consider: layout, color palette, typography, spacing, visual hierarchy, overall design fidelity.

Respond ONLY with this JSON, nothing else:
{"score": 0.0, "reason": "one sentence explaining the score"}"""


@dataclass
class MetricResult:
    name: str
    score: float | None
    extra: dict


def _png_b64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("ascii")


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def judge(reference_png: Path, candidate_png: Path) -> MetricResult:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return MetricResult(name="vlm_judge", score=None,
                            extra={"skipped": True, "reason": "ANTHROPIC_API_KEY not set"})
    try:
        import anthropic
    except ImportError as e:
        return MetricResult(name="vlm_judge", score=None,
                            extra={"skipped": True, "reason": f"anthropic SDK missing: {e}"})

    client = anthropic.Anthropic(api_key=api_key, timeout=VLM_TIMEOUT_SEC)
    started = time.time()
    try:
        resp = client.messages.create(
            model=VLM_MODEL,
            max_tokens=VLM_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "REFERENCE:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": _png_b64(reference_png)}},
                    {"type": "text", "text": "CANDIDATE:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": _png_b64(candidate_png)}},
                    {"type": "text", "text": _VLM_PROMPT},
                ],
            }],
        )
    except Exception as e:
        return MetricResult(name="vlm_judge", score=None,
                            extra={"error": f"{type(e).__name__}: {e}", "wall_s": time.time() - started})

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    parsed = _extract_json(text)
    if parsed is None or "score" not in parsed:
        return MetricResult(name="vlm_judge", score=None,
                            extra={"error": "could not parse JSON", "raw": text[:500],
                                   "wall_s": time.time() - started})
    try:
        score = float(parsed["score"])
    except (TypeError, ValueError):
        return MetricResult(name="vlm_judge", score=None,
                            extra={"error": "non-numeric score", "raw": text[:500]})
    score = max(0.0, min(1.0, score))
    return MetricResult(name="vlm_judge", score=score,
                        extra={"reason": parsed.get("reason", "")[:300],
                               "model": VLM_MODEL,
                               "wall_s": round(time.time() - started, 2)})
