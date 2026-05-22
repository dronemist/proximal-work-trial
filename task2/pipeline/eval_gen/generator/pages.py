"""Stage 4 — generate each page as a standalone HTML file.

One LLM call per page. Each call gets:
- The brand spec (palette/typography/spacing names)
- The brief (one paragraph)
- The full component-library CSS (the anchor)
- This page's brief: title, purpose, required components
- Animation spec (if animated mode) or static constraint
- System-font stacks only (no Google Fonts, no external font links)

Output: complete `<!DOCTYPE html>` with a `<link rel="stylesheet" href="styles.css">`
referencing the shared library, plus inline `<style>` for any
page-specific tweaks. No `<script>` tags allowed.
"""
from __future__ import annotations

from pipeline.eval_gen.config import DEFAULT
from pipeline.eval_gen.generator.brand_spec import BrandSpec
from pipeline.eval_gen.generator.client import complete


_ANIMATION_CONSTRAINT_STATIC = """\
- **No animations or `@keyframes`.** Static page only. CSS `transition` on
  `:hover`/`:focus` is allowed (invisible in resting-state screenshot)."""

_ANIMATION_CONSTRAINT_ANIMATED = """\
- **Apply the CSS animation classes from styles.css** to appropriate elements.
  Use the `.animate-*` utility classes defined in the shared stylesheet for
  entrance animations. Apply stagger delays via `animation-delay` on individual
  elements or `:nth-child` rules in inline `<style>`. All animations must be
  CSS-only — no JavaScript.
- CSS `transition` on `:hover`/`:focus` is also allowed."""

SYSTEM_PROMPT_TEMPLATE = """\
You are an expert frontend engineer producing a single self-contained HTML
page that is part of a larger multi-page website. Every page on this site
links to the SAME `styles.css` (the component library) and shares the SAME
header navigation and footer.

OUTPUT FORMAT — exact:
```html
<!DOCTYPE html>
<html lang="en"[OPTIONAL data-theme="dark" if this page is the dark-mode variant]>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>...</title>
<link rel="stylesheet" href="styles.css">
<style>
  /* page-specific tweaks ONLY — minimal */
</style>
</head>
<body>
  ...
</body>
</html>
```

CRITICAL CONSTRAINTS:
- **Mobile-first responsive.** The shared `styles.css` is written
  mobile-first: defaults target 375px, with `@media (min-width: 768px)`
  and `@media (min-width: 1024px)` for wider layouts. Your page-specific
  `<style>` must follow the same pattern — default CSS for mobile,
  `min-width` queries to enhance for wider screens. Any page-specific
  grids (stat rows, filter bars, multi-column sections) must stack to a
  single column by default and only expand in `min-width` queries.
  **No element may cause horizontal scrolling at 375px.**
  **Grid / flex overflow rules (CRITICAL):** Every grid child must have
  `min-width: 0` — without it, content overflows the grid track at narrow
  viewports. Every flex child that contains text or tables: `min-width: 0`.
  Any element with `min-width: <N>px` (e.g., tables, heatmaps) MUST be
  inside a wrapper with `overflow-x: auto; max-width: 100%;` so the
  fixed width scrolls inside the wrapper instead of expanding the page.
  Never set `min-width` on a layout-level element without an overflow
  wrapper.
- HTML + CSS only. **No JavaScript**. No `<script>` tag may appear. No event
  handlers (`onclick=`, etc.). No JS-driven anything.
{animation_constraint}
- **Use the component classes defined in the shared `styles.css`** —
  `.btn`, `.btn--primary`, `.card`, `.nav`, `.input`, `.table`, `.dialog`,
  `.kpi`, etc. Inline `<style>` is for page-specific layout (grids,
  data visualizations, charts, heatmaps) — not for re-styling the
  shared components' colors, fonts, or spacing.
- **No external resources of any kind.** The ONLY allowed `<link>` is the
  relative `styles.css`. Specifically forbidden: any `<link>` to
  fonts.googleapis.com or any CDN; any `@import url(...)`; any `@font-face`
  with a URL source; any http(s):// `url(...)` in CSS; any inline base64
  data URI for images.
- **System fonts only** — the shared styles.css already uses system-font
  stacks. Do not override `font-family` to anything else in inline styles.
- **Images**: for any image slot, render an inline `<svg>` placeholder OR a
  `<div>` styled as a placeholder via CSS (`background-color`, `aspect-ratio`).
  Inline `<svg>` for icons is preferred and encouraged.
- **Header + footer** must be byte-identical across every page of the site
  (same nav items, same logo treatment). Repeat them verbatim.
- **Interactive-looking components** are rendered in their visible static
  state: tabs show the active tab's panel; modals are shown via `<dialog open>`;
  dropdowns are closed; toasts visible in their default position; tooltips
  hidden by default (use `:hover` to reveal).
- **Realistic content**: do NOT use lorem ipsum. Write plausible domain-
  appropriate copy: real-looking names, dates, numeric values, product
  descriptions. Vary it across pages.
- **Accessibility**: semantic HTML (`<nav>`, `<main>`, `<section>`, `<article>`,
  proper heading hierarchy), `aria-label` where needed, `:focus-visible`
  styling, skip-to-content link.

Output ONLY the HTML, wrapped in a single ```html code fence. No prose.
"""


