#!/usr/bin/env python3
"""
Phase 2 grader entrypoint — orchestration only.

Anti-cheat lives in `anticheat.py`. Per-image scoring lives in `metrics.py`.
This file just renders, scores, composes.

Aggregation:
  - Per (page, viewport) → SSIM with both-dim padding (metrics.ssim)
  - Per page → harmonic mean across viewports; missing-everywhere page → 0.0
  - Final → arithmetic mean across pages × anticheat multiplier
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import anticheat  # noqa: E402
import metrics as metrics_mod  # noqa: E402
import vlm_judge  # noqa: E402

VIEWPORTS = {
    "desktop": (1440, 900),
}

EPS = 1e-3  # harmonic-mean floor


# ---------------------------------------------------------------------------
# Rendering + aggregation
# ---------------------------------------------------------------------------


def render_agent_output(agent_html_dir: Path, render_out_dir: Path) -> dict:
    """Render every agent HTML at every viewport in VIEWPORTS."""
    import importlib.util

    candidates = [HERE.parent / "render.py", HERE / "render.py"]
    render_path = next((p for p in candidates if p.exists()), None)
    if render_path is None:
        raise FileNotFoundError("render.py not found alongside grader")
    spec = importlib.util.spec_from_file_location("render_mod", render_path)
    render_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_mod)

    render_out_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, dict] = {}
    for html_path in sorted(agent_html_dir.glob("*.html")):
        stem = html_path.stem
        for vp_name, (w, h) in VIEWPORTS.items():
            out_png = render_out_dir / f"{stem}.{vp_name}.png"
            try:
                meta = render_mod.render(
                    source=str(html_path),
                    output_png=out_png,
                    viewport_width=w,
                    viewport_height=h,
                    full_page=True,
                )
                rendered[f"{stem}.{vp_name}"] = meta
            except Exception as e:
                rendered[f"{stem}.{vp_name}"] = {"error": str(e)}
    return rendered


def _harmonic_mean(scores: list[float]) -> float:
    if not scores:
        return 0.0
    return len(scores) / sum(1.0 / max(s, EPS) for s in scores)


def _verify_reference_widths(reference_dir: Path) -> list[str]:
    """Sanity check: reference PNG widths must match VIEWPORTS within tolerance.
    Catches drift between this file's VIEWPORTS and the renderer's."""
    from PIL import Image
    warnings: list[str] = []
    for ref_png in sorted(reference_dir.glob("*.png")):
        parts = ref_png.stem.split(".")
        if len(parts) < 2:
            continue
        viewport_name = parts[-1]
        if viewport_name not in VIEWPORTS:
            warnings.append(f"unknown viewport tag in {ref_png.name}")
            continue
        expected_w = VIEWPORTS[viewport_name][0]
        actual_w = Image.open(ref_png).size[0]
        # Allow up to 50% horizontal overflow (e.g., wide <pre> blocks).
        if actual_w < expected_w * 0.9 or actual_w > expected_w * 1.5:
            warnings.append(
                f"{ref_png.name}: width {actual_w}px outside tolerance for "
                f"viewport={viewport_name} (expected ~{expected_w}px)"
            )
    return warnings


def _weighted_arith(subscores: dict[str, float | None]) -> float:
    """Weighted arithmetic mean using metrics.METRIC_WEIGHTS.

    Metrics combine arithmetically because they measure *different* axes:
    a perfect color score shouldn't be tanked by a weak layout score.
    Harmonic punishment is reserved for aggregating the *same* axis across
    viewports and pages, where one bad measurement *should* punish the rest.

    Scores of None (e.g. VLM judge with missing API key or transient API
    error) are dropped from BOTH the numerator and the denominator. The
    remaining metrics renormalise to fill the weight that was meant for the
    skipped metric, so a missing VLM doesn't tank the composite.
    """
    weights = metrics_mod.METRIC_WEIGHTS
    present = {k: v for k, v in subscores.items() if v is not None}
    total_w = sum(weights.get(k, 0.0) for k in present)
    if total_w <= 0:
        return 0.0
    return sum(present[k] * weights.get(k, 0.0) for k in present) / total_w


def compose(
    per_page_viewport_scores: dict[str, dict[str, dict]],
    anticheat_multiplier: float,
) -> tuple[float, dict[str, float]]:
    """Three-tier aggregation:
      - per (page, viewport): weighted arithmetic mean over metrics (in caller)
      - per page: harmonic mean across viewports
      - per site: harmonic mean across pages  ← cross-page failure punishes hard

    A page where ALL viewports are missing → 0.0 exact (not EPS-floored).
    """
    per_page_h: dict[str, float] = {}
    for page, viewports in per_page_viewport_scores.items():
        composed_per_vp: list[float] = []
        all_missing = True
        for vp_name, vp_subscores in viewports.items():
            if vp_subscores.get("_missing"):
                continue
            all_missing = False
            composed_per_vp.append(vp_subscores["_composite"])
        if all_missing:
            per_page_h[page] = 0.0
            continue
        per_page_h[page] = _harmonic_mean(composed_per_vp)

    if not per_page_h:
        return 0.0, {}
    site_score = _harmonic_mean(list(per_page_h.values()))
    return float(site_score * anticheat_multiplier), per_page_h


def _grade_page_viewport(
    reference_png: Path,
    candidate_png: Path,
    reference_dom: Path,
    candidate_dom: Path,
    viewport_width: int,
    vlm_result=None,
) -> dict:
    """Run structured metrics + fold in the precomputed VLM result."""
    results = metrics_mod.compute_all(
        reference_png=reference_png,
        candidate_png=candidate_png,
        reference_dom=reference_dom,
        candidate_dom=candidate_dom,
        viewport_width=viewport_width,
        vlm_result=vlm_result,
    )
    subscores = {k: dataclasses.asdict(v) for k, v in results.items()}
    composite = _weighted_arith({k: v.score for k, v in results.items()})
    subscores["_composite"] = composite
    return subscores


def _judge_all_pairs(pairs):
    """Fan out VLM judgments in parallel. Returns dict keyed by '{page}.{vp}'."""
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {k: vlm_judge.MetricResult(name="vlm_judge", score=None,
                                          extra={"skipped": True,
                                                 "reason": "ANTHROPIC_API_KEY not set"})
                for k, _, _ in pairs}
    out = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(vlm_judge.judge, ref, cand): key for key, ref, cand in pairs}
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                out[key] = fut.result()
            except Exception as e:
                out[key] = vlm_judge.MetricResult(name="vlm_judge", score=None,
                                                  extra={"error": f"{type(e).__name__}: {e}"})
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-html", required=True)
    ap.add_argument(
        "--reference-dir",
        help="Directory of pre-rendered reference PNGs (+ .dom.json sidecars). "
        "Ignored if --reference-html is given.",
    )
    ap.add_argument(
        "--reference-html",
        help="Directory of reference HTML/CSS to render on-the-fly. When set, "
        "the grader renders reference + agent in the same container so "
        "PNG/DOM extraction match by construction.",
    )
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--reward-file", default="/logs/verifier/reward.txt")
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()

    if not args.reference_dir and not args.reference_html:
        print("ERROR: pass --reference-dir or --reference-html", file=sys.stderr)
        return 2

    agent_html_dir = Path(args.agent_html)
    output_dir = Path(args.output_dir)
    reward_file = Path(args.reward_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    reward_file.parent.mkdir(parents=True, exist_ok=True)

    if args.reference_html:
        ref_html_dir = Path(args.reference_html)
        ref_rendered = output_dir / "reference_rendered"
        ref_meta = render_agent_output(ref_html_dir, ref_rendered)
        (output_dir / "reference_render_meta.json").write_text(
            json.dumps(ref_meta, indent=2)
        )
        reference_dir = ref_rendered
    else:
        reference_dir = Path(args.reference_dir)
    started = time.time()

    # 0. Sanity check reference widths
    ref_warnings = _verify_reference_widths(reference_dir)
    if ref_warnings:
        (output_dir / "reference_warnings.txt").write_text("\n".join(ref_warnings))

    # 1. Render the agent's HTML if requested
    render_meta: dict = {}
    if args.render:
        render_meta = render_agent_output(agent_html_dir, output_dir / "rendered")
        (output_dir / "render_meta.json").write_text(json.dumps(render_meta, indent=2))
        candidate_dir = output_dir / "rendered"
    else:
        candidate_dir = agent_html_dir

    # 2. Run all anti-cheat checks (delegates to anticheat.run_all_checks)
    ac = anticheat.run_all_checks(
        agent_dir=agent_html_dir,
        reference_dir=reference_dir,
        render_meta=render_meta,
    )
    (output_dir / "anticheat.json").write_text(
        json.dumps(
            {
                "penalty_multiplier": ac.penalty_multiplier,
                "violation_counts": ac.counts,
                "violations": ac.violations,
            },
            indent=2,
        )
    )

    # 3a. Pre-compute VLM judgments in parallel for every present pair.
    vlm_pairs = []
    for ref_png in sorted(reference_dir.glob("*.png")):
        parts = ref_png.stem.split(".")
        if len(parts) < 2 or parts[-1] not in VIEWPORTS:
            continue
        page = ".".join(parts[:-1])
        cand = candidate_dir / f"{page}.{parts[-1]}.png"
        if cand.exists():
            vlm_pairs.append((f"{page}.{parts[-1]}", ref_png, cand))
    vlm_t0 = time.time()
    vlm_results = _judge_all_pairs(vlm_pairs)
    print(f"[grade] VLM judge: {len(vlm_results)} pairs in {time.time()-vlm_t0:.1f}s")

    # 3b. Score every (page, viewport) pair the references advertise
    per_page_viewport: dict[str, dict[str, dict]] = {}
    missing: list[str] = []
    for ref_png in sorted(reference_dir.glob("*.png")):
        parts = ref_png.stem.split(".")
        if len(parts) < 2:
            continue
        viewport_name = parts[-1]
        if viewport_name not in VIEWPORTS:
            continue
        page_name = ".".join(parts[:-1])
        candidate_png = candidate_dir / f"{page_name}.{viewport_name}.png"
        ref_dom = ref_png.with_suffix(".dom.json")
        candidate_dom = candidate_png.with_suffix(".dom.json")
        if not candidate_png.exists():
            missing.append(f"{page_name}.{viewport_name}")
            per_page_viewport.setdefault(page_name, {})[viewport_name] = {
                "_missing": True,
                "_composite": 0.0,
            }
            continue
        key = f"{page_name}.{viewport_name}"
        vw, _ = VIEWPORTS[viewport_name]
        per_page_viewport.setdefault(page_name, {})[viewport_name] = _grade_page_viewport(
            ref_png, candidate_png, ref_dom, candidate_dom,
            viewport_width=vw,
            vlm_result=vlm_results.get(key),
        )

    # 4. Compose
    reward, per_page_harmonic = compose(per_page_viewport, ac.penalty_multiplier)

    # 5. Write everything
    subscores = {
        "per_page_viewport": per_page_viewport,
        "per_page_harmonic": per_page_harmonic,
        "metric_weights": metrics_mod.METRIC_WEIGHTS,
        "anticheat_multiplier": ac.penalty_multiplier,
        "anticheat_violations": len(ac.violations),
        "anticheat_counts": ac.counts,
        "missing": missing,
        "reference_warnings": ref_warnings,
        "reward": reward,
        "viewport_widths": {name: w for name, (w, _) in VIEWPORTS.items()},
        "wall_clock_seconds": time.time() - started,
    }
    (output_dir / "subscores.json").write_text(json.dumps(subscores, indent=2))
    reward_file.write_text(f"{reward}\n")

    print(json.dumps(subscores, indent=2)[:5000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
