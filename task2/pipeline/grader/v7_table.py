"""Build the per-test x per-feature table from the v7 regrade.

Picks the best-of-5 trial per task by reward_with_vlm, then averages each
structured feature across all (page, viewport) pairs of that winning trial.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JOBS = ROOT / "jobs"

FEATURES = ["ssim", "block_match", "palette", "text", "position", "typography", "overflow", "vlm_judge"]

rows = []
for jd in sorted(JOBS.glob("*-v7-claude-k5")):
    best = None
    for trial in sorted(jd.glob("*__*")):
        sp = trial / "verifier" / "grading" / "subscores_v5.json"
        if not sp.exists():
            continue
        s = json.loads(sp.read_text())
        r = s.get("reward_v5", 0.0)
        if best is None or r > best[0]:
            best = (r, trial, s)
    if best is None:
        continue
    reward, trial, sub = best
    feat_avg = {f: [] for f in FEATURES}
    for page, vps in sub["per_page_viewport"].items():
        for vp, m in vps.items():
            if m.get("_missing"):
                continue
            for f in FEATURES:
                v = m.get(f)
                score = v.get("score") if isinstance(v, dict) else v
                if score is not None:
                    feat_avg[f].append(score)
    feat_means = {f: (sum(vs) / len(vs) if vs else None) for f, vs in feat_avg.items()}
    rows.append({
        "task": jd.name.replace("-claude-k5", ""),
        "trial": trial.name.split("__")[1],
        "reward": reward,
        **feat_means,
    })


def fmt(v):
    return f"{v:.3f}" if isinstance(v, (int, float)) else " -- "


cols = ["task", "trial", "reward"] + FEATURES
widths = {c: max(len(c), max(len(fmt(r[c])) if c not in ("task","trial") else len(str(r[c])) for r in rows)) for c in cols}
print(" | ".join(c.ljust(widths[c]) for c in cols))
print("-+-".join("-" * widths[c] for c in cols))
for r in rows:
    cells = []
    for c in cols:
        v = r[c]
        if c in ("task","trial"):
            cells.append(str(v).ljust(widths[c]))
        else:
            cells.append(fmt(v).ljust(widths[c]))
    print(" | ".join(cells))

(JOBS / "_v7_per_feature_table.json").write_text(json.dumps(rows, indent=2))
print(f"\nJSON: {JOBS / '_v7_per_feature_table.json'}")
