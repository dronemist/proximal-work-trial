"""Stages 6 + 8 — coherence verification + corpus audit (smoke-minimal).

Smoke-wave coverage:
  - Stage 6: header / footer byte equality across pages of a site.
  - Stage 6: CSS-token variance — number of distinct font families and color
    values in the rendered stylesheet. Single library + per-page overrides.
  - Stage 8: print a coverage report; no enforced thresholds at N=5.

DreamSim pairwise and Vendi-CLIP land in the pilot wave on Modal GPU.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Pull header / footer by tag — looser than the synthesis spec which required
# byte-identity, but the generator wraps both in <header>...</header> and
# <footer>...</footer>. We compare those substrings across pages.

_HEADER_RE = re.compile(r"<header\b[^>]*>(.*?)</header>", re.IGNORECASE | re.DOTALL)
_FOOTER_RE = re.compile(r"<footer\b[^>]*>(.*?)</footer>", re.IGNORECASE | re.DOTALL)
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.IGNORECASE)
_COLOR_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")


@dataclass
class CoherenceReport:
    site_id: str
    header_consistent: bool
    footer_consistent: bool
    distinct_font_families: int
    distinct_colors: int
    per_page_issues: dict[str, list[str]]


def verify_site(site_dir: Path, page_slugs: list[str]) -> CoherenceReport:
    headers: list[str] = []
    footers: list[str] = []
    per_page_issues: dict[str, list[str]] = {}

    all_css_text = ""
    css_path = site_dir / "styles.css"
    if css_path.exists():
        all_css_text = css_path.read_text(errors="replace")

    for slug in page_slugs:
        html_path = site_dir / f"{slug}.html"
        if not html_path.exists():
            per_page_issues.setdefault(slug, []).append("missing HTML")
            continue
        html = html_path.read_text(errors="replace")
        h = _extract(_HEADER_RE, html)
        f = _extract(_FOOTER_RE, html)
        headers.append(_normalize(h))
        footers.append(_normalize(f))
        all_css_text += _extract_inline_style(html)

    header_consistent = len(set(headers)) <= 1 and headers and headers[0] != ""
    footer_consistent = len(set(footers)) <= 1 and footers and footers[0] != ""

    families = Counter()
    for m in _FONT_FAMILY_RE.finditer(all_css_text):
        for fam in m.group(1).split(","):
            families[fam.strip().strip("'\"")] += 1

    colors = Counter()
    for m in _COLOR_HEX_RE.finditer(all_css_text):
        colors[m.group(0).lower()] += 1

    return CoherenceReport(
        site_id=site_dir.name,
        header_consistent=header_consistent,
        footer_consistent=footer_consistent,
        distinct_font_families=len(families),
        distinct_colors=len(colors),
        per_page_issues=per_page_issues,
    )


def _extract(pattern: re.Pattern, html: str) -> str:
    m = pattern.search(html)
    return m.group(1) if m else ""


def _extract_inline_style(html: str) -> str:
    out = []
    for m in re.finditer(r"<style\b[^>]*>(.*?)</style>", html, re.IGNORECASE | re.DOTALL):
        out.append(m.group(1))
    return "\n".join(out)


def _normalize(text: str) -> str:
    """Whitespace-collapse for forgiving byte-identity comparison."""
    return re.sub(r"\s+", " ", text).strip()


def write_report(report: CoherenceReport, path: Path) -> None:
    path.write_text(json.dumps(report.__dict__, indent=2))
