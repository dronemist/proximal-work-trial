"""Procedural business name generator. NAICS + adjective/noun cross-product.

No real company names; no trademark risk. The "industry" comes from the
domain (already NAICS-grounded); we just compose Adjective × Noun × Suffix.
"""
from __future__ import annotations

ADJECTIVES = [
    "Quiet", "Lattice", "Forge", "Marigold", "Drift", "Sable",
    "Ember", "Cobalt", "Slate", "Pioneer", "Beacon", "Junction",
    "Northwind", "Ember", "Granite", "Hazel", "Iris", "Loam",
    "Mosaic", "Onyx", "Pebble", "Quartz", "Reed", "Solstice",
    "Tamarisk", "Umber", "Vellum", "Willow", "Yarrow", "Zenith",
]

NOUNS = [
    "Labs", "Works", "Foundry", "Atlas", "Compass", "Harbor",
    "Bridge", "Vector", "Signal", "Pulse", "Field", "Junction",
    "Anchor", "Cipher", "Echo", "Forge", "Grove", "Helm",
]

SUFFIXES = [
    "Co", "Studio", "Works", "Group", "Systems", "Lab", "Foundry",
]


def sample_business_name(rng) -> str:
    adj = rng.choice(ADJECTIVES)
    noun = rng.choice(NOUNS)
    suffix = rng.choice(SUFFIXES)
    return f"{adj} {noun} {suffix}"
