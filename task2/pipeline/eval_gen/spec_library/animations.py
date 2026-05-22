"""Animation primitives — load/entrance CSS animations sampled per-site.

Each animation is a dict describing a CSS @keyframes animation to apply to
specific element types. Scope: load-triggered entrance animations only.
No hover, no scroll, no looping/ambient, no JS.

Primitives are combinatorially sampled at generation time, producing diverse
animation profiles from a small library — same pattern as palettes × typography.
"""
from __future__ import annotations

from typing import TypedDict


class AnimationPrimitive(TypedDict):
    name: str
    description: str
    css_keyframes: str
    properties: str  # the animation shorthand value (minus name)
    target_hint: str  # which elements this typically applies to


ENTRANCE_ANIMATIONS: list[AnimationPrimitive] = [
    {
        "name": "fade-in",
        "description": "Simple opacity fade from invisible to visible",
        "css_keyframes": "@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }",
        "properties": "fade-in {duration} {easing} {delay} both",
        "target_hint": "sections, cards, hero content",
    },
    {
        "name": "fade-up",
        "description": "Fade in while sliding up from below",
        "css_keyframes": "@keyframes fade-up { from { opacity: 0; transform: translateY(24px); } to { opacity: 1; transform: translateY(0); } }",
        "properties": "fade-up {duration} {easing} {delay} both",
        "target_hint": "cards, feature blocks, content sections",
    },
    {
        "name": "fade-down",
        "description": "Fade in while sliding down from above",
        "css_keyframes": "@keyframes fade-down { from { opacity: 0; transform: translateY(-24px); } to { opacity: 1; transform: translateY(0); } }",
        "properties": "fade-down {duration} {easing} {delay} both",
        "target_hint": "navigation, headers, top banners",
    },
    {
        "name": "fade-left",
        "description": "Fade in while sliding from the right",
        "css_keyframes": "@keyframes fade-left { from { opacity: 0; transform: translateX(32px); } to { opacity: 1; transform: translateX(0); } }",
        "properties": "fade-left {duration} {easing} {delay} both",
        "target_hint": "sidebar content, right-aligned elements",
    },
    {
        "name": "fade-right",
        "description": "Fade in while sliding from the left",
        "css_keyframes": "@keyframes fade-right { from { opacity: 0; transform: translateX(-32px); } to { opacity: 1; transform: translateX(0); } }",
        "properties": "fade-right {duration} {easing} {delay} both",
        "target_hint": "main content, left-aligned elements",
    },
    {
        "name": "scale-up",
        "description": "Grow from slightly smaller to full size with fade",
        "css_keyframes": "@keyframes scale-up { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }",
        "properties": "scale-up {duration} {easing} {delay} both",
        "target_hint": "hero images, cards, modal-like elements",
    },
    {
        "name": "scale-down",
        "description": "Shrink from slightly larger to full size with fade",
        "css_keyframes": "@keyframes scale-down { from { opacity: 0; transform: scale(1.08); } to { opacity: 1; transform: scale(1); } }",
        "properties": "scale-down {duration} {easing} {delay} both",
        "target_hint": "headlines, hero text, featured content",
    },
    {
        "name": "clip-reveal-up",
        "description": "Reveal content by animating a clip-path upward",
        "css_keyframes": "@keyframes clip-reveal-up { from { clip-path: inset(100% 0 0 0); } to { clip-path: inset(0 0 0 0); } }",
        "properties": "clip-reveal-up {duration} {easing} {delay} both",
        "target_hint": "images, hero sections, feature blocks",
    },
    {
        "name": "blur-in",
        "description": "Fade in from blurred to sharp",
        "css_keyframes": "@keyframes blur-in { from { opacity: 0; filter: blur(8px); } to { opacity: 1; filter: blur(0); } }",
        "properties": "blur-in {duration} {easing} {delay} both",
        "target_hint": "backgrounds, hero images, overlay content",
    },
    {
        "name": "rotate-in",
        "description": "Slight rotation with fade for a dynamic entrance",
        "css_keyframes": "@keyframes rotate-in { from { opacity: 0; transform: rotate(-3deg) translateY(16px); } to { opacity: 1; transform: rotate(0deg) translateY(0); } }",
        "properties": "rotate-in {duration} {easing} {delay} both",
        "target_hint": "cards, testimonials, decorative elements",
    },
]

AMBIENT_ANIMATIONS: list[AnimationPrimitive] = [
    {
        "name": "pulse",
        "description": "Gentle scale pulse that loops infinitely",
        "css_keyframes": "@keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }",
        "properties": "pulse {duration} {easing} {delay} infinite both",
        "target_hint": "CTA buttons, badges, notification dots",
    },
    {
        "name": "float",
        "description": "Subtle vertical float up and down",
        "css_keyframes": "@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }",
        "properties": "float {duration} {easing} {delay} infinite both",
        "target_hint": "decorative icons, hero illustrations, floating elements",
    },
    {
        "name": "shimmer",
        "description": "Background gradient shimmer sweep",
        "css_keyframes": "@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }",
        "properties": "shimmer {duration} linear {delay} infinite",
        "target_hint": "skeleton loaders, decorative dividers, accent borders",
    },
    {
        "name": "glow",
        "description": "Pulsing box-shadow glow effect",
        "css_keyframes": "@keyframes glow { 0%, 100% { box-shadow: 0 0 4px rgba(var(--glow-rgb, 99,102,241), 0.3); } 50% { box-shadow: 0 0 16px rgba(var(--glow-rgb, 99,102,241), 0.6); } }",
        "properties": "glow {duration} {easing} {delay} infinite both",
        "target_hint": "featured cards, active nav items, primary buttons",
    },
    {
        "name": "spin-slow",
        "description": "Slow continuous rotation",
        "css_keyframes": "@keyframes spin-slow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }",
        "properties": "spin-slow {duration} linear {delay} infinite",
        "target_hint": "loading indicators, decorative icons, gear/cog elements",
    },
]


