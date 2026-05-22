"""Stage 3 — generate a per-site CSS component library.

The library is the "anchor" pattern (StoryDiffusion analog from research): a
single shared stylesheet that every page links to, defining brand tokens as
CSS custom properties + reusable component classes. By generating it once
per site and reusing it across pages, we get cross-page coherence "for free"
on the typography/color/spacing axes.
"""
from __future__ import annotations

from pipeline.eval_gen.config import DEFAULT
from pipeline.eval_gen.generator.brand_spec import BrandSpec
from pipeline.eval_gen.generator.client import complete


SYSTEM_PROMPT = """\
You are an expert CSS engineer producing a single shared stylesheet that
every page on a multi-page website will link to. The stylesheet defines:

1. **CSS custom properties** (`:root { --color-bg, --color-fg, ... }`) for
   every brand token (palette, typography, spacing, radius, shadow). Use
   semantic names, not raw values, in component styles.
2. **A `:root[data-theme="dark"]` block** overriding the palette tokens for
   dark mode (the page HTML opts in via `data-theme="dark"` on `<html>`).
3. **Base styles**: `*, *::before, *::after { box-sizing: border-box }`,
   sensible body defaults (font-family, line-height, color, background),
   `:focus-visible` ring, `prefers-reduced-motion` respect.
4. **Layout primitives** the pages will need: `.container`, `.stack`
   (vertical rhythm), `.grid-*`, `.row`, `.col`. Use modern CSS (flexbox,
   grid, gap, aspect-ratio).
5. **ONLY the component classes the pages in this site actually need.** The
   user message lists every page on this site with its purpose. Read those
   purposes carefully and emit ONLY the components that fit. **Do not
   produce CSS for components no page will use.** Use BEM-like class names
   (`.btn`, `.btn--primary`, `.card`, `.card__body`). Possible components
   to draw from when relevant: buttons, cards, nav, form inputs (text,
   select, checkbox, radio, toggle, multi-step), tables (incl. sortable /
   paginated / sticky-header variants), tabs, accordion (via
   `<details>`), `<dialog>` styling, dropdown, popover, tooltip, toast,
   skeleton, empty-state, KPI/stat card, timeline, kanban column,
   calendar grid, breadcrumbs, pagination, badge/chip, avatar.
6. **Utility classes** (small set): `.sr-only`, `.text-muted`, `.text-mono`,
   spacing utilities tied to the spacing scale.

CRITICAL CONSTRAINTS:

**MOBILE-FIRST RESPONSIVE CSS.**
Write all default styles for mobile (375px). Then progressively enhance:
  - `@media (min-width: 768px)` — tablet enhancements
  - `@media (min-width: 1024px)` — desktop enhancements

The golden rule: **default (no media query) CSS must produce a clean,
non-overflowing layout at 375px wide.** Everything wider is added via
`min-width` media queries. Never use `max-width` queries.

What this means in practice:
  - `.container`: `width: 100%; padding-inline: 16px;` by default.
    At ≥1024px add `max-width: 1280px; margin-inline: auto;`.
  - `.grid-2`, `.grid-3`, `.grid-4`: `grid-template-columns: 1fr` by
    default (stacked). At ≥768px: 2 columns. At ≥1024px: full column count.
  - **Grid overflow prevention (CRITICAL):** Every direct child of a CSS
    grid container MUST have `min-width: 0`. Without this, grid children
    default to `min-width: auto` and their content can overflow the track,
    breaking the layout at narrow viewports. Apply globally:
    `.grid-2 > *, .grid-3 > *, .grid-4 > * { min-width: 0; }`
    and on any custom layout grids (e.g., `.split > *`, two-column
    layouts, sidebar + main). Do NOT use `overflow: hidden` on layout
    containers — it clips shadows, tooltips, and dropdowns.
  - `.nav`: horizontal top bar by default (wrapping flex row). If the
    site's layout grammar calls for a sidebar (dashboards, admin panels),
    promote to a sticky left sidebar at ≥1024px. The parent must be a
    flex row so sticky works:
    ```
    .app-layout { display: flex; }
    .nav { position: sticky; top: 0; height: 100vh; overflow-y: auto;
           width: var(--nav-width); flex-shrink: 0; }
    .main-content { flex: 1; min-width: 0; }
    ```
    NEVER use `position: fixed` — fixed elements do not extend in
    full-page screenshots and will appear cut off. For non-sidebar
    sites, keep the nav as a simple top bar at all breakpoints.
  - `.table-wrap`: set `overflow-x: auto; max-width: 100%;` so tables
    scroll horizontally without expanding the page body. The inner
    `.table` may use `min-width` for readability — the wrapper contains it.
    Use `white-space: nowrap` on `th`/`td` ONLY if the table is inside
    `.table-wrap`; otherwise let text wrap naturally.
  - Never set `width`, `min-width`, or `flex-basis` to a fixed px value
    wider than 100% on layout elements. Use `max-width` + `width: 100%`
    or percentage-based sizing. Reserve `min-width` for elements INSIDE
    an `overflow-x: auto` wrapper only.
  - All flex containers: `flex-wrap: wrap` by default. All flex children
    that might contain text or tables: `min-width: 0`.

No element in this stylesheet may cause horizontal overflow at 375px.

- HTML+CSS only. NO JavaScript anywhere — no `<script>` tags, no event
  handlers, no JS-driven anything.
- NO animations or `@keyframes`. Only static `transition` on `:hover` /
  `:focus` is allowed (invisible in resting-state screenshots).
- **SYSTEM FONTS ONLY.** No `@import`, no `@font-face`, no link to
  fonts.googleapis.com or any external font source. Use the exact font-family
  stacks supplied in the spec verbatim — these are system-font stacks that
  resolve locally on the render container.
- NO external resources of any kind: no CDN images, no remote stylesheets,
  no http(s):// URLs in `url(...)` declarations, no data URIs.
- For dark mode use the `:root[data-theme="dark"]` selector (NOT
  `@media (prefers-color-scheme: dark)`) — the page HTML opts in via the
  `data-theme="dark"` attribute on `<html>`.

Output ONLY the CSS, wrapped in a single ```css code fence. Do not include
any HTML, HEAD, or LINK tags — just the stylesheet body. No surrounding prose.
"""


