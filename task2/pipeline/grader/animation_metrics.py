"""
Animation grading metrics — compare reference vs candidate animation keyframes.

Four sub-metrics, all return MetricResult with score in [0.0, 1.0]:

  1. keyframe_ssim(ref_dir, cand_dir, page, viewport)
     Mean SSIM across animation keyframe snapshots (0%, 50%, 100%).

  2. animation_count(ref_meta, cand_meta)
     Ratio-based score penalizing missing or extra animations.

  3. timing_similarity(ref_meta, cand_meta)
     Hungarian-matched duration/delay comparison.

  4. property_match(ref_meta, cand_meta)
     Jaccard over animated CSS properties (opacity, transform, etc.).

Composition:
  animation_score = 0.50 * keyframe_ssim
                  + 0.20 * animation_count
                  + 0.15 * timing_similarity
                  + 0.15 * property_match
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

ANIMATION_METRIC_WEIGHTS = {
    "keyframe_ssim": 0.50,
    "animation_count": 0.20,
    "timing_similarity": 0.15,
    "property_match": 0.15,
}


@dataclass
class MetricResult:
    name: str
    score: float | None
    extra: dict


def _load_animation_meta(meta_path: Path) -> list[dict]:
    if not meta_path.exists():
        return []
    try:
        return json.loads(meta_path.read_text())
    except Exception:
        return []


def keyframe_ssim(
    ref_screenshots_dir: Path,
    cand_screenshots_dir: Path,
    page_slug: str,
    vp_name: str,
    keyframe_pcts: list[str] | None = None,
) -> MetricResult:
    """SSIM across animation keyframe snapshots."""
    if keyframe_pcts is None:
        keyframe_pcts = ["0pct", "50pct", "100pct"]

    scores: list[float] = []
    details: dict[str, float] = {}

    for pct_label in keyframe_pcts:
        ref_png = ref_screenshots_dir / f"{page_slug}.{vp_name}.anim_{pct_label}.png"
        cand_png = cand_screenshots_dir / f"{page_slug}.{vp_name}.anim_{pct_label}.png"

        if not ref_png.exists() or not cand_png.exists():
            details[pct_label] = 0.0
            scores.append(0.0)
            continue

        ref_arr = np.array(Image.open(ref_png).convert("RGB"))
        cand_arr = np.array(Image.open(cand_png).convert("RGB"))

        crop_h = min(ref_arr.shape[0], cand_arr.shape[0])
        crop_w = min(ref_arr.shape[1], cand_arr.shape[1])
        ref_crop = ref_arr[:crop_h, :crop_w, :]
        cand_crop = cand_arr[:crop_h, :crop_w, :]

        s, _ = structural_similarity(
            ref_crop, cand_crop, channel_axis=2, data_range=255, full=True,
        )
        s = float(max(0.0, min(1.0, s)))
        scores.append(s)
        details[pct_label] = s

    mean_score = float(np.mean(scores)) if scores else 0.0
    return MetricResult(
        name="keyframe_ssim",
        score=mean_score,
        extra={"per_keyframe": details, "n_keyframes_compared": len(scores)},
    )


def animation_count(ref_meta: list[dict], cand_meta: list[dict]) -> MetricResult:
    """Score based on how well the candidate matches the reference animation count."""
    n_ref = len(ref_meta)
    n_cand = len(cand_meta)

    if n_ref == 0 and n_cand == 0:
        return MetricResult(name="animation_count", score=1.0, extra={"both_zero": True})
    if n_ref == 0 or n_cand == 0:
        return MetricResult(
            name="animation_count", score=0.0,
            extra={"reference_count": n_ref, "candidate_count": n_cand},
        )

    ratio = min(n_ref, n_cand) / max(n_ref, n_cand)
    return MetricResult(
        name="animation_count",
        score=float(ratio),
        extra={"reference_count": n_ref, "candidate_count": n_cand, "ratio": ratio},
    )


def timing_similarity(ref_meta: list[dict], cand_meta: list[dict]) -> MetricResult:
    """Hungarian-matched duration/delay comparison between animations."""
    if not ref_meta and not cand_meta:
        return MetricResult(name="timing_similarity", score=1.0, extra={"empty": True})
    if not ref_meta or not cand_meta:
        return MetricResult(
            name="timing_similarity", score=0.0,
            extra={"reference_count": len(ref_meta), "candidate_count": len(cand_meta)},
        )

    from scipy.optimize import linear_sum_assignment

    n_ref, n_cand = len(ref_meta), len(cand_meta)
    n = max(n_ref, n_cand)

    # Normalize durations: max reference duration as the scale
    max_dur = max((a.get("duration", 0) for a in ref_meta), default=1000) or 1000

    cost = np.ones((n, n), dtype=np.float32)
    for i in range(n_ref):
        r_dur = ref_meta[i].get("duration", 0) / max_dur
        r_delay = ref_meta[i].get("delay", 0) / max_dur
        for j in range(n_cand):
            c_dur = cand_meta[j].get("duration", 0) / max_dur
            c_delay = cand_meta[j].get("delay", 0) / max_dur
            dur_diff = abs(r_dur - c_dur)
            delay_diff = abs(r_delay - c_delay)
            cost[i, j] = (dur_diff + delay_diff) / 2.0

    row_idx, col_idx = linear_sum_assignment(cost)
    matched_costs = [float(cost[i, j]) for i, j in zip(row_idx, col_idx)]
    mean_cost = float(np.mean(matched_costs)) if matched_costs else 1.0
    score = float(max(0.0, min(1.0, 1.0 - mean_cost)))

    return MetricResult(
        name="timing_similarity",
        score=score,
        extra={
            "reference_count": n_ref,
            "candidate_count": n_cand,
            "mean_normalized_cost": mean_cost,
        },
    )


def _extract_animated_properties(meta: list[dict]) -> set[str]:
    """Extract the set of CSS properties being animated from keyframe data."""
    props: set[str] = set()
    for anim in meta:
        for kf in anim.get("keyframes", []):
            for key in kf:
                if key not in ("offset", "easing", "composite", "computedOffset"):
                    props.add(key)
        name = anim.get("name", "")
        if name and name != "unknown":
            props.add(f"@{name}")
    return props


def property_match(ref_meta: list[dict], cand_meta: list[dict]) -> MetricResult:
    """Jaccard similarity over animated CSS properties."""
    ref_props = _extract_animated_properties(ref_meta)
    cand_props = _extract_animated_properties(cand_meta)

    if not ref_props and not cand_props:
        return MetricResult(name="property_match", score=1.0, extra={"empty": True})
    if not ref_props or not cand_props:
        return MetricResult(
            name="property_match", score=0.0,
            extra={"reference_props": sorted(ref_props), "candidate_props": sorted(cand_props)},
        )

    jaccard = len(ref_props & cand_props) / len(ref_props | cand_props)
    return MetricResult(
        name="property_match",
        score=float(jaccard),
        extra={
            "reference_props": sorted(ref_props),
            "candidate_props": sorted(cand_props),
            "intersection": sorted(ref_props & cand_props),
        },
    )


def compute_animation_score(
    ref_screenshots_dir: Path,
    cand_screenshots_dir: Path,
    page_slug: str,
    vp_name: str,
    ref_meta: list[dict],
    cand_meta: list[dict],
    keyframe_pcts: list[str] | None = None,
) -> tuple[float, dict]:
    """Compute the composite animation score for one (page, viewport) pair.

    Returns (score, details_dict).
    """
    results = {
        "keyframe_ssim": keyframe_ssim(
            ref_screenshots_dir, cand_screenshots_dir, page_slug, vp_name, keyframe_pcts,
        ),
        "animation_count": animation_count(ref_meta, cand_meta),
        "timing_similarity": timing_similarity(ref_meta, cand_meta),
        "property_match": property_match(ref_meta, cand_meta),
    }

    weighted_sum = 0.0
    total_weight = 0.0
    for name, result in results.items():
        w = ANIMATION_METRIC_WEIGHTS.get(name, 0.0)
        if result.score is not None:
            weighted_sum += result.score * w
            total_weight += w

    composite = weighted_sum / total_weight if total_weight > 0 else 0.0
    details = {name: {"score": r.score, **r.extra} for name, r in results.items()}
    details["_composite"] = composite
    details["_weights"] = ANIMATION_METRIC_WEIGHTS

    return composite, details
