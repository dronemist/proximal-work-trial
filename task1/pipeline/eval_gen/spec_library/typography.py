"""Curated typography pairings — SYSTEM FONTS ONLY.

Smoke-wave constraint: the agent's render at grade time has no internet
access, so the reference cannot use Google Fonts (would create an unwinnable
typography gap, and the anti-cheat detect_off_origin would fire on agents
that try to link them). Both the reference and the agent use the same
system-font stacks, matching what `reference_sites/001-landing/index.html`
already does.

Pilot wave will switch to inline `@font-face` with base64-encoded woff2
files. For smoke we stay with system stacks.

Each pairing supplies CSS font-family stack strings the generator pastes
directly into `font-family:` declarations.
"""
from __future__ import annotations

from typing import TypedDict


# System-font stacks — picked to match what's available on the Modal/Ubuntu
# render container plus macOS/Windows for cross-platform consistency.
SANS_SYSTEM = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
SERIF_SYSTEM = 'Georgia, "Times New Roman", "Liberation Serif", serif'
MONO_SYSTEM = 'ui-monospace, "SF Mono", Menlo, "DejaVu Sans Mono", Consolas, monospace'


class TypeFace(TypedDict):
    stack: str            # full CSS font-family value
    weight: int
    category: str         # "serif" | "sans-serif" | "monospace"


class TypePairing(TypedDict):
    name: str
    heading: TypeFace
    body: TypeFace
    mono: TypeFace
    scale: dict           # {"display": int, "h1": int, "h2": int, "body": int, "small": int}


PAIRINGS: list[TypePairing] = [
    {
        "name": "editorial-serif",
        "heading": {"stack": SERIF_SYSTEM, "weight": 700, "category": "serif"},
        "body": {"stack": SANS_SYSTEM, "weight": 400, "category": "sans-serif"},
        "mono": {"stack": MONO_SYSTEM, "weight": 400, "category": "monospace"},
        "scale": {"display": 60, "h1": 36, "h2": 24, "body": 16, "small": 13},
    },
    {
        "name": "utility-sans",
        "heading": {"stack": SANS_SYSTEM, "weight": 700, "category": "sans-serif"},
        "body": {"stack": SANS_SYSTEM, "weight": 400, "category": "sans-serif"},
        "mono": {"stack": MONO_SYSTEM, "weight": 400, "category": "monospace"},
        "scale": {"display": 56, "h1": 32, "h2": 22, "body": 15, "small": 13},
    },
    {
        "name": "dense-sans",
        "heading": {"stack": SANS_SYSTEM, "weight": 600, "category": "sans-serif"},
        "body": {"stack": SANS_SYSTEM, "weight": 400, "category": "sans-serif"},
        "mono": {"stack": MONO_SYSTEM, "weight": 400, "category": "monospace"},
        "scale": {"display": 48, "h1": 28, "h2": 20, "body": 14, "small": 12},
    },
    {
        "name": "mixed-serif-sans",
        "heading": {"stack": SERIF_SYSTEM, "weight": 600, "category": "serif"},
        "body": {"stack": SANS_SYSTEM, "weight": 400, "category": "sans-serif"},
        "mono": {"stack": MONO_SYSTEM, "weight": 400, "category": "monospace"},
        "scale": {"display": 58, "h1": 34, "h2": 24, "body": 16, "small": 14},
    },
    {
        "name": "mono-display",
        "heading": {"stack": MONO_SYSTEM, "weight": 700, "category": "monospace"},
        "body": {"stack": SANS_SYSTEM, "weight": 400, "category": "sans-serif"},
        "mono": {"stack": MONO_SYSTEM, "weight": 400, "category": "monospace"},
        "scale": {"display": 48, "h1": 28, "h2": 20, "body": 15, "small": 12},
    },
]


def sample_typography(rng) -> TypePairing:
    return rng.choice(PAIRINGS)