STAGGER_PATTERNS: list[dict] = [
    {
        "name": "sequential",
        "description": "Each item delays by a fixed increment",
        "typical_step_ms": 80,
    },
    {
        "name": "cascade",
        "description": "Increasing delay gaps — first items appear fast, later ones slower",
        "typical_step_ms": 30,
    },
]

EASINGS = [
    "ease-out",
    "ease-in-out",
    "cubic-bezier(0.22, 1, 0.36, 1)",
    "cubic-bezier(0.33, 1, 0.68, 1)",
    "cubic-bezier(0.16, 1, 0.3, 1)",
    "cubic-bezier(0.65, 0, 0.35, 1)",
]

DURATION_RANGE = (300, 800)

COMPLEXITY_TIERS = {
    "simple": {"entrance": (1, 2), "ambient": (0, 1), "use_stagger": False},
    "medium": {"entrance": (2, 4), "ambient": (1, 2), "use_stagger": True},
    "hard":   {"entrance": (3, 5), "ambient": (2, 3), "use_stagger": True},
}


AMBIENT_DURATION_RANGE = (2000, 5000)


def sample_animation_spec(rng, complexity: str = "medium") -> dict:
    """Sample entrance + ambient animations for a site."""
    tier = COMPLEXITY_TIERS[complexity]
    easing = rng.choice(EASINGS)

    n_entrance = rng.randint(*tier["entrance"])
    selected = rng.sample(ENTRANCE_ANIMATIONS, min(n_entrance, len(ENTRANCE_ANIMATIONS)))
    entrance_out = []
    for i, anim in enumerate(selected):
        dur_ms = rng.randint(*DURATION_RANGE)
        base_delay_ms = i * rng.randint(50, 150)
        resolved_props = anim["properties"].format(
            duration=f"{dur_ms}ms",
            easing=easing,
            delay=f"{base_delay_ms}ms",
        )
        entrance_out.append({
            **anim,
            "resolved_properties": resolved_props,
            "duration_ms": dur_ms,
            "delay_ms": base_delay_ms,
            "easing": easing,
        })

    n_ambient = rng.randint(*tier["ambient"])
    ambient_selected = rng.sample(AMBIENT_ANIMATIONS, min(n_ambient, len(AMBIENT_ANIMATIONS)))
    ambient_out = []
    for anim in ambient_selected:
        dur_ms = rng.randint(*AMBIENT_DURATION_RANGE)
        resolved_props = anim["properties"].format(
            duration=f"{dur_ms}ms",
            easing=easing,
            delay="0ms",
        )
        ambient_out.append({
            **anim,
            "resolved_properties": resolved_props,
            "duration_ms": dur_ms,
            "delay_ms": 0,
            "easing": easing,
        })

    stagger = None
    if tier["use_stagger"] and selected:
        stagger = rng.choice(STAGGER_PATTERNS)

    return {
        "entrance_animations": entrance_out,
        "ambient_animations": ambient_out,
        "stagger": stagger,
        "easing": easing,
        "complexity": complexity,
    }


def format_animation_spec_for_prompt(spec: dict) -> str:
    """Format the animation spec as prose for inclusion in LLM prompts."""
    lines = []
    lines.append(f"Animation complexity: {spec['complexity']}")
    lines.append(f"Site-wide easing: {spec['easing']}")

    if spec["entrance_animations"]:
        lines.append("\nEntrance animations (fire once on page load, use `animation-fill-mode: both`):")
        for anim in spec["entrance_animations"]:
            lines.append(
                f"  - {anim['name']}: {anim['description']}. "
                f"Apply to: {anim['target_hint']}. "
                f"Duration: {anim['duration_ms']}ms, delay: {anim['delay_ms']}ms."
            )

    if spec.get("ambient_animations"):
        lines.append("\nAmbient animations (loop infinitely, subtle background motion):")
        for anim in spec["ambient_animations"]:
            lines.append(
                f"  - {anim['name']}: {anim['description']}. "
                f"Apply to: {anim['target_hint']}. "
                f"Duration: {anim['duration_ms']}ms, loops infinitely."
            )

    if spec["stagger"]:
        lines.append(
            f"\nStagger pattern: {spec['stagger']['name']} — {spec['stagger']['description']}. "
            f"Use animation-delay with ~{spec['stagger']['typical_step_ms']}ms increments "
            f"between sibling items (e.g., cards in a grid, list items). "
            f"Apply via nth-child or inline animation-delay on each item."
        )

    return "\n".join(lines)


def collect_keyframes_css(spec: dict) -> str:
    """Collect all @keyframes rules from the spec for inclusion in styles.css."""
    blocks = []
    seen = set()
    for anim in spec["entrance_animations"]:
        if anim["name"] not in seen:
            blocks.append(anim["css_keyframes"])
            seen.add(anim["name"])
    for anim in spec.get("ambient_animations", []):
        if anim["name"] not in seen:
            blocks.append(anim["css_keyframes"])
            seen.add(anim["name"])
    return "\n\n".join(blocks)
