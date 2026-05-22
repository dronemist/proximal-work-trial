"""Re-run VLM on every (page, viewport) pair of the fresh Modal jobs using the
reverted (looser) VLM prompt, then recompute composite with the v6 overflow
multiplier: composite = min(structured, vlm) * (0.5 + 0.5 * overflow_score).

Reads each trial's subscores.json, writes subscores_v7.json + reward_v7.txt.
"""
from __future__ import annotations
import json
import sys
import concurrent.futures
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "pipeline" / "grader"))

from vlm_judge import judge  # uses reverted prompt + downscale + tolerant parse

JOBS = ROOT / "jobs"
SUFFIX = "-opus-20260522-1437-k10"


def harmonic(values):
    eps = 1e-6
    if not values:
        return 0.0
    safe = [max(v, eps) for v in values]
    return float(len(safe) / sum(1.0 / v for v in safe))


_lock = threading.Lock()
_done = 0
_total = 0


def regrade_pair(ref_png, cand_png):
    try:
        r = judge(ref_png, cand_png)
        return r.score, r.extra
    except Exception as e:
        return None, {"error": f"{type(e).__name__}: {e}"}


def regrade_trial(trial: Path, ref_dir: Path):
    global _done
    sp = trial / "verifier" / "grading" / "subscores.json"
    if not sp.exists():
        return
    s = json.loads(sp.read_text())

    # Re-VLM every present pair in parallel
    pairs = []
    for page, vps in s["per_page_viewport"].items():
        for vp, m in vps.items():
            if m.get("_missing"):
                continue
            ref_png = ref_dir / f"{page}.{vp}.png"
            cand_png = trial / "verifier" / "grading" / "rendered" / f"{page}.{vp}.png"
            if ref_png.exists() and cand_png.exists():
                pairs.append((page, vp, ref_png, cand_png, m))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(regrade_pair, rp, cp): (page, vp, m) for (page, vp, rp, cp, m) in pairs}
        for fut in concurrent.futures.as_completed(futures):
            page, vp, m = futures[fut]
            score, extra = fut.result()
            m["vlm_judge"] = {"name": "vlm_judge", "score": score, "extra": extra}
            with _lock:
                _done += 1
                if _done % 50 == 0:
                    print(f"  vlm: {_done}/{_total}", flush=True)

    # Recompute composites
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
            composites.append(composite)
        per_page_h[page] = 0.0 if all_missing else harmonic(composites)

    anticheat = s.get("anticheat_multiplier", 1.0)
    site = harmonic(list(per_page_h.values())) if per_page_h else 0.0
    reward = site * anticheat
    s["per_page_harmonic"] = per_page_h
    s["reward_v7"] = reward
    (trial / "verifier" / "grading" / "subscores_v7.json").write_text(json.dumps(s, indent=2))
    (trial / "verifier" / "reward_v7.txt").write_text(f"{reward}\n")


def main():
    global _total
    trials = []
    for jd in sorted(JOBS.glob(f"*{SUFFIX}")):
        task_name = jd.name.replace(SUFFIX, "")
        ref_dir = ROOT / "tasks" / "v9" / task_name / "tests" / "reference_truth"
        if not ref_dir.exists():
            continue
        for trial in sorted(jd.glob("*__*")):
            trials.append((trial, ref_dir))

    # Count total pairs
    for trial, ref_dir in trials:
        sp = trial / "verifier" / "grading" / "subscores.json"
        if not sp.exists():
            continue
        s = json.loads(sp.read_text())
        for page, vps in s["per_page_viewport"].items():
            for vp, m in vps.items():
                if not m.get("_missing"):
                    _total += 1
    print(f"total VLM calls to make: {_total}")
    print(f"trials: {len(trials)}")

    for trial, ref_dir in trials:
        regrade_trial(trial, ref_dir)
    print(f"DONE: {_done}/{_total}")


if __name__ == "__main__":
    main()
