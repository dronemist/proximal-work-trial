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

# One place to tune. grade.py reads this dict.
METRIC_WEIGHTS = {
    "ssim": 0.20,
    "block_match": 0.20,
    "palette": 0.20,
    "typography": 0.15,
    "overflow": 0.15,    # horizontal-overflow check at the rendered viewport
    "vlm_judge": 0.10,   # gestalt sanity; narrow discriminating range so low weight
}


@dataclass
class MetricResult:
    name: str
    score: float
    extra: dict


# ---------------------------------------------------------------------------
# 1. SSIM
# ---------------------------------------------------------------------------

CATASTROPHIC_RATIO = 0.5  # if either dim differs by ≥50%, hard-fail


def ssim(reference: Path, candidate: Path) -> MetricResult:
    """SSIM with both-dim zero-padding, hard-fail on ≥50% size delta."""
    ref = Image.open(reference).convert("RGB")
    cand = Image.open(candidate).convert("RGB")
    ref_arr = np.array(ref)
    cand_arr = np.array(cand)

    ref_h, ref_w = ref_arr.shape[:2]
    cand_h, cand_w = cand_arr.shape[:2]

    height_ratio = abs(ref_h - cand_h) / max(ref_h, cand_h)
    width_ratio = abs(ref_w - cand_w) / max(ref_w, cand_w)

    if height_ratio >= CATASTROPHIC_RATIO or width_ratio >= CATASTROPHIC_RATIO:
        return MetricResult(
            name="ssim",
            score=0.0,
            extra={
                "reference_size": [ref_w, ref_h],
                "candidate_size": [cand_w, cand_h],
                "dim_catastrophic": True,
            },
        )

    if (ref_h, ref_w) != (cand_h, cand_w):
        target_h, target_w = max(ref_h, cand_h), max(ref_w, cand_w)
        ref_arr = _pad_to(ref_arr, target_h, target_w)
        cand_arr = _pad_to(cand_arr, target_h, target_w)

    score, _ = structural_similarity(
        ref_arr, cand_arr, channel_axis=2, data_range=255, full=True
    )
    score = float(max(0.0, min(1.0, score)))
    return MetricResult(
        name="ssim",
        score=score,
        extra={
            "reference_size": [ref_w, ref_h],
            "candidate_size": [cand_w, cand_h],
        },
    )


