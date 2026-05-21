"""
Phase 1 anti-cheat: two static-analysis checks on the agent's HTML/CSS.

Returns a multiplicative penalty in (0.0, 1.0]. 1.0 = no violation.
For Phase 1 we use a **flat 0.1× penalty if ANY violation fires**. Simpler than
per-violation decay; one knob to tune; matches the R4 graded-penalty direction.
Flipping to hard-zero is a one-line change once R4 is user-confirmed.

Phase 2+ will add:
  - inline SVG reproductions (>50KB or >70% viewport)
  - <object>, <embed>
  - render-time race conditions (post-screenshot mutation check)
  - font-loading races
  - OCR adversarial text / Unicode lookalikes
  - print-vs-screen media split
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

VIOLATION_PENALTY = 0.1

# Strip <!-- ... --> HTML comments and /* ... */ CSS comments before scanning so
# agents writing legitimate comments like "<!-- no iframe used -->" aren't flagged.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# data:<image-mime>... in any context — HTML src/href, CSS url(), srcset, etc.
# Also matches CSS data:image/svg+xml,... and url("data:..."). Phase 1 scope:
# we deliberately do not over-match into legit base64-encoded inline-script
# blobs, since the agent has no need for those in a pure HTML/CSS task.
_DATA_IMAGE_URI = re.compile(
    r"""data:image/[a-zA-Z0-9.+\-]+[;,]""", re.IGNORECASE
)

# Real iframe tag construction (matches `<iframe ` or `<iframe>` or `<iframe/`).
# `\b` would have matched `</iframe>` too — that's an iframe-USE indicator
# anyway, so keeping it inclusive. Excludes false-positives like `<iframescript>`
# by requiring a tag terminator.
_IFRAME_TAG = re.compile(r"<\s*iframe[\s>/]", re.IGNORECASE)


@dataclass
class AnticheatResult:
    penalty_multiplier: float
    violations: list[dict]


def _strip_comments(text: str, kind: str) -> str:
    if kind == "html":
        return _HTML_COMMENT.sub("", text)
    if kind == "css":
        return _CSS_COMMENT.sub("", text)
    return text


def check_html(html: str, source_path: Path | None = None, kind: str = "html") -> list[dict]:
    """Scan a single HTML or CSS string for violations.

    `kind` controls which comment-stripping pass to apply. For .html files we
    strip HTML comments AND CSS comments inside <style> blocks (cheap to strip
    both unconditionally).
    """
    stripped = _strip_comments(html, "html")
    stripped = _strip_comments(stripped, "css")

    violations: list[dict] = []

    for m in _DATA_IMAGE_URI.finditer(stripped):
        violations.append(
            {
                "check": "data_image_uri",
                "match": m.group(0),
                "position": m.start(),
                "source": str(source_path) if source_path else None,
            }
        )

    if kind == "html":
        for m in _IFRAME_TAG.finditer(stripped):
            violations.append(
                {
                    "check": "iframe",
                    "match": m.group(0),
                    "position": m.start(),
                    "source": str(source_path) if source_path else None,
                }
            )

    return violations


def check_directory(html_dir: Path) -> AnticheatResult:
    """Scan every .html and .css file under html_dir for violations."""
    all_violations: list[dict] = []
    for path in html_dir.rglob("*"):
        ext = path.suffix.lower()
        if ext not in {".html", ".htm", ".css"}:
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        kind = "html" if ext in {".html", ".htm"} else "css"
        all_violations.extend(check_html(text, source_path=path, kind=kind))

    multiplier = VIOLATION_PENALTY if all_violations else 1.0
    return AnticheatResult(penalty_multiplier=multiplier, violations=all_violations)
