"""Re-run overflow metric on all v7 trials with the new symmetric-width-diff
logic and empty-candidate → 0.0. Reads existing block_match(k=100) + other
scores from subscores_k100.json, replaces overflow only, re-aggregates.
"""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
JOBS = ROOT / "jobs"
TASKS = ROOT / "tasks"

METRIC_WEIGHTS = {
    "text": 0.20, "overflow": 0.18, "ssim": 0.15, "block_match": 0.15,
    "palette": 0.12, "typography": 0.10, "position": 0.10, "vlm_judge": 0.0,
}
OVERFLOW_PENALTY_SLOPE = 2.0
OVERFLOW_MIN_ELEMENTS = 5


def overflow_v2(ref_dom_path: Path, cand_dom_path: Path,
                ref_png_path: Path, cand_png_path: Path,
                viewport_width: int):
    cand_data = json.loads(cand_dom_path.read_text()) if cand_dom_path.exists() else {"elements": []}
    ref_data = json.loads(ref_dom_path.read_text()) if ref_dom_path.exists() else {"elements": []}
    cand_elements = cand_data.get("elements") or []
    if len(cand_elements) < OVERFLOW_MIN_ELEMENTS:
        return 0.0, {"empty_candidate": True, "candidate_element_count": len(cand_elements)}
    cand_scroll_w = int((cand_data.get("page") or {}).get("scrollWidth") or viewport_width)
    ref_scroll_w = int((ref_data.get("page") or {}).get("scrollWidth") or viewport_width)
    cand_png_w = Image.open(cand_png_path).size[0] if cand_png_path.exists() else 0
    ref_png_w = Image.open(ref_png_path).size[0] if ref_png_path.exists() else 0
    effective_cand = max(cand_scroll_w, cand_png_w)
    effective_ref = max(ref_scroll_w, ref_png_w)
    width_diff = abs(effective_cand - effective_ref) / max(viewport_width, 1)
    score = float(max(0.0, min(1.0, 1.0 - OVERFLOW_PENALTY_SLOPE * width_diff)))
    return score, {
        "candidate_scroll_width": cand_scroll_w, "reference_scroll_width": ref_scroll_w,
        "candidate_png_width": cand_png_w, "reference_png_width": ref_png_w,
        "effective_candidate_width": effective_cand, "effective_reference_width": effective_ref,
        "viewport_width": viewport_width, "width_diff_ratio": round(width_diff, 4),
        "over_px": max(0, effective_cand - effective_ref),
        "under_px": max(0, effective_ref - effective_cand),
    }


VP_WIDTHS = {"desktop": 1440, "tablet": 768, "mobile": 375}


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
        sp = trial / "verifier" / "grading" / "subscores_k100.json"
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
                ref_png = ref_dir / f"{page}.{vp}.png"
                cand_png = rendered / f"{page}.{vp}.png"
                vpw = VP_WIDTHS.get(vp, 1440)
                ov_score, ov_extra = overflow_v2(ref_dom, cand_dom, ref_png, cand_png, vpw)
                m["overflow"] = {"name": "overflow", "score": ov_score, "extra": ov_extra}
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
                m["_structured_v2"] = structured
                m["_composite_v2"] = composite
                composites.append(composite)
            per_page_h[page] = 0.0 if all_missing else harmonic(composites)
        site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
        reward = site * anticheat
        s["reward_v2"] = reward
        s["per_page_harmonic_v2"] = per_page_h
        (trial / "verifier" / "grading" / "subscores_v2.json").write_text(json.dumps(s, indent=2))
        (trial / "verifier" / "reward_v2.txt").write_text(f"{reward}\n")
        old = float((trial / "verifier" / "reward_k100.txt").read_text())
        print(f"{jd.name}/{trial.name}: k100={old:.4f} → v2={reward:.4f} ({reward-old:+.4f})")
