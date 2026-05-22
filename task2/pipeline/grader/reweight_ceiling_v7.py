"""Re-aggregate v7 trials with overflow soft-ceiling.

Reads existing v3 metric scores (VLM, anticheat-fixed) from subscores_v3.json,
applies composite = min(structured, vlm, 0.5 + 0.5 * overflow_score), then
harmonic across viewports/pages × anticheat. Writes subscores_v5.json /
reward_v5.txt.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JOBS = ROOT / "jobs"

METRIC_WEIGHTS = {
    "text": 0.20, "overflow": 0.0, "ssim": 0.15, "block_match": 0.15,
    "palette": 0.12, "typography": 0.10, "position": 0.10, "vlm_judge": 0.0,
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
    for trial in sorted(jd.glob("*__*")):
        sp = trial / "verifier" / "grading" / "subscores_v3.json"
        if not sp.exists():
            continue
        s = json.loads(sp.read_text())
        pv = s["per_page_viewport"]
        anticheat = s.get("anticheat_multiplier", 1.0)

        per_page_h = {}
        for page, vps in pv.items():
            composites = []
            all_missing = True
            for vp, m in vps.items():
                if m.get("_missing"):
                    continue
                all_missing = False
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
                ov = m.get("overflow", {})
                ov_score = ov.get("score") if isinstance(ov, dict) else None
                ov_score_eff = ov_score if ov_score is not None else 1.0
                ceiling = 0.5 + 0.5 * ov_score_eff
                composite = structured
                if vlm_score is not None:
                    composite = min(composite, vlm_score)
                composite = min(composite, ceiling)
                m["_overflow_ceiling"] = ceiling
                m["_composite_v5"] = composite
                composites.append(composite)
            per_page_h[page] = 0.0 if all_missing else harmonic(composites)

        site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
        reward = site * anticheat
        s["reward_v5"] = reward
        s["per_page_harmonic_v5"] = per_page_h
        (trial / "verifier" / "grading" / "subscores_v5.json").write_text(json.dumps(s, indent=2))
        (trial / "verifier" / "reward_v5.txt").write_text(f"{reward}\n")
        old = float((trial / "verifier" / "reward_v3_eval.txt").read_text())
        flag = " ← MOVED" if abs(reward - old) > 0.005 else ""
        print(f"{trial.name}: v3={old:.4f} → v5={reward:.4f} ({reward-old:+.4f}){flag}")
