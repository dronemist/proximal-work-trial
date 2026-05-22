"""Re-aggregate v7 trials with new METRIC_WEIGHTS (no re-render, no re-VLM).

Reads each trial's subscores_vlm.json (which contains per-metric scores + VLM),
recomputes _structured per (page, vp) with current METRIC_WEIGHTS, applies
min(structured, vlm) ceiling, then harmonic across vps → harmonic across pages
× anticheat. Writes subscores_reweighted.json and reward_reweighted.txt.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
METRIC_WEIGHTS = {
    "text": 0.20, "overflow": 0.18, "ssim": 0.15, "block_match": 0.15,
    "palette": 0.12, "typography": 0.10, "position": 0.10, "vlm_judge": 0.0,
}

JOBS = ROOT / "jobs"


def weighted_arith(scores: dict[str, float | None]) -> float:
    present = {k: v for k, v in scores.items() if v is not None}
    total_w = sum(METRIC_WEIGHTS.get(k, 0.0) for k in present)
    if total_w <= 0:
        return 0.0
    return sum(present[k] * METRIC_WEIGHTS.get(k, 0.0) for k in present) / total_w


def harmonic(values: list[float]) -> float:
    eps = 1e-6
    if not values:
        return 0.0
    safe = [max(v, eps) for v in values]
    return float(len(safe) / sum(1.0 / v for v in safe))


def reaggregate(trial: Path) -> dict | None:
    sp = trial / "verifier" / "grading" / "subscores_vlm.json"
    if not sp.exists():
        return None
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
                score = v.get("score") if isinstance(v, dict) else v
                per_metric[k] = score
            structured = weighted_arith(per_metric)
            vlm = m.get("vlm_judge", {})
            vlm_score = vlm.get("score") if isinstance(vlm, dict) else None
            composite = structured if vlm_score is None else min(structured, vlm_score)
            m["_structured_reweighted"] = structured
            m["_composite_reweighted"] = composite
            composites.append(composite)
        per_page_h[page] = 0.0 if all_missing else harmonic(composites)

    site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
    reward = site * anticheat
    s["per_page_harmonic_reweighted"] = per_page_h
    s["reward_reweighted"] = reward
    (trial / "verifier" / "grading" / "subscores_reweighted.json").write_text(json.dumps(s, indent=2))
    (trial / "verifier" / "reward_reweighted.txt").write_text(f"{reward}\n")
    old = float((trial / "verifier" / "reward_vlm.txt").read_text().strip())
    return {"trial": trial.name, "reward_vlm": old, "reward_reweighted": reward}


for jd in sorted(JOBS.glob("*-v7-claude-k5")):
    for trial in sorted(jd.glob("*__*")):
        r = reaggregate(trial)
        if r:
            print(f"{jd.name}/{r['trial']}: vlm={r['reward_vlm']:.4f} → reweighted={r['reward_reweighted']:.4f}")
