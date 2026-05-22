"""Stage 1 — sample a brand spec.

Pure local sampling, no LLM calls. Domain × archetype × palette × typography
× spacing all sampled deterministically from the seed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Any

from pipeline.eval_gen.spec_library import (
    animations,
    archetypes,
    business_names,
    domains,
    palettes,
    spacing,
    typography,
)


@dataclass
class BrandSpec:
    site_id: str
    business_name: str
    domain: dict[str, Any]
    archetype: dict[str, Any]
    aesthetic_hint: str       # short prose hint passed to generator; intentionally NOT a named aesthetic family (decision: non-web visual seed eventually replaces this — for smoke, free-form)
    palette: dict[str, Any]
    typography: dict[str, Any]
    spacing: dict[str, Any]
    page_list: list[dict]
    dark_mode_pages: list[str] = field(default_factory=list)   # explicit list of page slugs rendered in dark mode
    animation_spec: dict = field(default_factory=dict)          # animation primitives sampled for this site (empty = static)

    @property
    def theme_mode(self) -> str:
        """Derived from dark_mode_pages + page_list.

        "light" — no pages dark.
        "dark"  — every page dark.
        "mixed" — some-but-not-all pages dark (the alternate-state pattern).
        """
        n_dark = len(self.dark_mode_pages)
        n_total = len(self.page_list)
        if n_dark == 0:
            return "light"
        if n_total > 0 and n_dark == n_total:
            return "dark"
        return "mixed"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["theme_mode"] = self.theme_mode   # surfaced in summaries / inspections
        return d


# Short aesthetic-hint phrases. NOT the Anthropic cookbook taxonomy.
# These are deliberately vague compositional cues so the LLM can't pattern-
# match to a known recipe. Replace with non-web visual seeds in pilot wave.
AESTHETIC_HINTS = [
    "calm muted neutrals with one bold accent, generous whitespace, restrained type contrast",
    "high-density information design, sharp 1px borders, subtle gradients only at decision points",
    "warm low-saturation palette, large rounded surfaces, friendly type with high x-height",
    "monochrome utility aesthetic, dense type, deliberate use of mono for numeric data",
    "soft pastel with rounded everything, gentle drop shadows, ample padding inside cards",
    "structured grid-led layout, strong type hierarchy, color used sparingly as wayfinding",
    "extreme type-size contrast — display-size headlines next to small dense body, no decoration",
    "card-heavy composition, every section bounded by a shadowed surface, minimal raw text on page background",
    "flat illustration-style — solid color blocks, no shadows, no gradients, no glows",
    "typographic-poster sensibility — oversized headers, asymmetric alignment, color used as graphic element",
    "sharp-cornered industrial look — 0 or 2px radius only, bold strokes, hairline dividers",
    "lush rich-color treatment — full-bleed surfaces in saturated brand tones, white reserved for content cards",
    "documentation-clean — three-pane structure feel, prose-first, color reserved for callouts",
    "marketing-bold — large hero proportions, generous vertical rhythm, oversized buttons",
    "data-product utility — table-and-form-dominant, every page has a primary action button in the top-right",
    "playful display aesthetic — irregular spacing, mixed type weights within a heading, color used as personality",
]


def _build_theme_mode_list(n_sites: int, rng: random.Random) -> list[str]:
    """Build a length-n_sites list of theme_modes with the target ratio
    (50% light, 30% dark, 20% mixed), then shuffle. Guarantees the exact
    distribution at every n_sites instead of relying on per-site rolls.
    """
    n_light = round(n_sites * 0.5)
    n_dark = round(n_sites * 0.3)
    n_mixed = n_sites - n_light - n_dark
    if n_mixed < 0:
        # Rounding overshoot — pull from light first, then dark.
        excess = -n_mixed
        n_light = max(0, n_light - excess)
        n_mixed = 0
    modes = ["light"] * n_light + ["dark"] * n_dark + ["mixed"] * n_mixed
    rng.shuffle(modes)
    return modes


def sample_brand_specs(
    n_sites: int,
    seed: int = 42,
    run_suffix: str = "",
) -> list[BrandSpec]:
    """Sample `n_sites` brand specs with cross-site diversity guarantees.

    For each axis (domain, archetype, palette, typography, spacing,
    aesthetic_hint, theme_mode), the pool/distribution is shuffled with a
    deterministic seed and then site i gets `pool[i % pool_size]`.
    theme_mode uses a fixed-ratio approach: a length-n list with exact
    50/30/20 counts (rounded) is shuffled and assigned per site.

      - When n_sites <= pool_size: every site gets a distinct value on that axis.
      - When n_sites > pool_size: values cycle (still deterministic).

    The shuffle seed folds in `run_suffix`, so repeated runs with different
    suffixes produce genuinely different site sets (not just renamed dirs).

    page_list and dark_mode_pages are NOT populated here — call
    `resolve_page_list(spec, n_pages, rng)` per site afterwards (which
    reads the already-decided spec.theme_mode).
    """
    shuffle_seed = f"{seed}-{run_suffix or 'default'}-shuffle"

    def _shuffled(pool: list, axis: str) -> list:
        # Per-axis RNG so adding a new axis later doesn't perturb others.
        out = list(pool)
        random.Random(f"{shuffle_seed}-{axis}").shuffle(out)
        return out

    palette_pool = _shuffled(palettes.PALETTES, "palette")
    typo_pool = _shuffled(typography.PAIRINGS, "typography")
    spacing_pool = _shuffled(spacing.FAMILIES, "spacing")
    domain_pool = _shuffled(domains.DOMAINS, "domain")
    arch_pool = _shuffled(archetypes.ARCHETYPES, "archetype")
    hint_pool = _shuffled(AESTHETIC_HINTS, "hint")
    theme_pool = _build_theme_mode_list(
        n_sites, random.Random(f"{shuffle_seed}-theme")
    )

    specs: list[BrandSpec] = []
    # Theme intent per site, paired with the spec for the caller to use when
    # invoking resolve_page_list. We don't store it on the BrandSpec — theme_mode
    # is a derived property of dark_mode_pages.
    out: list[tuple[BrandSpec, str]] = []
    for i in range(n_sites):
        idx = i + 1
        local_rng = random.Random(f"{seed}-{run_suffix}-name-{idx}")

        domain = domain_pool[i % len(domain_pool)]
        archetype = arch_pool[i % len(arch_pool)]
        palette = palette_pool[i % len(palette_pool)]
        typo = typo_pool[i % len(typo_pool)]
        spc = spacing_pool[i % len(spacing_pool)]
        aesthetic_hint = hint_pool[i % len(hint_pool)]
        theme_intent = theme_pool[i]
        name = business_names.sample_business_name(local_rng)

        site_id = f"{idx:03d}-{domain['name']}"
        if run_suffix:
            site_id = f"{site_id}-{run_suffix}"

        spec = BrandSpec(
            site_id=site_id,
            business_name=name,
            domain=domain,
            archetype=archetype,
            aesthetic_hint=aesthetic_hint,
            palette=palette,
            typography=typo,
            spacing=spc,
            page_list=[],
            dark_mode_pages=[],
        )
        specs.append(spec)
        out.append((spec, theme_intent))
    # Stash theme intent on a side-channel attribute for resolve_page_list to read.
    # Not a dataclass field — purely transient. resolve_page_list deletes it.
    for spec, intent in out:
        spec._theme_intent = intent   # type: ignore[attr-defined]
    return specs


def sample_brand_spec(idx: int, seed: int = 42, run_suffix: str = "") -> BrandSpec:
    """Single-site sampler — preserved for back-compat with callers that
    invoke per-site. Uses independent rng-based sampling (no cross-site
    uniqueness). For batches use `sample_brand_specs(n_sites, ...)` instead.
    """
    rng = random.Random(f"{seed}-{idx}")

    domain = domains.sample_domain(rng)
    archetype = archetypes.sample_archetype(rng)
    pal = palettes.sample_palette(rng)
    typo = typography.sample_typography(rng)
    spc = spacing.sample_spacing(rng)
    aesthetic_hint = rng.choice(AESTHETIC_HINTS)
    name = business_names.sample_business_name(rng)

    site_id = f"{idx:03d}-{domain['name']}"
    if run_suffix:
        site_id = f"{site_id}-{run_suffix}"

    return BrandSpec(
        site_id=site_id,
        business_name=name,
        domain=domain,
        archetype=archetype,
        aesthetic_hint=aesthetic_hint,
        palette=pal,
        typography=typo,
        spacing=spc,
        page_list=[],
        dark_mode_pages=[],
    )


def resolve_page_list(spec: BrandSpec, n_pages: int, rng: random.Random) -> None:
    """Populate spec.page_list with n_pages sampled from spec.domain, then
    set spec.dark_mode_pages based on the spec's theme intent. The intent
    was attached as `spec._theme_intent` by sample_brand_specs (transient).
    If absent (legacy callers), defaults to "light".

      - "light": dark_mode_pages = [] (all pages light)
      - "dark":  dark_mode_pages = every slug (all pages dark)
      - "mixed": dark_mode_pages = a subset chosen to make the site mostly
                 one theme with ONE page flipped. Tests theme switching.

    After this runs, spec.theme_mode (the @property) returns the same value
    derived from dark_mode_pages.
    """
    spec.page_list = domains.sample_page_list(rng, spec.domain, n_pages)
    if not spec.page_list:
        return

    intent = getattr(spec, "_theme_intent", "light")
    all_slugs = [p["slug"] for p in spec.page_list]

    if intent == "light":
        spec.dark_mode_pages = []
    elif intent == "dark":
        spec.dark_mode_pages = list(all_slugs)
    else:  # "mixed"
        flipped_slug = rng.choice(all_slugs)
        if rng.random() < 0.5:
            # light-dominant + one dark page
            spec.dark_mode_pages = [flipped_slug]
        else:
            # dark-dominant + one light page
            spec.dark_mode_pages = [s for s in all_slugs if s != flipped_slug]

    # Transient attribute no longer needed — clean up before serialization.
    if hasattr(spec, "_theme_intent"):
        del spec._theme_intent


def resolve_animation_spec(
    spec: BrandSpec, rng: random.Random, complexity: str = "medium"
) -> None:
    """Populate spec.animation_spec with sampled animation primitives.

    Call after resolve_page_list. Pass complexity="none" to leave static.
    """
    if complexity == "none":
        spec.animation_spec = {}
        return
    spec.animation_spec = animations.sample_animation_spec(rng, complexity)
