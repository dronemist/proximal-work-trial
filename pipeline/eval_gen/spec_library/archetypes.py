"""Layout archetypes — the grammar a domain's pages render in.

Each archetype is a one-sentence description that gets fed into the
generation prompt. The agent at eval-time never sees this label (Decision
#10) — it's purely a generation-side signal.
"""
from __future__ import annotations

from typing import TypedDict


class Archetype(TypedDict):
    name: str
    description: str


ARCHETYPES: list[Archetype] = [
    {"name": "dashboard-sidebar", "description": "Left sidebar navigation + top bar + multi-card body grid with KPIs and charts."},
    {"name": "data-dense-table", "description": "Header + filter bar + paginated dense data table with sortable columns."},
    {"name": "kanban-board", "description": "Horizontal kanban columns containing cards; column headers show counts."},
    {"name": "three-pane-docs", "description": "Left nav tree, center prose column, right table-of-contents."},
    {"name": "pricing-tiers", "description": "Hero with tagline, then 3-4 tier cards side-by-side, feature comparison table below."},
    {"name": "card-feed-masonry", "description": "Variable-height cards in 3-5 columns; Pinterest-style masonry."},
    {"name": "calendar-grid", "description": "Month/week calendar grid with events as colored blocks; sidebar for create."},
    {"name": "magazine-editorial", "description": "Large serif title, lead photo, multi-column body, pull quotes."},
    {"name": "swiss-grid", "description": "Strict 12-col modular grid, generous white space, numbered sections."},
    {"name": "asymmetric-hero", "description": "60/40 split hero text vs. image, off-axis composition."},
    {"name": "bento-grid", "description": "Irregular tile mosaic with large and small cards mixed; Apple-style."},
    {"name": "stripe-style-api-docs", "description": "Left endpoints nav, center description, right code samples."},
    {"name": "wizard-stepper", "description": "Top progress bar with numbered steps, single-question-per-screen with prev/next."},
    {"name": "map-first-results", "description": "Full-bleed map left, floating sidebar of results right."},
    {"name": "timeline-feed", "description": "Vertical chronological feed with timeline rail on the left edge."},
    {"name": "tree-explorer", "description": "Left tree of nested items, right detail panel; file-manager-like."},
    # Additional archetypes — broader layout coverage
    {"name": "stat-strip-grid", "description": "Top horizontal strip of large numeric stat cards, content body below in 2-3 columns."},
    {"name": "split-screen-marketing", "description": "50/50 vertical split: bold left half with color block + headline, right half with content."},
    {"name": "hero-with-tabs", "description": "Hero on top, then a tab strip switching between content panels below (rendered with active tab visible)."},
    {"name": "marquee-portfolio", "description": "Full-bleed alternating-direction rows of large project tiles, text captions between rows."},
    {"name": "command-palette-app", "description": "Top search/command bar dominant; results below as grouped sections."},
    {"name": "checklist-onboarding", "description": "Centered card with a progress checklist down the left, current step content on the right."},
    {"name": "data-explorer-three-pane", "description": "Left filters, center chart/table, right detail panel; data-tool style."},
    {"name": "feed-and-suggestions", "description": "Center column main feed with a fixed right-rail of suggestions / friends / trending widgets."},
    {"name": "comparison-matrix", "description": "Top-anchored comparison table with feature rows × product columns; sticky header."},
]


def sample_archetype(rng) -> Archetype:
    return rng.choice(ARCHETYPES)
