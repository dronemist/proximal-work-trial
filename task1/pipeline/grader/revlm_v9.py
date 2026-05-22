"""Re-run VLM only on (page, viewport) pairs whose previous VLM call returned
None (oversize-image rejects + truncated-JSON parse failures), then recompute
the per-viewport composite and the per-site reward.

Reads Modal-side subscores.json, writes subscores_revlm.json + reward_revlm.txt.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline" / "grader"))

from vlm_judge import judge  # uses updated downscale + tolerant JSON

JOBS = ROOT / "jobs"


def harmonic(values):
    eps = 1e-6
    if not values:
        return 0.0
    safe = [max(v, eps) for v in values]
    return float(len(safe) / sum(1.0 / v for v in safe))


def composite(structured, vlm_score, ov_score):
    ov = ov_score if ov_score is not None else 1.0
    ceiling = 0.5 + 0.5 * ov
    c = structured
    if vlm_score is not None:
        c = min(c, vlm_score)
    return min(c, ceiling), ceiling


def main():
    fixed = 0
    seen = 0
    for jd in sorted(JOBS.glob("*-claude-opus-4-7-k10")):
        task_name = jd.name.replace("-claude-opus-4-7-k10", "")
        ref_dir = ROOT / "tasks" / "v9" / task_name / "tests" / "reference_truth"
        if not ref_dir.exists():
            continue
        for trial in sorted(jd.glob("*__*")):
            sp = trial / "verifier" / "grading" / "subscores.json"
            if not sp.exists():
                continue
            s = json.loads(sp.read_text())
            per_page_h = {}
            changed = False
            for page, vps in s["per_page_viewport"].items():
                composites = []
                all_missing = True
                for vp, m in vps.items():
                    if m.get("_missing"):
                        continue
                    all_missing = False
                    vlm = m.get("vlm_judge", {})
                    vlm_score = vlm.get("score") if isinstance(vlm, dict) else None

                    if vlm_score is None:
                        # Re-run VLM with downscale + tolerant parse
                        ref_png = ref_dir / f"{page}.{vp}.png"
                        cand_png = trial / "verifier" / "grading" / "rendered" / f"{page}.{vp}.png"
                        if ref_png.exists() and cand_png.exists():
                            seen += 1
                            res = judge(ref_png, cand_png)
                            if res.score is not None:
                                fixed += 1
                                changed = True
                                m["vlm_judge"] = {
                                    "name": "vlm_judge",
                                    "score": res.score,
                                    "extra": res.extra,
                                }
                                vlm_score = res.score

                    structured = m.get("_structured")
                    ov = m.get("overflow", {})
                    ov_score = ov.get("score") if isinstance(ov, dict) else None
                    c, ceil = composite(structured, vlm_score, ov_score)
                    m["_composite"] = c
                    m["_overflow_ceiling"] = ceil
                    composites.append(c)
                per_page_h[page] = 0.0 if all_missing else harmonic(composites)

            anticheat = s.get("anticheat_multiplier", 1.0)
            site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
            reward = site * anticheat
            s["per_page_harmonic"] = per_page_h
            s["reward_revlm"] = reward

            out = trial / "verifier" / "grading" / "subscores_revlm.json"
            out.write_text(json.dumps(s, indent=2))
            (trial / "verifier" / "reward_revlm.txt").write_text(f"{reward}\n")
            if changed:
                old = float((trial / "verifier" / "reward.txt").read_text())
                print(f"{trial.name}: {old:.4f} -> {reward:.4f} ({reward-old:+.4f})")

    print(f"\nattempted={seen} fixed={fixed}")


if __name__ == "__main__":
    main()
