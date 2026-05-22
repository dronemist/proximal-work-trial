"""VLM-as-judge metric — Claude Sonnet 4.6 scoring (reference, candidate) PNG pairs.

Restored for validation: we want to compare VLM scores against structured
metrics on real candidates and let a human decide whether VLM is calibrated
well enough to keep as a graded metric. See key_decisions.md R11.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path


VLM_MODEL = "claude-sonnet-4-6"
VLM_TIMEOUT_SEC = 30.0
VLM_MAX_TOKENS = 512
# Anthropic API rejects images whose largest dimension exceeds 8000px. Full-page
# mobile screenshots routinely exceed this. Downscale before sending.
VLM_MAX_DIM = 7800


_VLM_PROMPT = """You are evaluating whether a candidate webpage screenshot faithfully replicates a reference webpage screenshot. The candidate was produced by an AI agent trying to copy the reference exactly. Be a strict critic — small differences are evidence of failure, not stylistic choice.

The first image is the REFERENCE (what the page should look like).
The second image is the CANDIDATE (what the AI agent produced).

Score from 0.0 to 1.0 by checking each of these in order. **Charts, tables, icons, and content count more than overall layout** — those are where agents fabricate.

1. **Content fidelity (most important)**
   - Are charts/graphs data-accurate? Same shape, same trend, same axis labels?
   - Do tables have the same number of rows? Same values in matching cells?
   - Are icons rendered correctly (right glyph, right style)?
   - Did the agent hallucinate extra UI elements, data points, or sections?

2. **Visual fidelity**
   - Colors: do background tones, button colors, accent colors match? Look carefully at the *dominant* background color — even a small hue shift (e.g. cyan-tinted black vs navy blue) means the page identity is different. Don't treat "both look dark" as a match.
   - Typography hierarchy: do heading sizes match? Body weights match?
   - Layout: do panels, spacing, and alignment match?

3. **Faithfulness penalties**
   - Major content hallucination (e.g. 9 rows in ref → 100 rows in candidate): cap at 0.4.
   - Wrong chart data or wrong icons: cap at 0.6.
   - Wrong colors but right layout: cap at 0.7.

Scoring scale:
  1.0 = visually and structurally identical
  0.8 = same design, only minor color/spacing drift, content fully matches
  0.5 = layout matches but content wrong (hallucinated data, wrong chart, wrong icons)
  0.3 = different at a glance OR significant content fabrication
  0.0 = unrelated

Respond ONLY with this JSON, nothing else:
{"score": 0.0, "reason": "one sentence calling out the most important difference"}"""


@dataclass
class MetricResult:
    name: str
    score: float | None
    extra: dict


def _png_b64(path: Path) -> str:
    raw = path.read_bytes()
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if max(w, h) > VLM_MAX_DIM:
            scale = VLM_MAX_DIM / max(w, h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            raw = buf.getvalue()
    except Exception:
        pass
    return base64.standard_b64encode(raw).decode("ascii")


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        pass
    # Truncated JSON (max_tokens cap mid-reason): pull the score directly.
    s = re.search(r'"score"\s*:\s*([0-9.]+)', text)
    if s:
        try:
            r = re.search(r'"reason"\s*:\s*"([^"]*)', text)
            return {"score": float(s.group(1)),
                    "reason": (r.group(1) if r else "") + " [truncated]"}
        except ValueError:
            return None
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
