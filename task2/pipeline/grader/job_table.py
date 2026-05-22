"""Per-task summary across trials: mean, best, pass@k, plus per-feature means.

Generalises v7_table.py. Works on any job-name suffix (e.g. v7 / v9 runs) and
on whichever subscores file is present (subscores_v5.json from local re-grade,
else Modal-native subscores.json).

Usage:
    python3 pipeline/grader/job_table.py --suffix -v9-claude-opus-4-7-k10
    python3 pipeline/grader/job_table.py --suffix -v7-claude-k5 --subscores subscores_v5.json
    python3 pipeline/grader/job_table.py --suffix -v9-claude-opus-4-7-k10 \
            --thresholds 0.5 0.7 --zero-eps 0.01

Reports per task:
  - n_trials, n_valid (after dropping regression-zero rewards <= zero_eps)
  - mean (over valid trials), stdev, min, max, best (max)
  - pass@T for each --threshold (fraction of trials with reward >= T,
    computed over ALL trials including zeros — pass-rate is a reliability metric)
  - per-feature mean across the best trial's (page, viewport) pairs
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parent.parent.parent
JOBS = ROOT / "jobs"

FEATURES = ["ssim", "block_match", "palette", "text", "position",
            "typography", "overflow", "vlm_judge"]


def load_subscores(trial: Path, candidates: list[str]) -> tuple[dict | None, str | None]:
    for name in candidates:
        p = trial / "verifier" / "grading" / name
        if p.exists():
            return json.loads(p.read_text()), name
    return None, None


def reward_of(sub: dict, name: str) -> float | None:
    # subscores_v5.json uses "reward_v5"; Modal-native uses "reward"
    for k in ("reward_v6", "reward_revlm", "reward_v5", "reward"):
        if k in sub:
            return float(sub[k])
    # fallback: read reward.txt
    return None


def best_trial_feature_means(sub: dict) -> dict[str, float | None]:
    feat = {f: [] for f in FEATURES}
    for page, vps in sub.get("per_page_viewport", {}).items():
        for vp, m in vps.items():
            if m.get("_missing"):
                continue
            for f in FEATURES:
                v = m.get(f)
                sc = v.get("score") if isinstance(v, dict) else v
                if sc is not None:
                    feat[f].append(sc)
    return {f: (mean(vs) if vs else None) for f, vs in feat.items()}


def fmt(v, w=6):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "  -- ".ljust(w)
    if isinstance(v, float):
        return f"{v:.3f}".ljust(w)
    return str(v).ljust(w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suffix", required=True,
                    help="Job-name suffix, e.g. '-v9-claude-opus-4-7-k10'")
    ap.add_argument("--subscores", nargs="+",
                    default=["subscores_v5.json", "subscores.json"],
                    help="Which subscores files to try in order (first hit wins)")
    ap.add_argument("--thresholds", nargs="+", type=float, default=[0.5, 0.7],
                    help="Reward thresholds for pass@T (default: 0.5 0.7)")
    ap.add_argument("--zero-eps", type=float, default=0.01,
                    help="Rewards <= this are treated as regression-zero and dropped from mean")
    ap.add_argument("--json-out", type=str, default=None,
                    help="Optional path to dump table as JSON")
    args = ap.parse_args()

    rows = []
    for jd in sorted(JOBS.glob(f"*{args.suffix}")):
        rewards = []
        sub_by_trial = []
        for trial in sorted(jd.glob("*__*")):
            sub, used = load_subscores(trial, args.subscores)
            r = None
            if sub is not None:
                r = reward_of(sub, used)
            if r is None:
                rf = trial / "verifier" / "reward.txt"
                if rf.exists():
                    try:
                        r = float(rf.read_text().strip())
                    except ValueError:
                        r = None
            if r is None:
                continue
            rewards.append(r)
            sub_by_trial.append((r, trial, sub))
        if not rewards:
            continue

        n_trials = len(rewards)
        valid = [r for r in rewards if r > args.zero_eps]
        n_valid = len(valid)
        m = mean(valid) if valid else 0.0
        sd = pstdev(valid) if len(valid) > 1 else 0.0
        best = max(rewards)
        worst = min(rewards)
        pass_at = {f"p@{t}": (sum(1 for r in rewards if r >= t) / n_trials)
                   for t in args.thresholds}

        # Best trial feature means
        best_sub = max(sub_by_trial, key=lambda x: x[0])[2]
        feat_means = best_trial_feature_means(best_sub) if best_sub else {f: None for f in FEATURES}
        n_pages = len(best_sub.get("per_page_viewport", {})) if best_sub else 0

        task = jd.name.replace(args.suffix, "")
        rows.append({
            "task": task,
            "pages": n_pages,
            "n": n_trials,
            "n_valid": n_valid,
            "mean": m,
            "stdev": sd,
            "min": worst,
            "best": best,
            **pass_at,
            **{f: feat_means.get(f) for f in FEATURES},
        })

    if not rows:
        print(f"No jobs matched suffix '{args.suffix}'")
        return

    pass_cols = [f"p@{t}" for t in args.thresholds]
    cols = ["task", "pages", "n", "n_valid", "mean", "stdev", "min", "best"] + pass_cols + FEATURES
    widths = {c: max(len(c), 6) for c in cols}
    widths["task"] = max(len("task"), max(len(r["task"]) for r in rows))

    print(" | ".join(c.ljust(widths[c]) for c in cols))
    print("-+-".join("-" * widths[c] for c in cols))
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c)
            if c == "task":
                cells.append(str(v).ljust(widths[c]))
            elif c in ("n", "n_valid", "pages"):
                cells.append(str(v).ljust(widths[c]))
            else:
                cells.append(fmt(v, widths[c]))
        print(" | ".join(cells))

    bests = [r["best"] for r in rows]
    print()
    print(f"cross-task mean-of-bests: {mean(bests):.3f}  range [{min(bests):.3f}, {max(bests):.3f}]")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, indent=2))
        print(f"\nJSON: {args.json_out}")


if __name__ == "__main__":
    main()
