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

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import anticheat  # noqa: E402
import animation_metrics  # noqa: E402
import metrics as metrics_mod  # noqa: E402
import vlm_judge  # noqa: E402

from viewports import VIEWPORTS  # noqa: E402

EPS = 1e-3  # harmonic-mean floor
STATIC_WEIGHT = 0.65
ANIMATION_WEIGHT = 0.35


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


def _is_animated_task(reference_dir: Path) -> bool:
    """Detect animated task by presence of .animations.json in reference dir."""
    return any(reference_dir.glob("*.animations.json"))


def _capture_agent_animation_keyframes(
    agent_html_dir: Path,
    output_dir: Path,
    keyframe_pcts: list[float] | None = None,
    n_filmstrip_frames: int = 10,
) -> dict:
    """Capture animation keyframes + filmstrip from the agent's HTML.

    Mirrors the reference capture in render_validate.py. Also generates a
    filmstrip PNG (n_filmstrip_frames across the timeline) for VLM judging.
    """
    if keyframe_pcts is None:
        keyframe_pcts = [0.0, 0.5, 1.0]

    from PIL import Image, ImageDraw
    from playwright.sync_api import sync_playwright

    _EXTRACT_JS = """() => {
        const anims = document.getAnimations();
        return anims.map(a => {
            const effect = a.effect;
            const timing = effect ? effect.getComputedTiming() : {};
            const keyframes = effect ? effect.getKeyframes() : [];
            const target = effect && effect.target ? {
                tag: effect.target.tagName,
                className: effect.target.className,
                id: effect.target.id || null,
            } : null;
            return {
                name: a instanceof CSSAnimation ? a.animationName : (a instanceof CSSTransition ? a.transitionProperty : 'unknown'),
                type: a.constructor.name,
                duration: timing.duration || 0,
                delay: timing.delay || 0,
                iterations: timing.iterations || 1,
                easing: timing.easing || 'linear',
                direction: timing.direction || 'normal',
                fillMode: timing.fill || 'none',
                keyframes: keyframes.map(kf => {
                    const obj = {};
                    for (const [k, v] of Object.entries(kf)) {
                        if (k !== 'composite' && k !== 'computedOffset') obj[k] = v;
                    }
                    return obj;
                }),
                target: target,
            };
        });
    }"""

    screenshots_dir = output_dir / "animation_keyframes"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for html_path in sorted(agent_html_dir.glob("*.html")):
                stem = html_path.stem
                source_url = f"file://{html_path.resolve()}"
                for vp_name, (w, h) in VIEWPORTS.items():
                    ctx = browser.new_context(
                        viewport={"width": w, "height": h},
                        device_scale_factor=1,
                    )
                    page = ctx.new_page()
                    page.goto(source_url, wait_until="load")
                    try:
                        page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
                    except Exception:
                        pass

                    page.evaluate("() => document.getAnimations().forEach(a => a.pause())")
                    animation_meta = page.evaluate(_EXTRACT_JS)

                    key = f"{stem}.{vp_name}"
                    if not animation_meta:
                        results[key] = {"metadata": [], "screenshots": {}, "filmstrip": None}
                        ctx.close()
                        continue

                    max_duration = max((a.get("duration", 0) for a in animation_meta), default=1000) or 1000
                    kf_screenshots = {}

                    for pct in keyframe_pcts:
                        target_ms = pct * max_duration
                        page.evaluate(f"""() => {{
                            document.getAnimations().forEach(a => {{
                                a.pause();
                                a.currentTime = {target_ms};
                            }});
                        }}""")
                        page.wait_for_timeout(50)

                        pct_label = f"{int(pct * 100)}pct"
                        out_png = screenshots_dir / f"{stem}.{vp_name}.anim_{pct_label}.png"
                        page.screenshot(
                            path=str(out_png), full_page=True,
                            type="png", animations="allow",
                        )
                        kf_screenshots[pct_label] = str(out_png)

                    # Filmstrip capture — more frames for VLM judging
                    frame_images: list[Image.Image] = []
                    frame_pcts: list[float] = []
                    for i in range(n_filmstrip_frames):
                        fpct = i / max(n_filmstrip_frames - 1, 1)
                        target_ms = fpct * max_duration
                        page.evaluate(f"""() => {{
                            document.getAnimations().forEach(a => {{
                                a.pause();
                                a.currentTime = {target_ms};
                            }});
                        }}""")
                        page.wait_for_timeout(30)
                        frame_bytes = page.screenshot(
                            full_page=False, type="png", animations="allow",
                        )
                        frame_images.append(Image.open(__import__("io").BytesIO(frame_bytes)))
                        frame_pcts.append(fpct)

                    filmstrip_path = None
                    if frame_images:
                        fw, fh = frame_images[0].size
                        cols = min(5, len(frame_images))
                        rows = (len(frame_images) + cols - 1) // cols
                        label_h = 20
                        pad = 2
                        strip = Image.new("RGB",
                                          (cols * (fw + pad) - pad, rows * (fh + label_h + pad) - pad),
                                          (255, 255, 255))
                        draw = ImageDraw.Draw(strip)
                        for idx, frame in enumerate(frame_images):
                            c, r = idx % cols, idx // cols
                            x, y = c * (fw + pad), r * (fh + label_h + pad)
                            ms = frame_pcts[idx] * max_duration
                            draw.text((x + 2, y), f"{int(frame_pcts[idx]*100)}% ({int(ms)}ms)", fill=(0, 0, 0))
                            strip.paste(frame, (x, y + label_h))
                        filmstrips_subdir = screenshots_dir / "filmstrips"
                        filmstrips_subdir.mkdir(parents=True, exist_ok=True)
                        filmstrip_path = filmstrips_subdir / f"{stem}.{vp_name}.filmstrip.png"
                        strip.save(str(filmstrip_path), optimize=True)

                    meta_path = screenshots_dir / f"{stem}.{vp_name}.animations.json"
                    meta_path.write_text(json.dumps(animation_meta, indent=2))

                    results[key] = {
                        "metadata": animation_meta,
                        "screenshots": kf_screenshots,
                        "filmstrip": str(filmstrip_path) if filmstrip_path else None,
                    }
                    ctx.close()
        finally:
            browser.close()

    return results


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
    # Structured arithmetic mean (VLM excluded by its weight=0 in METRIC_WEIGHTS).
    structured = _weighted_arith({k: v.score for k, v in results.items() if k != "vlm_judge"})
    # VLM is applied as a min() ceiling — content fabrication that structured
    # metrics undercount (chart values, icon glyphs, semantic correctness).
    vlm_score = results.get("vlm_judge").score if results.get("vlm_judge") else None
    # Overflow is applied as a partial multiplier: half of the base score is
    # multiplied by overflow_score, so a fully-broken responsive layout
    # (overflow=0) drags the composite down by 50% (vs. its previous floor of
    # 0.5). Overflow=1.0 leaves the score unchanged.
    overflow_res = results.get("overflow")
    overflow_score = overflow_res.score if (overflow_res and overflow_res.score is not None) else 1.0
    overflow_factor = 0.5 + 0.5 * overflow_score
    base = structured
    if vlm_score is not None:
        base = min(base, vlm_score)
    composite = base * overflow_factor
    subscores["_structured"] = structured
    subscores["_overflow_factor"] = overflow_factor
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


