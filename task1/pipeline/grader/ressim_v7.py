"""Re-run SSIM on all v7 trials with the overflow-aware padding fix, then
re-aggregate composite + reward using the existing other-metric scores from
subscores_v3.json.

For cand_w > ref_w: pad reference horizontally with right-edge bg color out
to cand_w, then SSIM. Otherwise: crop to min (existing behaviour).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

ROOT = Path(__file__).resolve().parent.parent.parent
JOBS = ROOT / "jobs"
TASKS = ROOT / "tasks"

METRIC_WEIGHTS = {
    "text": 0.20, "overflow": 0.18, "ssim": 0.15, "block_match": 0.15,
    "palette": 0.12, "typography": 0.10, "position": 0.10, "vlm_judge": 0.0,
}


def ssim_v2(ref_png: Path, cand_png: Path) -> tuple[float, dict]:
    ref = np.array(Image.open(ref_png).convert("RGB"))
    cand = np.array(Image.open(cand_png).convert("RGB"))
    ref_h, ref_w = ref.shape[:2]
    cand_h, cand_w = cand.shape[:2]
    crop_h = min(ref_h, cand_h)
    if cand_w > ref_w:
        right_edge = ref[:, -1:, :]
        bg = np.median(right_edge.reshape(-1, 3), axis=0).astype(np.uint8)
        pad = np.full((ref_h, cand_w - ref_w, 3), bg, dtype=np.uint8)
        ref = np.concatenate([ref, pad], axis=1)
        compared_w = cand_w
        strategy = "ref_padded_right_with_edge_bg"
    else:
        compared_w = cand_w
        strategy = "crop_to_min"
    ref_c = ref[:crop_h, :compared_w, :]
    cand_c = cand[:crop_h, :compared_w, :]
    score, _ = structural_similarity(ref_c, cand_c, channel_axis=2, data_range=255, full=True)
    score = float(max(0.0, min(1.0, score)))
    return score, {
        "reference_size": [ref_w, ref_h], "candidate_size": [cand_w, cand_h],
        "compared_size": [compared_w, crop_h], "pad_strategy": strategy,
    }


def weighted_arith(scores):
    present = {k: v for k, v in scores.items() if v is not None}
    total_w = sum(METRIC_WEIGHTS.get(k, 0.0) for k in present)
    if total_w <= 0:
        return 0.0
    return sum(present[k] * METRIC_WEIGHTS.get(k, 0.0) for k in present) / total_w


def harmonic(values):
    eps = 1e-6
    if not values:
        return 0.0
    safe = [max(v, eps) for v in values]
    return float(len(safe) / sum(1.0 / v for v in safe))


for jd in sorted(JOBS.glob("*-v7-claude-k5")):
    task_name = jd.name.replace("-claude-k5", "")
    ref_dir = TASKS / task_name / "tests" / "reference_truth"
    for trial in sorted(jd.glob("*__*")):
        sp = trial / "verifier" / "grading" / "subscores_v3.json"
        if not sp.exists():
            continue
        s = json.loads(sp.read_text())
        pv = s["per_page_viewport"]
        rendered = trial / "verifier" / "grading" / "rendered"
        anticheat = s.get("anticheat_multiplier", 1.0)

        per_page_h = {}
        for page, vps in pv.items():
            composites = []
            all_missing = True
            for vp, m in vps.items():
                if m.get("_missing"):
                    continue
                all_missing = False
                ref_png = ref_dir / f"{page}.{vp}.png"
                cand_png = rendered / f"{page}.{vp}.png"
                if ref_png.exists() and cand_png.exists():
                    new_ssim, ex = ssim_v2(ref_png, cand_png)
                    m["ssim"] = {"name": "ssim", "score": new_ssim, "extra": ex}
                per_metric = {}
                for k in METRIC_WEIGHTS:
                    if k == "vlm_judge":
                        continue
                    v = m.get(k)
                    sc = v.get("score") if isinstance(v, dict) else v
                    per_metric[k] = sc
                structured = weighted_arith(per_metric)
                vlm = m.get("vlm_judge", {})
                vlm_score = vlm.get("score") if isinstance(vlm, dict) else None
                composite = structured if vlm_score is None else min(structured, vlm_score)
                m["_structured_v4"] = structured
                m["_composite_v4"] = composite
                composites.append(composite)
            per_page_h[page] = 0.0 if all_missing else harmonic(composites)

        site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
        reward = site * anticheat
        s["reward_v4"] = reward
        s["per_page_harmonic_v4"] = per_page_h
        (trial / "verifier" / "grading" / "subscores_v4.json").write_text(json.dumps(s, indent=2))
        (trial / "verifier" / "reward_v4.txt").write_text(f"{reward}\n")
        old = float((trial / "verifier" / "reward_v3_eval.txt").read_text())
        flag = " ← MOVED" if abs(reward - old) > 0.005 else ""
        print(f"{trial.name}: v3={old:.4f} → v4={reward:.4f} ({reward-old:+.4f}){flag}")
