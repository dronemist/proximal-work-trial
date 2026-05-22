"""Re-run anticheat on all v7 trials with the fixed rules
(size-aware data_image_uri, percent-width oversized SVG skip) and the new
train/eval penalty split.

Reads agent output from each trial's `verifier/agent_output/`, reference truth
from `tasks/<task>/tests/reference_truth/`. Replaces anticheat fields in
subscores_v2.json and writes new rewards (eval = multiplicative, train = subtractive).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline" / "grader"))
import anticheat as ac_mod  # noqa: E402

JOBS = ROOT / "jobs"
TASKS = ROOT / "tasks"
VP_AREA = 1440 * 900


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
        sp = trial / "verifier" / "grading" / "subscores_v2.json"
        if not sp.exists():
            continue
        s = json.loads(sp.read_text())
        old_mult = s.get("anticheat_multiplier", 1.0)
        old_reward = float((trial / "verifier" / "reward_v2.txt").read_text())

        agent_out = trial / "verifier" / "agent_output"
        render_meta_path = trial / "verifier" / "grading" / "render_meta.json"
        render_meta = {}
        if render_meta_path.exists():
            try:
                render_meta = json.loads(render_meta_path.read_text())
            except Exception:
                render_meta = {}

        result = ac_mod.run_all_checks(
            agent_dir=agent_out, reference_dir=ref_dir,
            render_meta=render_meta, viewport_area=VP_AREA,
        )

        # Recompute eval reward: site_score (already in subscores) × new multiplier
        # site_score = sum_over_pages_harmonic / old_mult was the old reward divided by old_mult
        # but easier: take stored per_page_harmonic_v2 and re-fold.
        per_page = s.get("per_page_harmonic_v2", {})
        site = harmonic(list(per_page.values())) if per_page else 0.0
        reward_eval = site * result.penalty_multiplier
        reward_train = max(0.0, site - result.train_penalty)

        s["anticheat_multiplier"] = result.penalty_multiplier
        s["anticheat_train_penalty"] = result.train_penalty
        s["anticheat_violations"] = result.violations
        s["anticheat_counts"] = result.counts
        s["reward_v3_eval"] = reward_eval
        s["reward_v3_train"] = reward_train

        (trial / "verifier" / "grading" / "subscores_v3.json").write_text(json.dumps(s, indent=2))
        (trial / "verifier" / "reward_v3_eval.txt").write_text(f"{reward_eval}\n")
        (trial / "verifier" / "reward_v3_train.txt").write_text(f"{reward_train}\n")

        flag = " ← MOVED" if abs(reward_eval - old_reward) > 0.01 else ""
        print(f"{trial.name}: old(v2)={old_reward:.4f} → eval={reward_eval:.4f} "
              f"train={reward_train:.4f}  mult={old_mult:.2f}→{result.penalty_multiplier:.2f}  "
              f"v_types={len(result.counts)}{flag}")