def _judge_all_animation_pairs(pairs):
    """Fan out VLM animation judgments in parallel. Returns dict keyed by '{page}.{vp}'."""
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {k: vlm_judge.MetricResult(name="vlm_animation", score=None,
                                          extra={"skipped": True,
                                                 "reason": "ANTHROPIC_API_KEY not set"})
                for k, _, _ in pairs}
    out = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(vlm_judge.judge_animation, ref, cand): key for key, ref, cand in pairs}
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                out[key] = fut.result()
            except Exception as e:
                out[key] = vlm_judge.MetricResult(name="vlm_animation", score=None,
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
        candidate_dir=candidate_dir,
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

    # 4. Compose static score
    static_reward, per_page_harmonic = compose(per_page_viewport, ac.penalty_multiplier)

    # 5. Animation scoring (Part 2 tasks only)
    STRUCTURED_ANIM_WEIGHT = 0.40
    VLM_ANIM_WEIGHT = 0.60
    animated = _is_animated_task(reference_dir)
    animation_scores: dict = {}
    animation_reward = 0.0
    if animated:
        print("[grade] animated task detected — capturing agent animation keyframes + filmstrips...")
        agent_anim_t0 = time.time()
        agent_anim_results = _capture_agent_animation_keyframes(
            agent_html_dir, output_dir,
        )
        print(f"[grade] agent animation capture: {len(agent_anim_results)} pairs in {time.time()-agent_anim_t0:.1f}s")

        ref_anim_dir = reference_dir
        cand_anim_dir = output_dir / "animation_keyframes"

        # Collect VLM animation pairs for parallel judging
        vlm_anim_pairs = []
        for ref_meta_path in sorted(reference_dir.glob("*.animations.json")):
            parts = ref_meta_path.stem.split(".")
            if len(parts) < 3:
                continue
            vp_name = parts[-2]
            page_slug = ".".join(parts[:-2])
            if vp_name not in VIEWPORTS:
                continue
            ref_filmstrip = reference_dir / "filmstrips" / f"{page_slug}.{vp_name}.filmstrip.png"
            cand_filmstrip = cand_anim_dir / "filmstrips" / f"{page_slug}.{vp_name}.filmstrip.png"
            key = f"{page_slug}.{vp_name}"
            if ref_filmstrip.exists() and cand_filmstrip.exists():
                vlm_anim_pairs.append((key, ref_filmstrip, cand_filmstrip))

        # Fan out VLM animation judgments in parallel
        vlm_anim_results = _judge_all_animation_pairs(vlm_anim_pairs)
        print(f"[grade] VLM animation judge: {len(vlm_anim_results)} pairs")

        per_page_anim_scores: list[float] = []
        for ref_meta_path in sorted(reference_dir.glob("*.animations.json")):
            parts = ref_meta_path.stem.split(".")
            if len(parts) < 3:
                continue
            vp_name = parts[-2]
            page_slug = ".".join(parts[:-2])
            if vp_name not in VIEWPORTS:
                continue

            ref_meta = animation_metrics._load_animation_meta(ref_meta_path)
            cand_meta_path = cand_anim_dir / f"{page_slug}.{vp_name}.animations.json"
            cand_meta = animation_metrics._load_animation_meta(cand_meta_path)

            structured_score, anim_details = animation_metrics.compute_animation_score(
                ref_screenshots_dir=ref_anim_dir,
                cand_screenshots_dir=cand_anim_dir,
                page_slug=page_slug,
                vp_name=vp_name,
                ref_meta=ref_meta,
                cand_meta=cand_meta,
            )

            key = f"{page_slug}.{vp_name}"
            vlm_anim_res = vlm_anim_results.get(key)
            vlm_anim_score = vlm_anim_res.score if vlm_anim_res and vlm_anim_res.score is not None else None

            if vlm_anim_score is not None:
                combined = STRUCTURED_ANIM_WEIGHT * structured_score + VLM_ANIM_WEIGHT * vlm_anim_score
            else:
                combined = structured_score

            anim_details["_vlm_animation"] = {
                "score": vlm_anim_score,
                **(vlm_anim_res.extra if vlm_anim_res else {}),
            }
            anim_details["_structured_score"] = structured_score
            anim_details["_combined"] = combined
            animation_scores[key] = anim_details
            per_page_anim_scores.append(combined)

        animation_reward = float(np.mean(per_page_anim_scores)) if per_page_anim_scores else 0.0

    if animated:
        reward = STATIC_WEIGHT * static_reward + ANIMATION_WEIGHT * animation_reward
    else:
        reward = static_reward

    # 6. Write everything
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
    if animated:
        subscores["animated"] = True
        subscores["static_reward"] = static_reward
        subscores["animation_reward"] = animation_reward
        subscores["animation_weight"] = ANIMATION_WEIGHT
        subscores["static_weight"] = STATIC_WEIGHT
        subscores["animation_scores"] = animation_scores
        subscores["animation_structured_weight"] = STRUCTURED_ANIM_WEIGHT
        subscores["animation_vlm_weight"] = VLM_ANIM_WEIGHT
        subscores["animation_metric_weights"] = animation_metrics.ANIMATION_METRIC_WEIGHTS
    (output_dir / "subscores.json").write_text(json.dumps(subscores, indent=2))
    reward_file.write_text(f"{reward}\n")

    print(json.dumps(subscores, indent=2)[:5000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
