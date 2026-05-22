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
    # ----- Easy baselines (well-known design systems) -----------------------
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
    # ----- Japanese traditional (wabi-sabi) ---------------------------------
    {
        "name": "nippon-wabi",
        "source": "hand-curated (Japanese traditional colors)",
        "light": {
            "bg": "#f5f0e6", "surface": "#faf7f0", "fg": "#2b2421",
            "fg_muted": "#6c6024", "border": "#d8d0c0",
            "accent": "#7b90b0", "accent_fg": "#f5f0e6",
            "success": "#6c6024", "danger": "#a04050",
        },
        "dark": {
            "bg": "#1e1c18", "surface": "#2a2720", "fg": "#e0d8c8",
            "fg_muted": "#b5a4a4", "border": "#3a362e",
            "accent": "#94a8c8", "accent_fg": "#1a1816",
            "success": "#8a8040", "danger": "#c06070",
        },
    },
    # ----- African textile / kente-inspired ---------------------------------
    {
        "name": "kente-bold",
        "source": "hand-curated (African textile-inspired)",
        "light": {
            "bg": "#f8f0e0", "surface": "#fffaf0", "fg": "#1a1208",
            "fg_muted": "#5c4a2e", "border": "#d8c8a0",
            "accent": "#cc7722", "accent_fg": "#1a1208",
            "success": "#2e6b40", "danger": "#b83020",
        },
        "dark": {
            "bg": "#141008", "surface": "#221c10", "fg": "#f0e4c8",
            "fg_muted": "#b8a878", "border": "#3a3018",
            "accent": "#e89830", "accent_fg": "#141008",
            "success": "#50a060", "danger": "#e05040",
        },
    },
    # ----- 70s retro earth (avocado + harvest gold) -------------------------
    {
        "name": "seventies-earth",
        "source": "hand-curated (70s retro)",
        "light": {
            "bg": "#f4efe0", "surface": "#faf6ea", "fg": "#3a3020",
            "fg_muted": "#6b6040", "border": "#d4c8a8",
            "accent": "#6b8e23", "accent_fg": "#faf6ea",
            "success": "#708238", "danger": "#a0522d",
        },
        "dark": {
            "bg": "#1e1c14", "surface": "#2a2818", "fg": "#e4dcc4",
            "fg_muted": "#a8a070", "border": "#3d3820",
            "accent": "#daa520", "accent_fg": "#1a1808",
            "success": "#8aaa50", "danger": "#c86840",
        },
    },
    # ----- Art deco (black + gold + emerald) --------------------------------
    {
        "name": "deco-noir",
        "source": "hand-curated (art deco)",
        "light": {
            "bg": "#f8f6f0", "surface": "#ffffff", "fg": "#1a1a18",
            "fg_muted": "#50504a", "border": "#c8c4b0",
            "accent": "#b8860b", "accent_fg": "#1a1a18",
            "success": "#1a6850", "danger": "#8b0000",
        },
        "dark": {
            "bg": "#0a0a08", "surface": "#181814", "fg": "#e8e4d0",
            "fg_muted": "#908c78", "border": "#2e2e24",
            "accent": "#daa520", "accent_fg": "#0a0a08",
            "success": "#2e9070", "danger": "#c04040",
        },
    },
    # ----- Scandinavian frost (ultra-muted, near-neutral) -------------------
    {
        "name": "scandi-frost",
        "source": "hand-curated (Scandinavian minimal)",
        "light": {
            "bg": "#f2f0ed", "surface": "#fafaf8", "fg": "#2a2826",
            "fg_muted": "#787470", "border": "#dcdad6",
            "accent": "#6e8898", "accent_fg": "#f2f0ed",
            "success": "#5a7a68", "danger": "#9a5050",
        },
        "dark": {
            "bg": "#1c1b19", "surface": "#262422", "fg": "#e2e0dc",
            "fg_muted": "#9a9894", "border": "#3a3836",
            "accent": "#88a2b4", "accent_fg": "#1c1b19",
            "success": "#78a088", "danger": "#c07070",
        },
    },
    # ----- Dusty rose + ink (desaturated feminine) --------------------------
    {
        "name": "dusty-rose-ink",
        "source": "hand-curated (desaturated feminine)",
        "light": {
            "bg": "#f8f2f0", "surface": "#fffafa", "fg": "#2a1f22",
            "fg_muted": "#6b5560", "border": "#dcd0d4",
            "accent": "#b07080", "accent_fg": "#fffafa",
            "success": "#5a8068", "danger": "#a04048",
        },
        "dark": {
            "bg": "#1e1618", "surface": "#2a2024", "fg": "#e8dce0",
            "fg_muted": "#a89098", "border": "#3a2e34",
            "accent": "#d090a0", "accent_fg": "#1e1618",
            "success": "#78a888", "danger": "#d07078",
        },
    },
    # ----- Ocean + brass (nautical luxury) ----------------------------------
    {
        "name": "ocean-brass",
        "source": "hand-curated (nautical luxury)",
        "light": {
            "bg": "#f0f2f6", "surface": "#fafbff", "fg": "#0e1b30",
            "fg_muted": "#4a5568", "border": "#c8ceda",
            "accent": "#1a3a5c", "accent_fg": "#f0f2f6",
            "success": "#2a7050", "danger": "#9a2828",
        },
        "dark": {
            "bg": "#0a1020", "surface": "#141c30", "fg": "#dce0e8",
            "fg_muted": "#8090a8", "border": "#243040",
            "accent": "#c0982a", "accent_fg": "#0a1020",
            "success": "#48a870", "danger": "#d06060",
        },
    },
    # ----- Indigo + coral (warm-cool tension) -------------------------------
    {
        "name": "indigo-coral",
        "source": "hand-curated (warm-cool tension)",
        "light": {
            "bg": "#f4f2f8", "surface": "#fdfcff", "fg": "#1a1430",
            "fg_muted": "#504868", "border": "#d0cce0",
            "accent": "#e07050", "accent_fg": "#1a1430",
            "success": "#3a8a58", "danger": "#b03030",
        },
        "dark": {
            "bg": "#12101e", "surface": "#1e1a2e", "fg": "#e4e0f0",
            "fg_muted": "#9890b0", "border": "#302a48",
            "accent": "#f09070", "accent_fg": "#12101e",
            "success": "#60b878", "danger": "#e06060",
        },
    },
]


def sample_palette(rng) -> Palette:
    return rng.choice(PALETTES)
