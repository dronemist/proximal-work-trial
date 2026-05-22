"""Re-aggregate v9 trials with overflow as a partial multiplier instead of a
soft ceiling.

  composite = min(structured, vlm) * (0.5 + 0.5 * overflow_score)

Reads subscores_revlm.json (post-VLM-fix) and writes subscores_v6.json /
reward_v6.txt.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JOBS = ROOT / "jobs"


def harmonic(values):
    eps = 1e-6
    if not values:
        return 0.0
    safe = [max(v, eps) for v in values]
    return float(len(safe) / sum(1.0 / v for v in safe))


for jd in sorted(JOBS.glob("*-claude-opus-4-7-k10")):
    for trial in sorted(jd.glob("*__*")):
        sp = trial / "verifier" / "grading" / "subscores_revlm.json"
        if not sp.exists():
            continue
        s = json.loads(sp.read_text())
        per_page_h = {}
        for page, vps in s["per_page_viewport"].items():
            composites = []
            all_missing = True
            for vp, m in vps.items():
                if m.get("_missing"):
                    continue
                all_missing = False
                structured = m.get("_structured")
                vlm = m.get("vlm_judge", {})
                vlm_score = vlm.get("score") if isinstance(vlm, dict) else None
                ov = m.get("overflow", {})
                ov_score = ov.get("score") if isinstance(ov, dict) else 1.0
                if ov_score is None:
                    ov_score = 1.0
                factor = 0.5 + 0.5 * ov_score
                base = structured
                if vlm_score is not None:
                    base = min(base, vlm_score)
                composite = base * factor
                m["_overflow_factor"] = factor
                m["_composite"] = composite
                m.pop("_overflow_ceiling", None)
                composites.append(composite)
            per_page_h[page] = 0.0 if all_missing else harmonic(composites)

        anticheat = s.get("anticheat_multiplier", 1.0)
        site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
        reward = site * anticheat
        s["per_page_harmonic"] = per_page_h
        s["reward_v6"] = reward
        (trial / "verifier" / "grading" / "subscores_v6.json").write_text(json.dumps(s, indent=2))
        (trial / "verifier" / "reward_v6.txt").write_text(f"{reward}\n")