def make_user_content(
    spec: BrandSpec,
    brief: str,
    library_css: str,
    page: dict,
    other_pages: list[dict],
    is_dark: bool,
    previous_issues: list[str] | None = None,
) -> list[dict]:
    """Build the user content as a list of content blocks.

    The brief and the component library are constant across pages of the
    same site, so we mark them with `cache_control: ephemeral` — subsequent
    pages of this site hit the prompt cache (90% discount on those tokens,
    5-minute TTL). The per-page block at the end is what varies.
    """
    other_titles = ", ".join(f"{p['title']}: {p['slug']}.html" for p in other_pages)
    dark_note = (
        "\nIMPORTANT: This page is the DARK-MODE variant. Add `data-theme=\"dark\"`\n"
        "to the <html> element. The shared styles.css already defines the dark\n"
        "palette under `:root[data-theme='dark']`."
        if is_dark else ""
    )

    site_preamble = (
        f"Site: {spec.business_name} ({spec.domain['label']})\n\n"
        f"PAGES ON THIS SITE (use these slugs for relative links in the nav):\n"
        f"{other_titles}\n"
    )

    brief_block = f"CREATIVE BRIEF (applies to all pages):\n{brief}\n"

    library_block = (
        "SHARED COMPONENT LIBRARY (styles.css — already shipped at /styles.css;\n"
        "DO NOT inline it, just `<link>` to it):\n\n"
        f"```css\n{library_css}\n```\n"
    )

    retry_note = ""
    if previous_issues:
        issues_list = "\n".join(f"  - {iss}" for iss in previous_issues)
        retry_note = (
            "\nPREVIOUS ATTEMPT FAILED VALIDATION. Fix these specific issues:\n"
            f"{issues_list}\n\n"
            "DEBUGGING CHECKLIST for horizontal overflow:\n"
            "1. Search your inline <style> for any grid container — every grid child\n"
            "   MUST have `min-width: 0` or content will overflow the track.\n"
            "2. Any element with a fixed `min-width` or `width` in px MUST be inside\n"
            "   a wrapper with `overflow-x: auto; max-width: 100%`.\n"
            "3. Flex children with text: add `min-width: 0`.\n"
            "4. Default (no media query) CSS must work at 375px — multi-column grids\n"
            "   must be `grid-template-columns: 1fr` by default.\n\n"
            "Re-emit the entire HTML page with these fixes applied. No explanation.\n"
        )

    animation_note = ""
    if spec.animation_spec:
        from pipeline.eval_gen.spec_library.animations import format_animation_spec_for_prompt
        animation_note = (
            "\n\nANIMATION INSTRUCTIONS:\n"
            "Apply the animation utility classes from styles.css to elements on this page.\n"
            f"{format_animation_spec_for_prompt(spec.animation_spec)}\n"
            "Use the `.animate-*` classes from styles.css. For staggered groups (e.g.,\n"
            "cards in a grid), set incremental `animation-delay` via inline style or\n"
            "`:nth-child` rules in the page's `<style>` block.\n"
        )

    page_block = (
        f"THIS PAGE: {page['title']} ({page['slug']}.html)\n"
        f"Purpose: {page['purpose']}\n\n"
        "REQUIRED COMPONENTS for this page (pick the ones that make sense for the\n"
        "purpose; you may add more):\n"
        "- Top navigation with the business name as a logo + links to all other pages\n"
        "- A primary headline appropriate to the page purpose\n"
        "- The main content body — use as many of `.card`, `.table`, `.kpi`,\n"
        "  `.timeline`, `.kanban`, `.calendar`, `.dialog`, `.dropdown`, `.tabs`,\n"
        "  `.accordion`, `.empty-state` as fit the purpose\n"
        "- Footer with copyright, social links, and links back to other pages\n\n"
        f"Layout grammar to follow: {spec.archetype['description']}\n"
        f"{dark_note}{animation_note}{retry_note}\n\n"
        "Now write the complete HTML page. Single ```html block, no other text.\n"
    )

    return [
        {"type": "text", "text": site_preamble},
        # Brief is identical across this site's pages → cacheable
        {"type": "text", "text": brief_block, "cache_control": {"type": "ephemeral"}},
        # Library is the big chunk and identical across this site's pages → cacheable
        {"type": "text", "text": library_block, "cache_control": {"type": "ephemeral"}},
        # Per-page block (varies)
        {"type": "text", "text": page_block},
    ]


def generate_page(
    spec: BrandSpec,
    brief: str,
    library_css: str,
    page: dict,
    other_pages: list[dict],
    is_dark: bool = False,
    cfg=DEFAULT,
    previous_issues: list[str] | None = None,
) -> dict:
    user_content = make_user_content(
        spec, brief, library_css, page, other_pages, is_dark, previous_issues=previous_issues,
    )
    anim_constraint = (
        _ANIMATION_CONSTRAINT_ANIMATED if spec.animation_spec
        else _ANIMATION_CONSTRAINT_STATIC
    )
    system = SYSTEM_PROMPT_TEMPLATE.format(animation_constraint=anim_constraint)

    result = complete(
        model=cfg.renderer_model,
        system=system,
        user=user_content,
        max_tokens=cfg.max_tokens_per_page,
        temperature=cfg.temperature,
    )
    if result.stop_reason == "max_tokens":
        print(f"    WARNING: page {page['slug']} hit max_tokens cap ({result.output_tokens}); HTML may be truncated")
    html = _extract_html(result.text)
    return {
        "html": html,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_s": result.latency_s,
        "stop_reason": result.stop_reason,
    }


def _extract_html(text: str) -> str:
    marker = "```html"
    if marker in text:
        start = text.index(marker) + len(marker)
        rest = text[start:]
        if "```" in rest:
            return rest[: rest.index("```")].strip()
        return rest.strip()
    return text.strip().removeprefix("```").removesuffix("```").strip()
