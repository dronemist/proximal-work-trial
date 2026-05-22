"""Re-run VLM judge over completed v7 trials (verifier missed ANTHROPIC_API_KEY).

For each trial: load existing structured scores, call vlm_judge on each
(reference, candidate) pair, recompute composite = min(_structured, vlm),
re-aggregate per-page harmonic → per-site harmonic × anticheat, write
subscores_vlm.json + reward_vlm.txt next to the originals.
"""
from __future__ import annotations

import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline" / "grader"))
import vlm_judge  # noqa: E402

JOBS = ROOT / "jobs"
TASKS = ROOT / "tasks"


def harmonic(values: list[float]) -> float:
    eps = 1e-6
    if not values:
        return 0.0
    safe = [max(v, eps) for v in values]
    return float(len(safe) / sum(1.0 / v for v in safe))


def regrade_trial(trial_dir: Path, task_dir: Path) -> dict:
    sub_path = trial_dir / "verifier" / "grading" / "subscores.json"
    if not sub_path.exists():
        return {"trial": trial_dir.name, "error": "no subscores.json"}
    sub = json.loads(sub_path.read_text())
    pv = sub["per_page_viewport"]
    anticheat = sub.get("anticheat_multiplier", 1.0)

    ref_dir = task_dir / "tests" / "reference_truth"
    cand_dir = trial_dir / "verifier" / "grading" / "rendered"

    pairs = []
    for page, vps in pv.items():
        for vp, m in vps.items():
            if m.get("_missing"):
                continue
            ref = ref_dir / f"{page}.{vp}.png"
            cand = cand_dir / f"{page}.{vp}.png"
            if ref.exists() and cand.exists():
                pairs.append((page, vp, ref, cand))

    vlm_out = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(vlm_judge.judge, r, c): (p, v) for p, v, r, c in pairs}
        for f in as_completed(futs):
            p, v = futs[f]
            try:
                vlm_out[(p, v)] = f.result()
            except Exception as e:
                vlm_out[(p, v)] = vlm_judge.MetricResult(
                    name="vlm_judge", score=None,
                    extra={"error": f"{type(e).__name__}: {e}"})

    per_page_h = {}
    for page, vps in pv.items():
        composites = []
        all_missing = True
        for vp, m in vps.items():
            if m.get("_missing"):
                continue
            all_missing = False
            structured = m.get("_structured", m.get("_composite", 0.0))
            vlm_r = vlm_out.get((page, vp))
            vlm_score = vlm_r.score if vlm_r else None
            new_composite = structured if vlm_score is None else min(structured, vlm_score)
            m["vlm_judge"] = {"name": "vlm_judge", "score": vlm_score,
                              "extra": vlm_r.extra if vlm_r else {}}
            m["_composite_with_vlm"] = new_composite
            composites.append(new_composite)
        per_page_h[page] = 0.0 if all_missing else harmonic(composites)

    site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
    reward = site * anticheat

    sub["per_page_harmonic_with_vlm"] = per_page_h
    sub["reward_with_vlm"] = reward
    out_path = trial_dir / "verifier" / "grading" / "subscores_vlm.json"
    out_path.write_text(json.dumps(sub, indent=2))
    (trial_dir / "verifier" / "reward_vlm.txt").write_text(f"{reward}\n")
    return {"trial": trial_dir.name, "reward_old": float((trial_dir / "verifier" / "reward.txt").read_text().strip()),
            "reward_new": reward, "pairs": len(pairs)}


def main() -> int:
    task_dirs = sorted(TASKS.glob("*-v7"))
    summary = []
    for td in task_dirs:
        jobname = f"{td.name}-claude-k5"
        jd = JOBS / jobname
        if not jd.exists():
            continue
        for trial in sorted(jd.glob(f"{td.name}__*")):
            if not (trial / "verifier" / "grading" / "subscores.json").exists():
                continue
            res = regrade_trial(trial, td)
            print(f"{jobname}/{res['trial']}: "
                  f"old={res.get('reward_old','-'):.4f} → new={res.get('reward_new','-'):.4f} "
                  f"(pairs={res.get('pairs',0)})")
            summary.append({"task": td.name, **res})
    (JOBS / "_v7_regrade_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote summary → {JOBS / '_v7_regrade_summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
