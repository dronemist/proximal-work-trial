"""Spacing / radius / shadow scales — one family per generated site.

Sampling one whole family per site (rather than mixing) keeps the visual
rhythm coherent across pages. Each family is a self-contained set of tokens
the generator references in the brand spec.
"""
from __future__ import annotations

from typing import TypedDict


class SpacingFamily(TypedDict):
    name: str
    source: str
    space: list[int]      # px values, ordered smallest -> largest
    radius: dict[str, int]
    shadow: dict[str, str]


FAMILIES: list[SpacingFamily] = [
    {
        "name": "tailwind",
        "source": "Tailwind defaults (MIT)",
        "space": [4, 8, 12, 16, 24, 32, 48, 64, 96, 128],
        "radius": {"none": 0, "sm": 4, "md": 6, "lg": 8, "xl": 12, "2xl": 16, "full": 9999},
        "shadow": {
            "sm": "0 1px 2px rgba(0,0,0,0.05)",
            "md": "0 4px 6px -1px rgba(0,0,0,0.10), 0 2px 4px -2px rgba(0,0,0,0.06)",
            "lg": "0 10px 15px -3px rgba(0,0,0,0.10), 0 4px 6px -4px rgba(0,0,0,0.05)",
        },
    },
    {
        "name": "carbon",
        "source": "IBM Carbon (Apache 2.0)",
        "space": [2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96, 160],
        "radius": {"none": 0, "sm": 2, "md": 4, "lg": 8, "full": 9999},
        "shadow": {
            "sm": "0 1px 2px rgba(0,0,0,0.06)",
            "md": "0 2px 6px rgba(0,0,0,0.12)",
            "lg": "0 8px 24px rgba(0,0,0,0.16)",
        },
    },
    {
        "name": "polaris",
        "source": "Shopify Polaris (MIT)",
        "space": [4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128],
        "radius": {"none": 0, "sm": 4, "md": 8, "lg": 12, "xl": 16, "2xl": 20, "full": 9999},
        "shadow": {
            "sm": "0 1px 1px rgba(0,0,0,0.04)",
            "md": "0 2px 4px rgba(0,0,0,0.08), 0 0 1px rgba(0,0,0,0.04)",
            "lg": "0 4px 12px rgba(0,0,0,0.10), 0 0 1px rgba(0,0,0,0.04)",
        },
    },
    {
        "name": "material3",
        "source": "Material 3 (Apache 2.0)",
        "space": [4, 8, 12, 16, 24, 32, 40, 48, 56, 72, 96],
        "radius": {"none": 0, "xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 28, "full": 9999},
        "shadow": {
            "sm": "0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24)",
            "md": "0 3px 6px rgba(0,0,0,0.16), 0 3px 6px rgba(0,0,0,0.23)",
            "lg": "0 10px 20px rgba(0,0,0,0.19), 0 6px 6px rgba(0,0,0,0.23)",
        },
    },
]


def sample_spacing(rng) -> SpacingFamily:
    return rng.choice(FAMILIES)