def make_user_prompt(spec: BrandSpec, brief: str) -> str:
    page_listing = "\n".join(
        f"- {p['title']} ({p['slug']}.html): {p['purpose']}"
        for p in spec.page_list
    )
    return f"""\
Site: {spec.business_name} ({spec.domain['label']})

PAGES ON THIS SITE (use these to decide which components to include — skip
components that no page will use):
{page_listing}

CREATIVE BRIEF:
{brief}

DESIGN TOKENS (use as CSS custom properties — exact values shown):

Palette (light):
{_format_palette(spec.palette['light'])}

Palette (dark — for `:root[data-theme="dark"]`):
{_format_palette(spec.palette['dark'])}

Typography (system-font stacks — paste exactly into `font-family:` declarations):
- heading: {spec.typography['heading']['stack']}     (weight {spec.typography['heading']['weight']}, {spec.typography['heading']['category']})
- body:    {spec.typography['body']['stack']}     (weight {spec.typography['body']['weight']}, {spec.typography['body']['category']})
- mono:    {spec.typography['mono']['stack']}     (weight {spec.typography['mono']['weight']})
- scale (px at desktop): {spec.typography['scale']}

Spacing scale (px): {spec.spacing['space']}
Radius (px): {spec.spacing['radius']}
Shadow tokens: {spec.spacing['shadow']}

Now write the complete stylesheet. **Include only the components the listed
pages will actually use** — a settings page doesn't need kanban; a docs
page doesn't need a calendar. Single ```css block, no other text.
"""


def _format_palette(p: dict) -> str:
    return "\n".join(f"  --color-{k.replace('_', '-')}: {v};" for k, v in p.items())


def generate_library(
    spec: BrandSpec,
    brief: str,
    cfg=DEFAULT,
    previous_issues: list[str] | None = None,
) -> dict:
    user = make_user_prompt(spec, brief)
    if previous_issues:
        bullets = "\n".join(f"  - {iss}" for iss in previous_issues)
        user += (
            "\n\nIMPORTANT — your previous attempt at this stylesheet failed validation. "
            "Fix EACH of the issues below in this revision:\n"
            f"{bullets}"
        )
    result = complete(
        model=cfg.library_model,
        system=SYSTEM_PROMPT,
        user=user,
        max_tokens=64_000,
        temperature=0.6,
    )
    if result.stop_reason == "max_tokens":
        print(f"    WARNING: library hit max_tokens cap ({result.output_tokens}); CSS may be truncated")
    css = _extract_css(result.text)
    return {
        "css": css,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_s": result.latency_s,
    }


def _extract_css(text: str) -> str:
    """Pull CSS out of a ```css fenced block. Falls back to the whole text."""
    marker = "```css"
    if marker in text:
        start = text.index(marker) + len(marker)
        rest = text[start:]
        if "```" in rest:
            return rest[: rest.index("```")].strip()
        return rest.strip()
    # Fallback — strip any trailing markdown leftover
    return text.strip().removeprefix("```").removesuffix("```").strip()