def _pad_to(arr: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    cur_h, cur_w = arr.shape[:2]
    if cur_h >= target_h and cur_w >= target_w:
        return arr
    out = np.zeros((target_h, target_w, arr.shape[2]), dtype=arr.dtype)
    out[:cur_h, :cur_w, :] = arr
    return out


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
# Design2Code-style. For each element in reference and candidate we have its
# bounding box. We Hungarian-assign reference blocks to candidate blocks
# minimizing (1 - IoU), then aggregate the matched IoUs and penalize unmatched
# blocks on either side: final = sum(IoU) / max(N_ref, N_cand).
#
# Two simplifications vs. the published Design2Code Block-Match:
#   1. Per-pair score is bbox IoU only, no per-block text/color sub-scores.
#      Color and typography are already separate metrics in our stack; text
#      content is out of v1 scope.
#   2. We cap N at MAX_BLOCKS to keep the cost matrix small. Large pages
#      ( > 1k elements) would make Hungarian O(N^3) painful otherwise.


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
PALETTE_DIST_NORMALIZER = 0.6  # OKLab L2 ≈ 0.6 between strong palette mismatches
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


def _aggregate_palette(elements: list[dict]) -> list[tuple[tuple[float, float, float], float]]:
    """Group colors by quantized OKLab bucket (so #0a0a0a and #000000 merge),
    weight by total bbox area where that color appeared.

    Returns: [((L,a,b), area_weight), ...] sorted descending by weight.
    """
    buckets: dict[tuple[int, int, int], tuple[tuple[float, float, float], float]] = {}
    for el in elements:
        bbox = el.get("bbox") or {}
        area = float(bbox.get("w", 0)) * float(bbox.get("h", 0))
        if area <= 0:
            continue
        for k in ("color", "background_color"):
            rgb = _parse_color(el.get(k, ""))
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


def palette(reference_dom: Path, candidate_dom: Path) -> MetricResult:
    ref_palette = _aggregate_palette(_load_dom(reference_dom))
    cand_palette = _aggregate_palette(_load_dom(candidate_dom))

    if not ref_palette and not cand_palette:
        return MetricResult(name="palette", score=1.0, extra={"empty": True})
    if not ref_palette or not cand_palette:
        return MetricResult(
            name="palette",
            score=0.0,
            extra={
                "reference_palette_size": len(ref_palette),
                "candidate_palette_size": len(cand_palette),
            },
        )

    ref_top = ref_palette[:PALETTE_TOP_K]   # [(lab, area), ...] sorted desc by area
    cand_top = cand_palette[:PALETTE_TOP_K]

    # Mass-weighted Hungarian matching. Why mass-weighting:
    # eyeball calibration (R12) showed that a single accent-color shift on
    # a high-area element (e.g. brand-blue → brand-purple on a hero button
    # used across the page) reads as "noticeably different design" to a
    # human, but unweighted averaging dilutes this — only 1 of K matched
    # pairs has the shift, so its distance is averaged with K-1 close pairs.
    # Weighting by total bbox area where each color appears makes the
    # accent shift contribute proportionally to its visual prominence.
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

    matched_distances: list[float] = []
    weighted_total = 0.0
    weight_total = 0.0
    for i, j in zip(row_idx, col_idx):
        ref_share = ref_top[i][1] / ref_total
        cand_share = cand_top[j][1] / cand_total
        pair_weight = (ref_share + cand_share) / 2.0
        weighted_total += pair_weight * rect[i, j]
        weight_total += pair_weight
        matched_distances.append(float(rect[i, j]))

    avg_weighted = float(weighted_total / max(weight_total, 1e-9))
    base = float(max(0.0, min(1.0, 1.0 - avg_weighted / PALETTE_DIST_NORMALIZER)))

    # Over-coloring penalty: dock if the candidate's distinct-color count
    # is much larger than the reference's. Stronger than the previous
    # tuning because mass-weighted matching otherwise rewards bringing
    # extra "close enough" colors.
    size_ratio = (
        max(len(ref_palette), len(cand_palette))
        / max(1, min(len(ref_palette), len(cand_palette)))
    )
    over_color_penalty = float(max(0.0, min(0.20, 0.08 * (size_ratio - 1.3))))
    score = float(max(0.0, base - over_color_penalty))

    return MetricResult(
        name="palette",
        score=score,
        extra={
            "reference_palette_size": len(ref_palette),
            "candidate_palette_size": len(cand_palette),
            "matched_pairs": len(matched_distances),
            "weighted_mean_oklab_distance": avg_weighted,
            "base_score_before_penalty": base,
            "over_color_penalty": over_color_penalty,
        },
    )


# ---------------------------------------------------------------------------
# 4. Typography — set Jaccard over font-family stacks
# ---------------------------------------------------------------------------


def _collect_fonts(elements: list[dict]) -> set[str]:
    out: set[str] = set()
    for el in elements:
        fam = (el.get("font_family") or "").strip()
        if fam:
            # Take the first family in the stack ("Inter, sans-serif" → "Inter")
            primary = fam.split(",")[0].strip().strip('"').strip("'").lower()
            if primary:
                out.add(primary)
    return out


def typography(reference_dom: Path, candidate_dom: Path) -> MetricResult:
    ref = _load_dom(reference_dom)
    cand = _load_dom(candidate_dom)
    ref_set = _collect_fonts(ref)
    cand_set = _collect_fonts(cand)
    score = _set_jaccard(ref_set, cand_set)
    return MetricResult(
        name="typography",
        score=score,
        extra={
            "reference_fonts": sorted(ref_set),
            "candidate_fonts": sorted(cand_set),
        },
    )


# ---------------------------------------------------------------------------
# 5. Overflow — penalize candidates rendered wider than the declared viewport
# ---------------------------------------------------------------------------
#
# Eyeball calibration (R12) found a failure mode where the candidate's bbox
# positions matched the reference (block_match looked fine) but the rendered
# content overflowed horizontally — visible text was clipped at the viewport
# edge. None of SSIM / block_match / palette / typography caught this.
#
# Detection: a full-page screenshot's width equals max(viewport_w, scrollWidth).
# So PNG width > viewport_w directly indicates horizontal overflow. We compare
# the candidate's PNG width against max(viewport_width, reference_width)
# rather than the raw viewport — references occasionally legitimately overflow
# for wide <pre> blocks; the candidate gets a free pass to overflow up to the
# reference's tolerance, but is penalized linearly past that.


OVERFLOW_PENALTY_SLOPE = 2.0  # 1 unit of overflow ratio costs 2× score


def overflow(
    candidate_png: Path,
    reference_png: Path,
    viewport_width: int,
) -> MetricResult:
    cand_w, _ = Image.open(candidate_png).size
    ref_w, _ = Image.open(reference_png).size
    allowance = max(viewport_width, ref_w)
    over_px = max(0, cand_w - allowance)
    over_ratio = over_px / max(viewport_width, 1)
    score = max(0.0, min(1.0, 1.0 - OVERFLOW_PENALTY_SLOPE * over_ratio))
    return MetricResult(
        name="overflow",
        score=score,
        extra={
            "candidate_width": cand_w,
            "reference_width": ref_w,
            "viewport_width": viewport_width,
            "allowance_width": allowance,
            "overflow_px": over_px,
            "overflow_ratio": round(over_ratio, 4),
        },
    )


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
        "palette": palette(reference_dom, candidate_dom),
        "typography": typography(reference_dom, candidate_dom),
        "overflow": overflow(candidate_png, reference_png, viewport_width),
    }
    if vlm_result is not None:
        out["vlm_judge"] = vlm_result
    return out
