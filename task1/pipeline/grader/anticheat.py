"""
All anti-cheat detection lives here.

Six independent checks are exposed:

  1. `scan_html_css(html_dir)` — static-analysis scan of agent HTML/CSS for
     data:image URIs, <iframe>, <canvas>, <object>, and <embed> usage.
  2. `detect_image_copies(agent_dir, reference_dir)` — file-byte equality
     between any image in /app/ and any reference PNG. Catches
     `cp /reference/foo.png /app/foo.png` + `<img src="foo.png">`.
  3. `detect_off_origin(render_meta)` — any off-origin request the candidate's
     rendered page tried to make (CDN, web font, hotlinked image).
  4. `detect_raster_images(agent_dir)` — flags any raster image file
     (png, jpg, gif, etc.) in the agent output. SVGs are excluded.
  5. `detect_oversized_svgs(html_dir, viewport_area)` — flags inline <svg>
     elements covering more than 10% of the viewport area (HTML attributes only;
     skips percent-width and viewBox-only SVGs).
  6. `detect_oversized_rendered_svgs(candidate_dir, viewport_area)` — reads each
     candidate `.dom.json` sidecar and flags any <svg> whose rendered bbox
     exceeds 50% of viewport area. Catches the percent-width / viewBox-only
     gap left by check 5.

Each returns `list[dict]` of violations. Use `combine_violations(*lists)` to
fold them into a single `AnticheatResult` with the multiplicative penalty.

We use a **flat 0.1× penalty if ANY violation fires**. One knob; easy to tune.
Flipping to hard-zero is a one-line change.

NOTE — the agent's instruction.md does NOT mention any of these checks, nor
any of the structured metrics in metrics.py, nor the harmonic aggregation in
grade.py. The agent is told only the task ("replicate these screenshots"),
the output paths, the viewports it will be rendered at, and a short list of
generic constraints (HTML/CSS only, no JS, no external resources, avoid
horizontal overflow). It is NOT told:
  - which metrics are used, or their weights
  - that VLM judging is part of the score
  - that the score uses a harmonic mean across viewports/pages
  - that data:image URIs, oversized SVGs, raster files, off-origin requests,
    or reference image copies will trip an anticheat multiplier
This is deliberate: we want to measure faithful replication, not score-hacking
against a known rubric. Any leak of grader internals into instruction.md would
let the agent optimise the metric instead of the design.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

VIOLATION_PENALTY = 0.1


# ---------------------------------------------------------------------------
# Result type + combiner
# ---------------------------------------------------------------------------

@dataclass
class AnticheatResult:
    penalty_multiplier: float       # eval-mode multiplier (0.1 if any violation, else 1.0)
    train_penalty: float            # train-mode subtractive penalty (0.0 if none, capped)
    violations: list[dict]
    counts: dict[str, int]


TRAIN_PENALTY_PER_TYPE = 0.05       # subtractive per distinct violation type at training time
TRAIN_PENALTY_CAP = 0.20            # max total subtractive penalty


def combine_violations(*violation_lists: list[dict]) -> AnticheatResult:
    """Fold per-check violation lists into a single AnticheatResult.

    Exposes two penalty shapes so eval and RL training can decouple:
      - `penalty_multiplier`: flat 0.1× if any violation fires (held-out eval semantic:
        "you cheated → near-zero").
      - `train_penalty`: subtractive penalty = min(CAP, PER_TYPE × distinct_violation_types).
        Bridges the post-anticheat 0.0–0.4 dead-zone in the reward distribution so RL
        gradient is preserved when an agent writes real pages but trips one violation
        (e.g., a single inline data-URI icon).

    Counts are keyed by violation `check` field so consumers can break down failures.
    """
    all_v: list[dict] = []
    counts: dict[str, int] = {}
    for vs in violation_lists:
        for v in vs:
            all_v.append(v)
            counts[v.get("check", "unknown")] = counts.get(v.get("check", "unknown"), 0) + 1
    multiplier = VIOLATION_PENALTY if all_v else 1.0
    train_penalty = min(TRAIN_PENALTY_CAP, TRAIN_PENALTY_PER_TYPE * len(counts))
    return AnticheatResult(
        penalty_multiplier=multiplier,
        train_penalty=train_penalty,
        violations=all_v,
        counts=counts,
    )


# ---------------------------------------------------------------------------
# Check 1 — static HTML/CSS scan
# ---------------------------------------------------------------------------

# Strip <!-- ... --> HTML comments and /* ... */ CSS comments before scanning so
# agents writing legitimate comments like "<!-- no iframe used -->" aren't flagged.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

_DATA_IMAGE_URI = re.compile(r"""data:image/[a-zA-Z0-9.+\-]+[;,]""", re.IGNORECASE)
_IFRAME_TAG = re.compile(r"<\s*iframe[\s>/]", re.IGNORECASE)
_CANVAS_TAG = re.compile(r"<\s*canvas[\s>/]", re.IGNORECASE)
_OBJECT_TAG = re.compile(r"<\s*object[\s>/]", re.IGNORECASE)
_EMBED_TAG = re.compile(r"<\s*embed[\s>/]", re.IGNORECASE)


def _strip_comments(text: str) -> str:
    return _CSS_COMMENT.sub("", _HTML_COMMENT.sub("", text))


DATA_IMAGE_MIN_PAYLOAD_BYTES = 2048  # below this is an inline icon, not a reference-image embed


def _scan_single_file(text: str, source_path: Path | None, kind: str) -> list[dict]:
    stripped = _strip_comments(text)
    out: list[dict] = []
    for m in _DATA_IMAGE_URI.finditer(stripped):
        # Size-aware: small data: URIs (icons via mask-image / background-image) are
        # standard CSS practice and not what this rule was intended to catch. Only
        # flag payloads ≥ DATA_IMAGE_MIN_PAYLOAD_BYTES — a reference PNG base64-encodes
        # to ~100KB, while an inline SVG icon is typically <500B.
        start = m.end()
        end = -1
        for closer in (")", '"', "'"):
            i = stripped.find(closer, start)
            if i >= 0 and (end < 0 or i < end):
                end = i
        if end < 0:
            end = len(stripped)
        payload_bytes = end - start
        if payload_bytes < DATA_IMAGE_MIN_PAYLOAD_BYTES:
            continue
        out.append(
            {
                "check": "data_image_uri",
                "match": m.group(0),
                "position": m.start(),
                "payload_bytes": payload_bytes,
                "source": str(source_path) if source_path else None,
            }
        )
    if kind == "html":
        for tag_re, check_name in [
            (_IFRAME_TAG, "iframe"),
            (_CANVAS_TAG, "canvas"),
            (_OBJECT_TAG, "object"),
            (_EMBED_TAG, "embed"),
        ]:
            for m in tag_re.finditer(stripped):
                out.append(
                    {
                        "check": check_name,
                        "match": m.group(0),
                        "position": m.start(),
                        "source": str(source_path) if source_path else None,
                    }
                )
    return out


def scan_html_css(html_dir: Path) -> list[dict]:
    """Scan every .html / .htm / .css file in html_dir (recursively) for
    static violations. HTML and CSS comments are stripped before scanning so
    agent-written comments don't trigger false positives.
    """
    violations: list[dict] = []
    for path in html_dir.rglob("*"):
        ext = path.suffix.lower()
        if ext not in {".html", ".htm", ".css"}:
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        kind = "html" if ext in {".html", ".htm"} else "css"
        violations.extend(_scan_single_file(text, source_path=path, kind=kind))
    return violations


# ---------------------------------------------------------------------------
# Check 2 — image-copy detection (byte-equality with any reference PNG)
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detect_image_copies(agent_dir: Path, reference_dir: Path) -> list[dict]:
    """Detect any file in agent_dir that's byte-identical to a reference image.

    The reference site uses no <img> tags at all, so this is high-precision:
    a legitimate agent has no reason to ship a byte-for-byte copy of a
    reference screenshot.
    """
    ref_hashes: dict[str, str] = {}
    for ref in reference_dir.glob("*.png"):
        ref_hashes[_file_sha256(ref)] = ref.name

    out: list[dict] = []
    for path in agent_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
            continue
        h = _file_sha256(path)
        if h in ref_hashes:
            out.append(
                {
                    "check": "reference_image_copy",
                    "agent_path": str(path),
                    "matches_reference": ref_hashes[h],
                    "sha256": h,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Check 3 — off-origin requests during candidate render
# ---------------------------------------------------------------------------


def detect_off_origin(render_meta: dict) -> list[dict]:
    """Penalize any off-origin request made by the agent's rendered page.

    The renderer captures these in `off_origin_requests`. We re-surface them
    here as anti-cheat violations so the penalty multiplier reflects them.
    """
    out: list[dict] = []
    for key, meta in (render_meta or {}).items():
        for req in (meta.get("off_origin_requests") or []) if isinstance(meta, dict) else []:
            out.append({"check": "off_origin_request", "key": key, "request": req})
    return out


# ---------------------------------------------------------------------------
# Check 4 — raster image files in agent output
# ---------------------------------------------------------------------------

_RASTER_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff", ".tif"}


def detect_raster_images(agent_dir: Path) -> list[dict]:
    """Flag any raster image file in the agent output.

    A CSS-only layout task has no legitimate reason to include raster images.
    SVGs are excluded — small SVGs (icons, decorative) are acceptable.
    """
    out: list[dict] = []
    for path in agent_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in _RASTER_IMAGE_EXTS:
            out.append(
                {
                    "check": "raster_image_file",
                    "agent_path": str(path),
                    "extension": path.suffix.lower(),
                    "size_bytes": path.stat().st_size,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Check 5 — oversized inline SVGs (>10% of viewport area)
# ---------------------------------------------------------------------------

_SVG_OPEN = re.compile(r"<\s*svg\b([^>]*)>", re.IGNORECASE)
_SVG_CLOSE = re.compile(r"</\s*svg\s*>", re.IGNORECASE)
_WIDTH_ATTR = re.compile(r'\bwidth\s*=\s*["\']?\s*(\d+(?:\.\d+)?)\s*(px|%)?', re.IGNORECASE)
_HEIGHT_ATTR = re.compile(r'\bheight\s*=\s*["\']?\s*(\d+(?:\.\d+)?)\s*(px|%)?', re.IGNORECASE)
_VIEWBOX_ATTR = re.compile(
    r'\bviewBox\s*=\s*["\']?\s*[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)', re.IGNORECASE
)

DEFAULT_VIEWPORT_AREA = 1440 * 900  # desktop default


def _parse_svg_dimensions(attrs: str, viewport_area: int) -> float | None:
    """Estimate SVG area in pixels from its attributes. Returns None if indeterminate."""
    viewport_w = int(viewport_area**0.5 * (1440 / 900))
    viewport_h = int(viewport_area / viewport_w) if viewport_w else 900

    w_match = _WIDTH_ATTR.search(attrs)
    h_match = _HEIGHT_ATTR.search(attrs)

    if w_match and h_match:
        w_unit = (w_match.group(2) or "px").lower()
        h_unit = (h_match.group(2) or "px").lower()
        # Percent dimensions are parent-container-relative; we cannot determine
        # the actual rendered area from HTML alone. Treat as indeterminate to
        # avoid false-positive flags on legitimate chart-tile SVGs declared
        # `<svg width="100%" height="100%" viewBox="...">`. Stage 2 follow-up:
        # read the rendered bbox from the candidate DOM dump instead.
        if w_unit == "%" or h_unit == "%":
            return None
        w_val, h_val = float(w_match.group(1)), float(h_match.group(1))
        return w_val * h_val

    vb = _VIEWBOX_ATTR.search(attrs)
    if vb:
        # viewBox without explicit width/height is also unreliable — the rendered
        # size still depends on parent. Skip to avoid more false positives.
        return None

    return None


def detect_oversized_svgs(
    html_dir: Path, viewport_area: int = DEFAULT_VIEWPORT_AREA,
) -> list[dict]:
    """Flag inline <svg> elements whose area exceeds 10% of the viewport."""
    threshold = viewport_area * 0.10
    out: list[dict] = []

    for path in html_dir.rglob("*"):
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue

        for m in _SVG_OPEN.finditer(text):
            attrs = m.group(1)
            area = _parse_svg_dimensions(attrs, viewport_area)
            if area is not None and area > threshold:
                out.append(
                    {
                        "check": "oversized_inline_svg",
                        "source": str(path),
                        "position": m.start(),
                        "estimated_area_px": area,
                        "viewport_area": viewport_area,
                        "ratio": round(area / viewport_area, 3),
                    }
                )
    return out


# ---------------------------------------------------------------------------
# Check 6 — oversized rendered SVGs (bbox from dom.json sidecar)
# ---------------------------------------------------------------------------
# Closes the gap left by `detect_oversized_svgs`: percent-width and viewBox-only
# SVGs are skipped by the HTML-attribute parser because their rendered size
# depends on the parent. The rendered bbox in dom.json is authoritative.

RENDERED_SVG_RATIO_THRESHOLD = 0.5      # SVG occupying >50% of viewport area
RENDERED_SVG_MIN_BODY_BYTES = 4096      # also require ≥4KB of inline SVG content


def _max_svg_body_bytes(agent_dir: Path, page_stem: str) -> int:
    """Largest <svg>...</svg> inner-body size (in bytes) found in the agent
    HTML for `page_stem`. Returns 0 if no HTML / no SVG. Used to gate the
    rendered-bbox check: a small decorative SVG stretched by CSS is not a cheat;
    a giant body of inline path data is.
    """
    if agent_dir is None:
        return 0
    candidates = list(agent_dir.rglob(f"{page_stem}.html")) + list(
        agent_dir.rglob(f"{page_stem}.htm")
    )
    biggest = 0
    for path in candidates:
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        for m in _SVG_OPEN.finditer(text):
            close = _SVG_CLOSE.search(text, m.end())
            body_len = (close.start() - m.end()) if close else (len(text) - m.end())
            if body_len > biggest:
                biggest = body_len
    return biggest


def detect_oversized_rendered_svgs(
    candidate_dir: Path,
    viewport_area: int = DEFAULT_VIEWPORT_AREA,
    ratio_threshold: float = RENDERED_SVG_RATIO_THRESHOLD,
    agent_dir: Path | None = None,
    min_body_bytes: int = RENDERED_SVG_MIN_BODY_BYTES,
) -> list[dict]:
    """Flag any <svg> in candidate dom.json files whose rendered bbox covers
    more than `ratio_threshold` of the viewport AND whose source HTML contains
    an inline <svg> body of at least `min_body_bytes`. The body-size gate
    distinguishes the 'design as one giant SVG' cheat (KB of path data) from
    legitimate decorative SVGs stretched by CSS over scrolling content.
    """
    out: list[dict] = []
    if candidate_dir is None or not candidate_dir.exists():
        return out
    for dom_path in candidate_dir.rglob("*.dom.json"):
        try:
            data = json.loads(dom_path.read_text())
        except Exception:
            continue
        # dom filename is "<page>.<viewport>.dom.json"; HTML is "<page>.html"
        page_stem = dom_path.name.split(".")[0]
        body_bytes = _max_svg_body_bytes(agent_dir, page_stem) if agent_dir else min_body_bytes
        for el in data.get("elements", []):
            if str(el.get("tag", "")).lower() != "svg":
                continue
            bb = el.get("bbox") or {}
            area = float(bb.get("w", 0) or 0) * float(bb.get("h", 0) or 0)
            ratio = area / viewport_area if viewport_area else 0.0
            if ratio > ratio_threshold and body_bytes >= min_body_bytes:
                out.append(
                    {
                        "check": "oversized_rendered_svg",
                        "source": str(dom_path),
                        "rendered_area_px": area,
                        "viewport_area": viewport_area,
                        "ratio": round(ratio, 3),
                        "svg_body_bytes": body_bytes,
                    }
                )
    return out


# ---------------------------------------------------------------------------
# Convenience: run everything in one call
# ---------------------------------------------------------------------------


def run_all_checks(
    agent_dir: Path,
    reference_dir: Path,
    render_meta: dict | None = None,
    viewport_area: int = DEFAULT_VIEWPORT_AREA,
    candidate_dir: Path | None = None,
) -> AnticheatResult:
    """Run all checks against the candidate output and return a
    combined AnticheatResult.

    `candidate_dir` is the rendered-output dir containing `*.dom.json` sidecars;
    if omitted, the rendered-SVG check is skipped.
    """
    return combine_violations(
        scan_html_css(agent_dir),
        detect_image_copies(agent_dir, reference_dir),
        detect_off_origin(render_meta or {}),
        detect_raster_images(agent_dir),
        detect_oversized_svgs(agent_dir, viewport_area),
        detect_oversized_rendered_svgs(candidate_dir, viewport_area, agent_dir=agent_dir) if candidate_dir else [],
    )
