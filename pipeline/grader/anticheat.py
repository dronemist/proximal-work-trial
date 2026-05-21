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
     elements covering more than 10% of the viewport area.

Each returns `list[dict]` of violations. Use `combine_violations(*lists)` to
fold them into a single `AnticheatResult` with the multiplicative penalty.

We use a **flat 0.1× penalty if ANY violation fires**. One knob; easy to tune.
Flipping to hard-zero is a one-line change.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

VIOLATION_PENALTY = 0.1


# ---------------------------------------------------------------------------
# Result type + combiner
# ---------------------------------------------------------------------------

@dataclass
class AnticheatResult:
    penalty_multiplier: float
    violations: list[dict]
    counts: dict[str, int]


def combine_violations(*violation_lists: list[dict]) -> AnticheatResult:
    """Fold per-check violation lists into a single AnticheatResult.

    Counts are keyed by violation `check` field so consumers can break down
    failures by category in their logs.
    """
    all_v: list[dict] = []
    counts: dict[str, int] = {}
    for vs in violation_lists:
        for v in vs:
            all_v.append(v)
            counts[v.get("check", "unknown")] = counts.get(v.get("check", "unknown"), 0) + 1
    multiplier = VIOLATION_PENALTY if all_v else 1.0
    return AnticheatResult(penalty_multiplier=multiplier, violations=all_v, counts=counts)


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


def _scan_single_file(text: str, source_path: Path | None, kind: str) -> list[dict]:
    stripped = _strip_comments(text)
    out: list[dict] = []
    for m in _DATA_IMAGE_URI.finditer(stripped):
        out.append(
            {
                "check": "data_image_uri",
                "match": m.group(0),
                "position": m.start(),
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
        w_val, w_unit = float(w_match.group(1)), (w_match.group(2) or "px").lower()
        h_val, h_unit = float(h_match.group(1)), (h_match.group(2) or "px").lower()
        w_px = w_val / 100 * viewport_w if w_unit == "%" else w_val
        h_px = h_val / 100 * viewport_h if h_unit == "%" else h_val
        return w_px * h_px

    vb = _VIEWBOX_ATTR.search(attrs)
    if vb:
        return float(vb.group(1)) * float(vb.group(2))

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
# Convenience: run everything in one call
# ---------------------------------------------------------------------------


def run_all_checks(
    agent_dir: Path,
    reference_dir: Path,
    render_meta: dict | None = None,
    viewport_area: int = DEFAULT_VIEWPORT_AREA,
) -> AnticheatResult:
    """Run all checks against the candidate output and return a
    combined AnticheatResult.
    """
    return combine_violations(
        scan_html_css(agent_dir),
        detect_image_copies(agent_dir, reference_dir),
        detect_off_origin(render_meta or {}),
        detect_raster_images(agent_dir),
        detect_oversized_svgs(agent_dir, viewport_area),
    )
