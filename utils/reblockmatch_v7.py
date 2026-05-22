"""Re-run block_match with top-K=100 cap (was 400) on all v7 trials.

Reads each trial's persisted dom.json sidecars (ref + candidate), recomputes
block_match score, replaces the value in subscores_reweighted.json, then
re-aggregates structured composite + harmonic + reward with the locked
METRIC_WEIGHTS.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parent.parent.parent
JOBS = ROOT / "jobs"
TASKS = ROOT / "tasks"

MAX_BLOCKS = 100  # was 400 — top-K by area

METRIC_WEIGHTS = {
    "text": 0.20, "overflow": 0.18, "ssim": 0.15, "block_match": 0.15,
    "palette": 0.12, "typography": 0.10, "position": 0.10, "vlm_judge": 0.0,
}


def _iou(a, b):
    ax, ay, aw, ah = a["x"], a["y"], a["w"], a["h"]
    bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _bboxes(elements):
    out = []
    for el in elements:
        b = el.get("bbox") or {}
        if all(k in b for k in ("x", "y", "w", "h")) and b["w"] > 0 and b["h"] > 0:
            out.append(b)
    out.sort(key=lambda b: b["w"] * b["h"], reverse=True)
    return out[:MAX_BLOCKS]


def block_match_score(ref_dom_path: Path, cand_dom_path: Path):
    ref_data = json.loads(ref_dom_path.read_text())
    cand_data = json.loads(cand_dom_path.read_text())
    ref = _bboxes(ref_data.get("elements") or [])
    cand = _bboxes(cand_data.get("elements") or [])
    if not ref and not cand:
        return 1.0, {"empty": True}
    if not ref or not cand:
        return 0.0, {"reference_blocks": len(ref), "candidate_blocks": len(cand)}
    n_ref, n_cand = len(ref), len(cand)
    cost = np.ones((n_ref, n_cand), dtype=np.float32)
    for i, r in enumerate(ref):
        for j, c in enumerate(cand):
            cost[i, j] = 1.0 - _iou(r, c)
    row_idx, col_idx = linear_sum_assignment(cost)
    matched_ious = [1.0 - cost[i, j] for i, j in zip(row_idx, col_idx)]
    raw = float(sum(matched_ious) / min(n_ref, n_cand))
    score = float(raw ** 0.5)
    return score, {
        "reference_blocks": n_ref, "candidate_blocks": n_cand,
        "mean_matched_iou": float(np.mean(matched_ious)),
        "raw": raw, "k_cap": MAX_BLOCKS,
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
        sp = trial / "verifier" / "grading" / "subscores_reweighted.json"
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
                ref_dom = ref_dir / f"{page}.{vp}.dom.json"
                cand_dom = rendered / f"{page}.{vp}.dom.json"
                if ref_dom.exists() and cand_dom.exists():
                    new_score, new_extra = block_match_score(ref_dom, cand_dom)
                    m["block_match"] = {"name": "block_match", "score": new_score, "extra": new_extra}
                # rebuild per-metric dict for reweighting
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
                m["_structured_k100"] = structured
                m["_composite_k100"] = composite
                composites.append(composite)
            per_page_h[page] = 0.0 if all_missing else harmonic(composites)

        site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
        reward = site * anticheat
        s["reward_k100"] = reward
        s["per_page_harmonic_k100"] = per_page_h
        (trial / "verifier" / "grading" / "subscores_k100.json").write_text(json.dumps(s, indent=2))
        (trial / "verifier" / "reward_k100.txt").write_text(f"{reward}\n")
        print(f"{jd.name}/{trial.name}: reweighted=({float((trial / 'verifier' / 'reward_reweighted.txt').read_text()):.4f}) → k100={reward:.4f}")
