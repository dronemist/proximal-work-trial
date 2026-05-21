"""Curated color palettes for primitive seeding.

Smoke-wave subset only — each palette is a dict of semantic role -> hex. Sources
are all permissively licensed design systems (MIT / Apache 2.0). Expand from
research/primitive_sources.md before scaling beyond smoke.

Each palette has both light + (optional) dark variants. Dark mode is a Tier 1
priority in the coverage matrix, so most palettes ship both.
"""
from __future__ import annotations

from typing import TypedDict


class PaletteRoles(TypedDict, total=False):
    bg: str
    surface: str
    fg: str
    fg_muted: str
    border: str
    accent: str
    accent_fg: str
    success: str
    danger: str


class Palette(TypedDict):
    name: str
    source: str
    light: PaletteRoles
    dark: PaletteRoles


PALETTES: list[Palette] = [
    {
        "name": "primer-default",
        "source": "GitHub Primer (MIT)",
        "light": {
            "bg": "#ffffff",
            "surface": "#f6f8fa",
            "fg": "#1f2328",
            "fg_muted": "#59636e",
            "border": "#d1d9e0",
            "accent": "#0969da",
            "accent_fg": "#ffffff",
            "success": "#1a7f37",
            "danger": "#d1242f",
        },
        "dark": {
            "bg": "#0d1117",
            "surface": "#161b22",
            "fg": "#e6edf3",
            "fg_muted": "#8d96a0",
            "border": "#30363d",
            "accent": "#2f81f7",
            "accent_fg": "#ffffff",
            "success": "#3fb950",
            "danger": "#f85149",
        },
    },
    {
        "name": "carbon-gray-10",
        "source": "IBM Carbon (Apache 2.0)",
        "light": {
            "bg": "#f4f4f4",
            "surface": "#ffffff",
            "fg": "#161616",
            "fg_muted": "#525252",
            "border": "#e0e0e0",
            "accent": "#0f62fe",
            "accent_fg": "#ffffff",
            "success": "#198038",
            "danger": "#da1e28",
        },
        "dark": {
            "bg": "#161616",
            "surface": "#262626",
            "fg": "#f4f4f4",
            "fg_muted": "#a8a8a8",
            "border": "#393939",
            "accent": "#4589ff",
            "accent_fg": "#ffffff",
            "success": "#42be65",
            "danger": "#fa4d56",
        },
    },
    {
        "name": "polaris-cool",
        "source": "Shopify Polaris (MIT)",
        "light": {
            "bg": "#f1f2f4",
            "surface": "#ffffff",
            "fg": "#202223",
            "fg_muted": "#616a72",
            "border": "#c9cccf",
            "accent": "#00527c",
            "accent_fg": "#ffffff",
            "success": "#007f5f",
            "danger": "#b03930",
        },
        "dark": {
            "bg": "#1a1c1e",
            "surface": "#26282b",
            "fg": "#e3e5e7",
            "fg_muted": "#a0a3a6",
            "border": "#3a3d40",
            "accent": "#4d9ec9",
            "accent_fg": "#0a1620",
            "success": "#3aae8a",
            "danger": "#d57067",
        },
    },
    {
        "name": "material3-warm",
        "source": "Material 3 (Apache 2.0) — seeded #6750A4",
        "light": {
            "bg": "#fffbfe",
            "surface": "#f7f2fa",
            "fg": "#1c1b1f",
            "fg_muted": "#49454f",
            "border": "#cac4d0",
            "accent": "#6750a4",
            "accent_fg": "#ffffff",
            "success": "#386a20",
            "danger": "#b3261e",
        },
        "dark": {
            "bg": "#1c1b1f",
            "surface": "#2b2930",
            "fg": "#e6e1e5",
            "fg_muted": "#cac4d0",
            "border": "#49454f",
            "accent": "#d0bcff",
            "accent_fg": "#371e73",
            "success": "#b6f397",
            "danger": "#f2b8b5",
        },
    },
    {
        "name": "tailwind-slate",
        "source": "Tailwind CSS (MIT)",
        "light": {
            "bg": "#f8fafc",
            "surface": "#ffffff",
            "fg": "#0f172a",
            "fg_muted": "#475569",
            "border": "#e2e8f0",
            "accent": "#0ea5e9",
            "accent_fg": "#ffffff",
            "success": "#22c55e",
            "danger": "#ef4444",
        },
        "dark": {
            "bg": "#020617",
            "surface": "#0f172a",
            "fg": "#f1f5f9",
            "fg_muted": "#94a3b8",
            "border": "#334155",
            "accent": "#38bdf8",
            "accent_fg": "#082f49",
            "success": "#4ade80",
            "danger": "#f87171",
        },
    },
    # ----- Warm earth (terracotta + sage + cream) ----------------------------
    {
        "name": "terracotta-sage",
        "source": "hand-curated (warm earth)",
        "light": {
            "bg": "#fbf6ef", "surface": "#ffffff", "fg": "#332620",
            "fg_muted": "#6b5e57", "border": "#e3d8c8",
            "accent": "#c2542d", "accent_fg": "#ffffff",
            "success": "#5b7c52", "danger": "#a52a2a",
        },
        "dark": {
            "bg": "#2a1f1a", "surface": "#3a2d26", "fg": "#f0e4d5",
            "fg_muted": "#b8a89a", "border": "#4a3a30",
            "accent": "#e07854", "accent_fg": "#1a0f0a",
            "success": "#8aab7e", "danger": "#d97070",
        },
    },
    # ----- Forest + copper (nature) -----------------------------------------
    {
        "name": "forest-copper",
        "source": "hand-curated (nature)",
        "light": {
            "bg": "#f4f2ec", "surface": "#ffffff", "fg": "#1a2e1c",
            "fg_muted": "#5a6b5c", "border": "#d4d8c8",
            "accent": "#2f5d40", "accent_fg": "#f4f2ec",
            "success": "#5a8a4a", "danger": "#b85537",
        },
        "dark": {
            "bg": "#1a2419", "surface": "#26302a", "fg": "#e8e4d6",
            "fg_muted": "#a8b0a0", "border": "#3a4435",
            "accent": "#c97a3c", "accent_fg": "#1a1006",
            "success": "#7ba872", "danger": "#d97050",
        },
    },
    # ----- High-contrast monochrome + electric cyan -------------------------
    {
        "name": "mono-cyan",
        "source": "hand-curated (high-contrast B&W + neon)",
        "light": {
            "bg": "#ffffff", "surface": "#fafafa", "fg": "#000000",
            "fg_muted": "#525252", "border": "#d4d4d4",
            "accent": "#00d4ff", "accent_fg": "#001520",
            "success": "#00a86b", "danger": "#d62828",
        },
        "dark": {
            "bg": "#0a0a0a", "surface": "#1a1a1a", "fg": "#ffffff",
            "fg_muted": "#a3a3a3", "border": "#2a2a2a",
            "accent": "#22e0ff", "accent_fg": "#001520",
            "success": "#22c55e", "danger": "#ef4444",
        },
    },
    # ----- Editorial cream + black + red accent -----------------------------
    {
        "name": "editorial-red",
        "source": "hand-curated (literary/editorial)",
        "light": {
            "bg": "#f5f0e8", "surface": "#fffaf0", "fg": "#1a1a1a",
            "fg_muted": "#535047", "border": "#d8d2c4",
            "accent": "#c4302b", "accent_fg": "#fffaf0",
            "success": "#558b50", "danger": "#a02020",
        },
        "dark": {
            "bg": "#1a1814", "surface": "#26221b", "fg": "#e8e2d4",
            "fg_muted": "#a8a294", "border": "#3a342a",
            "accent": "#e85050", "accent_fg": "#1a0a0a",
            "success": "#7aab72", "danger": "#e85050",
        },
    },
    # ----- Deep navy + burnt orange + cream (mid-century editorial) ---------
    {
        "name": "midcentury-orange",
        "source": "hand-curated (mid-century editorial)",
        "light": {
            "bg": "#f0ece2", "surface": "#ffffff", "fg": "#1f2540",
            "fg_muted": "#5f6580", "border": "#d4d0c4",
            "accent": "#d4622f", "accent_fg": "#fff8ee",
            "success": "#3d7050", "danger": "#b03030",
        },
        "dark": {
            "bg": "#0f1428", "surface": "#1a2038", "fg": "#e8e4d4",
            "fg_muted": "#9098b0", "border": "#2a3050",
            "accent": "#e88040", "accent_fg": "#1f0a00",
            "success": "#60a070", "danger": "#e85050",
        },
    },
    # ----- Charcoal + mustard + cream ---------------------------------------
    {
        "name": "charcoal-mustard",
        "source": "hand-curated (charcoal + mustard)",
        "light": {
            "bg": "#f7f4ec", "surface": "#fffefa", "fg": "#252320",
            "fg_muted": "#5a5754", "border": "#dad6cc",
            "accent": "#d4a017", "accent_fg": "#1a1810",
            "success": "#557a40", "danger": "#a93a3a",
        },
        "dark": {
            "bg": "#1f1e1b", "surface": "#2c2a26", "fg": "#ede9dc",
            "fg_muted": "#b0aca0", "border": "#3d3a34",
            "accent": "#e8b830", "accent_fg": "#1a1408",
            "success": "#82a070", "danger": "#e87070",
        },
    },
    # ----- Mint + peach + ink (soft warm) -----------------------------------
    {
        "name": "mint-peach",
        "source": "hand-curated (soft warm)",
        "light": {
            "bg": "#f5fbf7", "surface": "#ffffff", "fg": "#1f3a2e",
            "fg_muted": "#5e7268", "border": "#d4e3d8",
            "accent": "#ff9580", "accent_fg": "#3d1810",
            "success": "#4a9970", "danger": "#d04040",
        },
        "dark": {
            "bg": "#152019", "surface": "#1f2c25", "fg": "#e0ede4",
            "fg_muted": "#9eb0a4", "border": "#2e3d35",
            "accent": "#ffb59a", "accent_fg": "#3d1810",
            "success": "#7ac49a", "danger": "#e87878",
        },
    },
    # ----- Slate + lime accent (utility + pop) ------------------------------
    {
        "name": "slate-lime",
        "source": "hand-curated (utility + pop)",
        "light": {
            "bg": "#f4f6f8", "surface": "#ffffff", "fg": "#1a1f24",
            "fg_muted": "#525a64", "border": "#d8dde2",
            "accent": "#88dd33", "accent_fg": "#1a2510",
            "success": "#22c55e", "danger": "#dc2626",
        },
        "dark": {
            "bg": "#10141a", "surface": "#1a2028", "fg": "#e8ecf0",
            "fg_muted": "#9ca5b0", "border": "#2a3038",
            "accent": "#a8e85a", "accent_fg": "#0a1502",
            "success": "#4ade80", "danger": "#f87171",
        },
    },
    # ----- Deep mauve + gold + cream (rich) ---------------------------------
    {
        "name": "mauve-gold",
        "source": "hand-curated (rich)",
        "light": {
            "bg": "#faf6f3", "surface": "#ffffff", "fg": "#3a2842",
            "fg_muted": "#6b5870", "border": "#dcd0d8",
            "accent": "#7a3d6d", "accent_fg": "#faf0f4",
            "success": "#558850", "danger": "#a83838",
        },
        "dark": {
            "bg": "#241a26", "surface": "#2f2532", "fg": "#ece2e8",
            "fg_muted": "#b09cab", "border": "#3d3340",
            "accent": "#c47a18", "accent_fg": "#1f1408",
            "success": "#7ab070", "danger": "#e07878",
        },
    },
    # ----- High-key pop (yellow + magenta + black) --------------------------
    {
        "name": "highkey-pop",
        "source": "hand-curated (bold high-key)",
        "light": {
            "bg": "#ffffff", "surface": "#ffffff", "fg": "#000000",
            "fg_muted": "#404040", "border": "#000000",
            "accent": "#ff00aa", "accent_fg": "#ffff00",
            "success": "#00cc66", "danger": "#ff0040",
        },
        "dark": {
            "bg": "#000000", "surface": "#0a0a0a", "fg": "#ffff00",
            "fg_muted": "#cccc88", "border": "#ffff00",
            "accent": "#ff44cc", "accent_fg": "#000000",
            "success": "#44ff88", "danger": "#ff4488",
        },
    },
]


def sample_palette(rng) -> Palette:
    return rng.choice(PALETTES)
