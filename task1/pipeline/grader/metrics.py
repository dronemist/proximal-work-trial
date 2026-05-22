"""
Grader metrics — v1, simplest version of each.

Four metrics, all return MetricResult with score in [0.0, 1.0]:

  1. ssim(ref_png, cand_png)
     SSIM with both-dim zero-padding + catastrophic-dim threshold.

  2. dom_structural(ref_dom, cand_dom)
     Tag-multiset Jaccard between the two dom.json dumps.

  3. palette(ref_dom, cand_dom)
     Set-Jaccard over distinct (color, background_color) values.

  4. typography(ref_dom, cand_dom)
     Set-Jaccard over distinct font-family values.

Composition lives in grade.py. METRIC_WEIGHTS below is the one knob.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment
from skimage.metrics import structural_similarity

# Six structured features with equal weights. VLM is intentionally absent —
# grade.py applies it as a min() ceiling on the structured mean, not as an
# averaged term. Overflow stays defined for diagnostics but with weight 0.
METRIC_WEIGHTS = {
    "text": 0.20,          # visible-text token similarity — wrong content is hardest to forgive
    "ssim": 0.15,          # pixel-level visual similarity
    "block_match": 0.15,   # bbox IoU after Hungarian matching
    "palette": 0.12,       # color similarity in OKLab — slightly-off colors hurt less than wrong text
    "typography": 0.10,    # font-family bucket + font-size hierarchy
    "position": 0.10,      # centroid drift after block matching — tertiary once blocks match
    "overflow": 0.0,       # applied as soft ceiling in grade.py (0.5 + 0.5*overflow_score), not in weighted mean
    "vlm_judge": 0.0,      # applied as min() ceiling in grade.py
}


@dataclass
class MetricResult:
    name: str
    score: float
    extra: dict


# ---------------------------------------------------------------------------
# 1. SSIM
# ---------------------------------------------------------------------------

def ssim(reference: Path, candidate: Path) -> MetricResult:
    """SSIM on a common top-left crop of size min(ref, cand) per axis.

    Cropping (instead of zero-padding to max dims) measures visual fidelity of
    the rendered overlap. Missed content is penalized separately by
    block_match / position; horizontal overflow is penalised by the `overflow`
    metric, which acts as a soft ceiling on the composite in grade.py.
    """
    ref = Image.open(reference).convert("RGB")
    cand = Image.open(candidate).convert("RGB")
    ref_arr = np.array(ref)
    cand_arr = np.array(cand)

    ref_h, ref_w = ref_arr.shape[:2]
    cand_h, cand_w = cand_arr.shape[:2]
    crop_h = min(ref_h, cand_h)
    crop_w = min(ref_w, cand_w)

    ref_crop = ref_arr[:crop_h, :crop_w, :]
    cand_crop = cand_arr[:crop_h, :crop_w, :]

    score, _ = structural_similarity(
        ref_crop, cand_crop, channel_axis=2, data_range=255, full=True
    )
    score = float(max(0.0, min(1.0, score)))
    return MetricResult(
        name="ssim",
        score=score,
        extra={
            "reference_size": [ref_w, ref_h],
            "candidate_size": [cand_w, cand_h],
            "compared_size": [crop_w, crop_h],
        },
    )




# ---------------------------------------------------------------------------
# DOM-dump loader (shared by 2/3/4)
# ---------------------------------------------------------------------------


def _load_dom(dom_path: Path) -> list[dict]:
    """Read the renderer's dom.json sidecar. Returns [] if missing/broken so
    metrics degrade to 0 rather than crashing the grader."""
    if not dom_path.exists():
        return []
    try:
        return json.loads(dom_path.read_text()).get("elements", [])
    except Exception:
        return []


def _set_jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# 2. Block-Match — Hungarian-matched bbox IoU
# ---------------------------------------------------------------------------
#
# For each element in reference and candidate we have its bounding box. We
# Hungarian-assign reference blocks to candidate blocks minimizing (1 - IoU),
# then aggregate the matched IoUs. Per-pair score is bbox IoU only — color
# and content are scored by separate metrics. N is capped at MAX_BLOCKS to
# keep Hungarian's O(N^3) tractable on large pages.


MAX_BLOCKS = 400


def _iou(a: dict, b: dict) -> float:
    ax, ay, aw, ah = a["x"], a["y"], a["w"], a["h"]
    bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _bboxes(elements: list[dict]) -> list[dict]:
    out = []
    for el in elements:
        b = el.get("bbox") or {}
        if all(k in b for k in ("x", "y", "w", "h")) and b["w"] > 0 and b["h"] > 0:
            out.append(b)
    # Sort by area desc so the head of the list is the most visually significant
    # elements; we cap to MAX_BLOCKS to keep Hungarian tractable.
    out.sort(key=lambda b: b["w"] * b["h"], reverse=True)
    return out[:MAX_BLOCKS]


def block_match(reference_dom: Path, candidate_dom: Path) -> MetricResult:
    ref = _bboxes(_load_dom(reference_dom))
    cand = _bboxes(_load_dom(candidate_dom))
    if not ref and not cand:
        return MetricResult(name="block_match", score=1.0, extra={"empty": True})
    if not ref or not cand:
        return MetricResult(
            name="block_match",
            score=0.0,
            extra={"reference_blocks": len(ref), "candidate_blocks": len(cand)},
        )

    n_ref, n_cand = len(ref), len(cand)
    # Cost matrix: 1 - IoU so Hungarian (which minimizes) maximizes IoU.
    cost = np.ones((n_ref, n_cand), dtype=np.float32)
    for i, r in enumerate(ref):
        for j, c in enumerate(cand):
            cost[i, j] = 1.0 - _iou(r, c)

    row_idx, col_idx = linear_sum_assignment(cost)
    matched_ious = [1.0 - cost[i, j] for i, j in zip(row_idx, col_idx)]

    # Calibration (R12 eyeball verdict): raw mean-IoU lands at ~0.34 even when
    # humans see a layout as "looks close." Two reasons:
    #   (1) IoU is geometrically harsh on shifts (a half-width offset gives
    #       IoU≈0.33 between same-size boxes), so a Claude output with
    #       ~20–40px shifts averages low even on visually-acceptable pages.
    #   (2) max(N_ref, N_cand) in the divisor adds a count-asymmetry penalty
    #       on top — when Claude over-creates wrappers, the matched IoUs are
    #       divided by N_cand rather than N_ref, ceiling-capping the score
    #       before any match-quality signal lands.
    # We address both: divide by min(N_ref, N_cand) (so count-asymmetry is
    # only logged in extras, not penalised in the score), and apply sqrt to
    # the final value so the operating range aligns with the other metrics
    # (0.34 → ~0.58). The raw IoU mean is still in extras for diagnostics.
    raw = sum(matched_ious) / min(n_ref, n_cand)
    score = float(raw ** 0.5)
    return MetricResult(
        name="block_match",
        score=score,
        extra={
            "reference_blocks": n_ref,
            "candidate_blocks": n_cand,
            "matched_pairs": len(matched_ious),
            "mean_matched_iou": float(np.mean(matched_ious)) if matched_ious else 0.0,
            "raw_score_before_sqrt": float(raw),
        },
    )


# ---------------------------------------------------------------------------
# 2b. Position-Match — centroid drift after Hungarian block matching
# ---------------------------------------------------------------------------
#
# After Hungarian-matching blocks by IoU, score by normalised centroid drift.
# IoU couples position with size; this isolates pure positional fidelity.
# Unmatched blocks on either side contribute the worst-case 1.0 normalised
# distance so the metric punishes both over- and under-creation of elements.


def position_match(reference_dom: Path, candidate_dom: Path) -> MetricResult:
    ref = _bboxes(_load_dom(reference_dom))
    cand = _bboxes(_load_dom(candidate_dom))
    if not ref and not cand:
        return MetricResult(name="position", score=1.0, extra={"empty": True})
    if not ref or not cand:
        return MetricResult(
            name="position", score=0.0,
            extra={"reference_blocks": len(ref), "candidate_blocks": len(cand)},
        )

    n_ref, n_cand = len(ref), len(cand)
    cost = np.ones((n_ref, n_cand), dtype=np.float32)
    for i, r in enumerate(ref):
        for j, c in enumerate(cand):
            cost[i, j] = 1.0 - _iou(r, c)
    row_idx, col_idx = linear_sum_assignment(cost)

    ref_w = max(b["x"] + b["w"] for b in ref)
    ref_h = max(b["y"] + b["h"] for b in ref)
    cand_w = max(b["x"] + b["w"] for b in cand)
    cand_h = max(b["y"] + b["h"] for b in cand)
    diag = float(np.hypot(max(ref_w, cand_w), max(ref_h, cand_h))) or 1.0

    norm_dists: list[float] = []
    for i, j in zip(row_idx, col_idx):
        r, c = ref[i], cand[j]
        rcx, rcy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
        ccx, ccy = c["x"] + c["w"] / 2, c["y"] + c["h"] / 2
        norm_dists.append(float(np.hypot(rcx - ccx, rcy - ccy) / diag))

    unmatched = abs(n_ref - n_cand)
    all_dists = norm_dists + [1.0] * unmatched
    mean_d = float(np.mean(all_dists)) if all_dists else 1.0
    score = float(max(0.0, min(1.0, 1.0 - mean_d)))
    return MetricResult(
        name="position",
        score=score,
        extra={
            "reference_blocks": n_ref,
            "candidate_blocks": n_cand,
            "matched_pairs": len(norm_dists),
            "mean_normalized_centroid_distance": mean_d,
            "page_diagonal_px": diag,
        },
    )


# ---------------------------------------------------------------------------
# 3. Palette — area-weighted Hungarian matching in OKLab
# ---------------------------------------------------------------------------
#
# Replaces the v0 exact-string Jaccard. We now:
#   1. Parse each element's color + background-color into sRGB
#   2. Convert to OKLab (perceptually-uniform)
#   3. Weight each color by the element's bbox area (big background ≫ tiny text)
#   4. Take the top-K colors per side
#   5. Hungarian-match between sides minimizing summed OKLab L2 distance
#      (the finite/discrete form of Earth Mover's Distance for equal-mass sets)
#   6. Score = 1 - (avg matched distance / NORMALIZER), clamped to [0, 1]
#
# Why Hungarian instead of full EMD: with K bounded (8 colors per side), Hungarian
# on a K×K matrix is exactly EMD up to mass-equalization. Avoids the POT dep.

PALETTE_TOP_K = 8
PALETTE_DIST_NORMALIZER = 0.15  # OKLab L2 threshold for "perceptually different identity"; ~15 JNDs
_RGB_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)")
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,8})$")


def _parse_color(s: str) -> tuple[int, int, int] | None:
    """Return (r, g, b) in 0..255 or None for transparent/unparseable."""
    if not s:
        return None
    s = s.strip().lower()
    if s in {"transparent", "none", "inherit", "initial"}:
        return None
    m = _RGB_RE.match(s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        alpha = float(m.group(4)) if m.group(4) is not None else 1.0
        if alpha <= 0.01:
            return None
        return (r, g, b)
    m = _HEX_RE.match(s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            r, g, b = (int(c * 2, 16) for c in h)
        elif len(h) in (6, 8):
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        else:
            return None
        return (r, g, b)
    return None


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb_to_oklab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Björn Ottosson's OKLab transform from 8-bit sRGB."""
    r, g, b = (_srgb_to_linear(v / 255.0) for v in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _aggregate_palette(
    elements: list[dict], field: str
) -> list[tuple[tuple[float, float, float], float]]:
    """Group colors from a single style field (e.g. "color" or "background_color")
    by quantized OKLab bucket, weighted by total bbox area where that color
    appeared. Aggregating fg and bg separately matters: on a dark-themed page,
    pooling text-color with background-color makes the (light) text dominate
    the area-weighted palette and falsely reports a "light" page.
    """
    buckets: dict[tuple[int, int, int], tuple[tuple[float, float, float], float]] = {}
    for el in elements:
        bbox = el.get("bbox") or {}
        area = float(bbox.get("w", 0)) * float(bbox.get("h", 0))
        if area <= 0:
            continue
        rgb = _parse_color(el.get(field, ""))
        if rgb is None:
            continue
        lab = _rgb_to_oklab(rgb)
        # Quantize bucket: 0.02 in L (resolution 50), 0.01 in a/b (resolution 100)
        key = (round(lab[0] / 0.02), round(lab[1] / 0.01), round(lab[2] / 0.01))
        existing = buckets.get(key)
        if existing is None:
            buckets[key] = (lab, area)
        else:
            buckets[key] = (existing[0], existing[1] + area)
    return sorted(buckets.values(), key=lambda x: -x[1])


def _score_palette_channel(
    ref_palette: list[tuple[tuple[float, float, float], float]],
    cand_palette: list[tuple[tuple[float, float, float], float]],
) -> tuple[float, dict]:
    """Score a single palette channel (fg or bg). Returns (score, extras)."""
    if not ref_palette and not cand_palette:
        return 1.0, {"empty": True}
    if not ref_palette or not cand_palette:
        return 0.0, {
            "reference_palette_size": len(ref_palette),
            "candidate_palette_size": len(cand_palette),
        }

    ref_top = ref_palette[:PALETTE_TOP_K]
    cand_top = cand_palette[:PALETTE_TOP_K]
    ref_total = sum(m for _, m in ref_top) or 1.0
    cand_total = sum(m for _, m in cand_top) or 1.0

    rect = np.zeros((len(ref_top), len(cand_top)), dtype=np.float32)
    for i, (r_lab, _) in enumerate(ref_top):
        for j, (c_lab, _) in enumerate(cand_top):
            rect[i, j] = (
                (r_lab[0] - c_lab[0]) ** 2
                + (r_lab[1] - c_lab[1]) ** 2
                + (r_lab[2] - c_lab[2]) ** 2
            ) ** 0.5

    row_idx, col_idx = linear_sum_assignment(rect)
    weighted_total = 0.0
    weight_total = 0.0
    for i, j in zip(row_idx, col_idx):
        ref_share = ref_top[i][1] / ref_total
        cand_share = cand_top[j][1] / cand_total
        pair_weight = (ref_share + cand_share) / 2.0
        weighted_total += pair_weight * rect[i, j]
        weight_total += pair_weight
    avg_weighted = float(weighted_total / max(weight_total, 1e-9))
    base = float(max(0.0, min(1.0, 1.0 - avg_weighted / PALETTE_DIST_NORMALIZER)))

    size_ratio = (
        max(len(ref_palette), len(cand_palette))
        / max(1, min(len(ref_palette), len(cand_palette)))
    )
    over_color_penalty = float(max(0.0, min(0.20, 0.08 * (size_ratio - 1.3))))
    score = float(max(0.0, base - over_color_penalty))
    return score, {
        "reference_palette_size": len(ref_palette),
        "candidate_palette_size": len(cand_palette),
        "weighted_mean_oklab_distance": avg_weighted,
        "base_score_before_penalty": base,
        "over_color_penalty": over_color_penalty,
    }


def palette(reference_dom: Path, candidate_dom: Path) -> MetricResult:
    """Average of background-palette and text-palette sub-scores.

    Splitting fg/bg is necessary because elements without an explicit
    background_color report rgba(0,0,0,0) (transparent) in computedStyle and
    get filtered out — leaving the candidate's text color to dominate the
    area-weighted palette pool. On a dark-themed page that means the light
    text color is reported as "the background," which makes any dark candidate
    look like a light reference.
    """
    ref_elems = _load_dom(reference_dom)
    cand_elems = _load_dom(candidate_dom)
    ref_bg = _aggregate_palette(ref_elems, "background_color")
    cand_bg = _aggregate_palette(cand_elems, "background_color")
    ref_fg = _aggregate_palette(ref_elems, "color")
    cand_fg = _aggregate_palette(cand_elems, "color")

    bg_score, bg_extra = _score_palette_channel(ref_bg, cand_bg)
    fg_score, fg_extra = _score_palette_channel(ref_fg, cand_fg)
    score = (bg_score + fg_score) / 2.0

    return MetricResult(
        name="palette",
        score=score,
        extra={
            "bg_score": bg_score,
            "fg_score": fg_score,
            "bg": bg_extra,
            "fg": fg_extra,
        },
    )


# ---------------------------------------------------------------------------
# 4. Typography — font-family bucket match + font-size hierarchy match
# ---------------------------------------------------------------------------
#
# Two-part score:
#   bucket_score: 1.0 if ref and cand both use the same font categories (serif
#     / sans / mono). Cheap sanity check — catches a monospace reference that
#     gets rendered in serif, but rarely fires for capable agents.
#   size_score:   how well the candidate reproduces the reference's distinct
#     font-size scale (e.g. 12/14/16/20/24/32/48 px). Computed via Hungarian
#     matching on px distance, weighted by element-share so a one-off size
#     doesn't dominate. This is the part that actually discriminates for RL.
#
# Combined: 0.3 * bucket_score + 0.7 * size_score


# Coarse classifier: maps a primary font-family name to one of three buckets.
# Same-bucket fonts look essentially identical to the eye for our purposes
# (e.g. "sf mono" vs "ui-monospace", "georgia" vs "iowan old style"), so
# bucketing avoids penalising the agent for choosing a different-but-equivalent
# fallback font.
_MONO_TOKENS = (
    "mono", "courier", "consolas", "menlo", "monaco", "jetbrains",
    "fira code", "source code", "roboto mono",
)
_SERIF_TOKENS = (
    "serif",  # plain "serif" generic family
    "georgia", "times", "garamond", "iowan", "palatino", "cambria",
    "book antiqua", "didot", "baskerville",
)


def _font_bucket(name: str) -> str:
    n = name.lower()
    if "sans-serif" in n or "sans serif" in n:
        return "sans"
    if any(tok in n for tok in _MONO_TOKENS):
        return "mono"
    if any(tok in n for tok in _SERIF_TOKENS):
        return "serif"
    return "sans"  # default for -apple-system, system-ui, inter, helvetica, …


def _collect_font_buckets(elements: list[dict]) -> tuple[set[str], set[str]]:
    """Return (bucket_set, primary_name_set) — buckets drive the score, primary
    names are kept for debug visibility in `extra`.
    """
    primaries: set[str] = set()
    for el in elements:
        fam = (el.get("font_family") or "").strip()
        if fam:
            primary = fam.split(",")[0].strip().strip('"').strip("'").lower()
            if primary:
                primaries.add(primary)
    buckets = {_font_bucket(p) for p in primaries}
    return buckets, primaries


def _collect_size_histogram(elements: list[dict], min_share: float = 0.01) -> list[tuple[float, float]]:
    """Return [(size_px, element_share), ...] for sizes used by at least
    `min_share` of visible elements. Filtered list prevents one-off accidental
    sizes from polluting the hierarchy comparison.
    """
    from collections import Counter
    sizes = [round(float(el.get("font_size_px") or 0), 1) for el in elements]
    sizes = [s for s in sizes if s > 0]
    if not sizes:
        return []
    total = len(sizes)
    counts = Counter(sizes)
    return sorted(
        ((sz, c / total) for sz, c in counts.items() if c / total >= min_share),
        key=lambda x: x[0],
    )


def _size_hierarchy_score(ref_hist: list[tuple[float, float]], cand_hist: list[tuple[float, float]]) -> float:
    """Hungarian-match ref sizes ↔ cand sizes on px distance, weighted by
    element-share. Score = 1 - mean_normalized_distance, clipped to [0, 1].

    Normalization: px distance / 24 (one typographic step). A 0-px gap → 1.0,
    a 24-px gap (e.g. ref 16px ↔ cand 40px) → 0.0.
    """
    from scipy.optimize import linear_sum_assignment

    if not ref_hist or not cand_hist:
        return 0.0
    n_ref, n_cand = len(ref_hist), len(cand_hist)
    n = max(n_ref, n_cand)
    cost = np.full((n, n), 24.0)  # padding = worst-case distance
    for i, (rs, _) in enumerate(ref_hist):
        for j, (cs, _) in enumerate(cand_hist):
            cost[i, j] = min(24.0, abs(rs - cs))
    row, col = linear_sum_assignment(cost)
    # Weight each pair by combined element-share. Unmatched (padded) rows
    # contribute their worst-case 24px distance.
    pair_dists = []
    pair_weights = []
    for i, j in zip(row, col):
        if i < n_ref and j < n_cand:
            w = (ref_hist[i][1] + cand_hist[j][1]) / 2
        else:
            # unmatched: penalise but with low weight (shape of the unmatched side)
            w_ref = ref_hist[i][1] if i < n_ref else 0
            w_cand = cand_hist[j][1] if j < n_cand else 0
            w = max(w_ref, w_cand)
        pair_dists.append(cost[i, j])
        pair_weights.append(w)
    total_w = sum(pair_weights)
    if total_w <= 0:
        return 0.0
    mean_norm = sum(d * w for d, w in zip(pair_dists, pair_weights)) / total_w / 24.0
    return float(max(0.0, min(1.0, 1.0 - mean_norm)))


def typography(reference_dom: Path, candidate_dom: Path) -> MetricResult:
    ref = _load_dom(reference_dom)
    cand = _load_dom(candidate_dom)
    ref_buckets, ref_names = _collect_font_buckets(ref)
    cand_buckets, cand_names = _collect_font_buckets(cand)
    bucket_score = _set_jaccard(ref_buckets, cand_buckets)

    ref_hist = _collect_size_histogram(ref)
    cand_hist = _collect_size_histogram(cand)
    size_score = _size_hierarchy_score(ref_hist, cand_hist)

    combined = 0.3 * bucket_score + 0.7 * size_score
    return MetricResult(
        name="typography",
        score=float(combined),
        extra={
            "bucket_score": bucket_score,
            "size_score": size_score,
            "reference_buckets": sorted(ref_buckets),
            "candidate_buckets": sorted(cand_buckets),
            "reference_size_hist": ref_hist,
            "candidate_size_hist": cand_hist,
            "reference_fonts": sorted(ref_names),
            "candidate_fonts": sorted(cand_names),
        },
    )


# ---------------------------------------------------------------------------
# 5. Overflow — penalise candidates whose horizontal content exceeds viewport
# ---------------------------------------------------------------------------
#
# Detection uses `document.documentElement.scrollWidth` captured during the
# render and stored under the dom.json sidecar's `page` key. This is the
# total rightmost extent of the page's content — it catches BOTH visibly-
# rendered overflow AND content that was clipped by `overflow:hidden` (which
# a PNG-width comparison would miss, since the PNG would stay at viewport
# width).
#
# Allowance = max(viewport_width, reference_scrollWidth). The candidate gets
# a free pass to overflow up to the reference's own scrollWidth — some
# legitimate designs have wide elements (long code blocks, full-bleed
# graphics) — and is penalised linearly past that.
#
# Empty / near-empty candidates return score=None so the composer drops the
# metric: an empty page can't overflow but also can't replicate the design,
# and we don't want the vacuous "no overflow detected" to credit the page.

OVERFLOW_PENALTY_SLOPE = 2.0     # 1 unit of overflow ratio costs 2× score
OVERFLOW_MIN_ELEMENTS = 5        # candidates with <5 visible elements → None


def overflow(
    candidate_dom: Path,
    reference_dom: Path,
    viewport_width: int,
    candidate_png: Path | None = None,
    reference_png: Path | None = None,
) -> MetricResult:
    cand_data = _load_dom_full(candidate_dom)
    ref_data = _load_dom_full(reference_dom)
    cand_elements = cand_data.get("elements") or []

    if len(cand_elements) < OVERFLOW_MIN_ELEMENTS:
        # Empty candidate: explicit fail on this axis instead of None (which
        # would silently drop it from the weighted mean). A page with no
        # content can't be a faithful replica.
        return MetricResult(
            name="overflow",
            score=0.0,
            extra={
                "empty_candidate": True,
                "candidate_element_count": len(cand_elements),
            },
        )

    cand_scroll_w = int((cand_data.get("page") or {}).get("scrollWidth") or viewport_width)
    ref_scroll_w = int((ref_data.get("page") or {}).get("scrollWidth") or viewport_width)

    # DOM scrollWidth can under-report real overflow when `overflow: hidden`
    # clips the document. Use max(scrollWidth, rendered PNG width) as the true
    # rendered width — the PNG is what the grader and a human actually see.
    cand_png_w = 0
    ref_png_w = 0
    if candidate_png is not None and candidate_png.exists():
        cand_png_w = Image.open(candidate_png).size[0]
    if reference_png is not None and reference_png.exists():
        ref_png_w = Image.open(reference_png).size[0]
    effective_cand_w = max(cand_scroll_w, cand_png_w)
    effective_ref_w = max(ref_scroll_w, ref_png_w)

    # Symmetric width-match: penalise the candidate for being wider OR narrower
    # than the reference's actual rendered width. Over-width is horizontal
    # overflow (broken at viewport); under-width is content-doesn't-fill (a
    # 900px column on a 1440px design is not a faithful replica). Use the
    # reference's rendered width as the target, viewport as the divisor.
    width_diff = abs(effective_cand_w - effective_ref_w) / max(viewport_width, 1)
    score = float(max(0.0, min(1.0, 1.0 - OVERFLOW_PENALTY_SLOPE * width_diff)))
    over_px = max(0, effective_cand_w - effective_ref_w)
    under_px = max(0, effective_ref_w - effective_cand_w)

    return MetricResult(
        name="overflow",
        score=score,
        extra={
            "candidate_scroll_width": cand_scroll_w,
            "reference_scroll_width": ref_scroll_w,
            "candidate_png_width": cand_png_w,
            "reference_png_width": ref_png_w,
            "effective_candidate_width": effective_cand_w,
            "effective_reference_width": effective_ref_w,
            "viewport_width": viewport_width,
            "over_px": over_px,
            "under_px": under_px,
            "width_diff_ratio": round(width_diff, 4),
        },
    )


# ---------------------------------------------------------------------------
# 6. Text similarity — weighted-Jaccard on visible tokens
# ---------------------------------------------------------------------------
#
# Catches content hallucination: row counts inflated, table data invented,
# numbers fabricated. Tokenisation is intentionally simple (lowercase, alnum
# runs, length≥2) so that punctuation, casing, and whitespace don't dominate.
# Weighted Jaccard ( sum min / sum max ) rather than set Jaccard so that
# "9 builds" vs "100 builds" gets the deserved low score: the extra 91 token
# occurrences inflate the union without finding matches in the intersection.


import re as _re
from collections import Counter as _Counter

_TOKEN_RE = _re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> _Counter:
    if not text:
        return _Counter()
    return _Counter(t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2)


def text_similarity(reference_dom: Path, candidate_dom: Path) -> MetricResult:
    ref = _load_dom_full(reference_dom).get("text") or ""
    cand = _load_dom_full(candidate_dom).get("text") or ""
    ref_t = _tokenize(ref)
    cand_t = _tokenize(cand)
    if not ref_t and not cand_t:
        return MetricResult(name="text", score=1.0, extra={"skipped": "both empty"})
    if not ref_t or not cand_t:
        return MetricResult(
            name="text", score=0.0,
            extra={"reference_tokens": sum(ref_t.values()), "candidate_tokens": sum(cand_t.values())},
        )
    inter = sum((ref_t & cand_t).values())
    union = sum((ref_t | cand_t).values())
    score = float(inter / max(union, 1))
    return MetricResult(
        name="text",
        score=score,
        extra={
            "reference_tokens": sum(ref_t.values()),
            "candidate_tokens": sum(cand_t.values()),
            "matched_tokens": inter,
            "union_tokens": union,
            "reference_unique": len(ref_t),
            "candidate_unique": len(cand_t),
        },
    )


def _load_dom_full(dom_path: Path) -> dict:
    """Load full dom.json including both `elements` and `page` keys."""
    if not dom_path.exists():
        return {"elements": [], "page": {}}
    try:
        return json.loads(dom_path.read_text())
    except Exception:
        return {"elements": [], "page": {}}


# ---------------------------------------------------------------------------
# Convenience: run all metrics for one (page, viewport) pair
# ---------------------------------------------------------------------------


def compute_all(
    reference_png: Path,
    candidate_png: Path,
    reference_dom: Path,
    candidate_dom: Path,
    viewport_width: int,
    vlm_result: MetricResult | None = None,
) -> dict[str, MetricResult]:
    """Run all structured metrics. VLM is computed in parallel by the caller."""
    out = {
        "ssim": ssim(reference_png, candidate_png),
        "block_match": block_match(reference_dom, candidate_dom),
        "position": position_match(reference_dom, candidate_dom),
        "palette": palette(reference_dom, candidate_dom),
        "typography": typography(reference_dom, candidate_dom),
        "text": text_similarity(reference_dom, candidate_dom),
        "overflow": overflow(candidate_dom, reference_dom, viewport_width,
                             candidate_png=candidate_png, reference_png=reference_png),
    }
    if vlm_result is not None:
        out["vlm_judge"] = vlm_result
    return out
