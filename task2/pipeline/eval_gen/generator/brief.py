"""Stage 2 — generate the creative brief from the brand spec.

Smoke-wave simplification: single call (no Verbalized Sampling). The brief
distills the brand spec into a short prose description that's reused in
every per-page prompt; this keeps Stage 4 prompts consistent across pages
of the same site without re-stating the whole spec each time.
"""
from __future__ import annotations

from pipeline.eval_gen.config import DEFAULT
from pipeline.eval_gen.generator.brand_spec import BrandSpec
from pipeline.eval_gen.generator.client import complete


SYSTEM_PROMPT_STATIC = """\
You are a senior product designer writing a concise creative brief for a
multi-page website. The brief will be passed to a different model that will
render each page as static HTML + CSS.

Output: 250-450 words. Plain prose, no headers, no bullet lists. Cover:
- The product and its target user (one sentence).
- The brand voice in 1-2 sentences (concrete: serious/playful, dense/airy, etc.).
- Visual identity: color usage (which roles get which colors), type hierarchy,
  spacing rhythm. Reference the supplied palette / typography / spacing family
  by name where helpful but don't list tokens — describe usage.
- The layout grammar: how pages share navigation, headers, footers. Be specific
  about where the nav sits, what the footer contains.
- 2-3 distinctive design touches that make this site feel coherent across
  pages (e.g., "every page uses a 8px grid with cards that have a 12px radius
  and a subtle bottom-only border").

Do NOT describe individual pages — that comes later. Do NOT mention specific
HTML tags or CSS properties; this is a designer's brief, not code.
"""

SYSTEM_PROMPT_ANIMATED = """\
You are a senior product designer writing a concise creative brief for a
multi-page website. The brief will be passed to a different model that will
render each page as HTML + CSS with CSS animations.

Output: 300-500 words. Plain prose, no headers, no bullet lists. Cover:
- The product and its target user (one sentence).
- The brand voice in 1-2 sentences (concrete: serious/playful, dense/airy, etc.).
- Visual identity: color usage (which roles get which colors), type hierarchy,
  spacing rhythm. Reference the supplied palette / typography / spacing family
  by name where helpful but don't list tokens — describe usage.
- The layout grammar: how pages share navigation, headers, footers. Be specific
  about where the nav sits, what the footer contains.
- The motion personality: describe how the site uses animation — is it restrained
  and subtle or energetic and playful? Which elements animate on load? What's
  the pacing and rhythm of the entrance animations? How do they reinforce the
  brand feel? The animation spec below lists the exact animations to use;
  describe how they should *feel* in context.
- 2-3 distinctive design touches that make this site feel coherent across
  pages (e.g., "every page uses a 8px grid with cards that have a 12px radius
  and a subtle bottom-only border").

Do NOT describe individual pages — that comes later. Do NOT mention specific
HTML tags or CSS properties; this is a designer's brief, not code.
"""


def make_user_prompt(spec: BrandSpec) -> str:
    from pipeline.eval_gen.spec_library.animations import format_animation_spec_for_prompt

    page_titles = ", ".join(p["title"] for p in spec.page_list)
    dark_note = (
        f"\nDark mode: pages {spec.dark_mode_pages} ship as a dark variant of the same design system."
        if spec.dark_mode_pages else ""
    )
    animation_note = ""
    if spec.animation_spec:
        animation_note = (
            f"\n\nANIMATION SPEC (CSS-only, load/entrance animations):\n"
            f"{format_animation_spec_for_prompt(spec.animation_spec)}"
        )
    return f"""\
Business: {spec.business_name}
Domain: {spec.domain['label']} ({spec.domain['industry']})
Layout grammar (use this as the structural backbone): {spec.archetype['description']}
Aesthetic hint: {spec.aesthetic_hint}

Palette source: {spec.palette['source']}; name: {spec.palette['name']}
Palette roles (light): {spec.palette['light']}
Typography (system-font stacks): heading category {spec.typography['heading']['category']} (weight {spec.typography['heading']['weight']}), body category {spec.typography['body']['category']} (weight {spec.typography['body']['weight']})
Spacing family: {spec.spacing['name']} — base scale {spec.spacing['space'][:5]}... px
Radius: {spec.spacing['radius']}

Pages on this site: {page_titles}{dark_note}{animation_note}

Write the brief now.
"""


def generate_brief(spec: BrandSpec, cfg=DEFAULT) -> dict:
    """Returns a dict with the brief text and a usage record."""
    user = make_user_prompt(spec)
    system = SYSTEM_PROMPT_ANIMATED if spec.animation_spec else SYSTEM_PROMPT_STATIC
    result = complete(
        model=cfg.brief_model,
        system=system,
        user=user,
        max_tokens=1500,
        temperature=0.9,
    )
    return {
        "brief": result.text,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_s": result.latency_s,
    }
