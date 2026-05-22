"""Create reference websites (and optionally package them as Harbor tasks).

Default: generation only. Inspect the output, then run with --package to write
Harbor task directories.

    cd /Users/siddhantmago/workspace/personal/work-trial

    # Phase 1 — generate websites only (default)
    .venv/bin/python -m pipeline.eval_gen.create_websites

    # Inspect at tasks_generated/_work/<site_id>/
    #   - <slug>.html          per-page HTML
    #   - styles.css           shared component library
    #   - screenshots/         per-(page, viewport) PNGs
    #   - _brand_spec.json     full spec
    #   - _brief.txt           creative brief
    #   - _summary.json        per-site stage results

    # Phase 2 — package the inspected sites as Harbor task directories
    .venv/bin/python -m pipeline.eval_gen.create_websites --package

Each packaged directory under tasks_generated/smoke/<NN-slug>/ is a self-
contained Harbor task with:
- the generated reference HTMLs + styles.css
- per-(page, viewport) reference PNGs rendered via the shipped Playwright
- the grader (pipeline/grader/* + pipeline/render.py) copied verbatim
- a base64'd oracle solve.sh that scores ~1.0

Stage 10 (Harbor job submission) is done manually:
    harbor run tasks_generated/smoke/<NN-slug> --agent claude

Smoke-wave simplifications vs full synthesis (see README.md):
- 5 sites only
- single renderer (Sonnet)
- no Verbalized Sampling on the brief (single call)
- no DreamSim / VLM critic / corpus audit thresholds
- pages_per_site = [5, 7] (smaller than production [7, 10])
"""
from __future__ import annotations

import json
import random
import shutil
import time
import traceback
from pathlib import Path

from pipeline.eval_gen.config import REPO_ROOT, DEFAULT
from pipeline.eval_gen.coherence import verify_site
from pipeline.eval_gen.generator.brand_spec import (
    BrandSpec,
    resolve_page_list,
    sample_brand_spec,
)
from pipeline.eval_gen.generator.brief import generate_brief
from pipeline.eval_gen.generator.library import generate_library
from pipeline.eval_gen.generator.pages import generate_page
from pipeline.eval_gen.render_validate import render_and_validate, validate_library_css


WORK_ROOT = REPO_ROOT / "reference_sites"


def _generate_one(spec: BrandSpec, site_work_dir: Path, cfg) -> dict:
    """Run stages 2–6 for a single site. Writes outputs to site_work_dir.

    Returns a dict suitable for inclusion in the smoke summary.
    """
    print("  [stage 2] generating brief...")
    brief_out = generate_brief(spec, cfg=cfg)
    (site_work_dir / "_brief.txt").write_text(brief_out["brief"])
    print(f"    brief: {brief_out['output_tokens']} out tokens, {brief_out['latency_s']:.1f}s")

    MAX_LIBRARY_RETRIES = 2
    print(f"  [stage 3] generating component library (styles.css) (with up to {MAX_LIBRARY_RETRIES} retries)...")
    lib_prior_issues: list[str] = []
    lib_out = None
    lib_attempts = 0
    for lib_attempt in range(MAX_LIBRARY_RETRIES + 1):
        lib_attempts = lib_attempt + 1
        lib_attempt_note = f" (retry {lib_attempt})" if lib_attempt > 0 else ""
        print(f"    > library{lib_attempt_note}: generating...", flush=True)
        lib_out = generate_library(
            spec, brief_out["brief"], cfg=cfg, previous_issues=lib_prior_issues
        )
        (site_work_dir / "styles.css").write_text(lib_out["css"])
        print(f"    library{lib_attempt_note}: {lib_out['output_tokens']} out tokens, {lib_out['latency_s']:.1f}s")
        lib_issues = validate_library_css(lib_out["css"], site_work_dir, cfg)
        if not lib_issues:
            break
        lib_prior_issues = lib_issues
        print(f"      library validation issues: {lib_issues[:3]}; retrying...")
    else:
        # Loop fell through without break — we exhausted retries.
        print(f"    ! library still has issues after {lib_attempts} attempts; continuing anyway")

    MAX_VALIDATION_RETRIES = 2

    print(f"  [stage 4+5] generating + validating {len(spec.page_list)} pages (with up to {MAX_VALIDATION_RETRIES} retries each)...")
    page_meta: list[dict] = []
    validation_results: list[dict] = []
    for page in spec.page_list:
        is_dark = page["slug"] in spec.dark_mode_pages
        prior_issues: list[str] = []
        final_p_out = None
        final_vr = None
        attempts_used = 0
        for attempt in range(MAX_VALIDATION_RETRIES + 1):
            attempts_used = attempt + 1
            attempt_note = f" (retry {attempt})" if attempt > 0 else ""
            print(f"    > {page['slug']}{'  (dark)' if is_dark else ''}{attempt_note}: generating...", flush=True)
            p_out = generate_page(
                spec,
                brief_out["brief"],
                lib_out["css"],
                page,
                spec.page_list,
                is_dark=is_dark,
                cfg=cfg,
                previous_issues=prior_issues,
            )
            (site_work_dir / f"{page['slug']}.html").write_text(p_out["html"])
            cache_hit = p_out.get("cache_read_tokens", 0)
            cache_new = p_out.get("cache_creation_tokens", 0)
            cache_note = f", cache: {cache_hit} read / {cache_new} created" if (cache_hit or cache_new) else ""
            retry_note = f" (retry {attempt})" if attempt > 0 else ""
            print(f"    - {page['slug']}{'  (dark)' if is_dark else ''}{retry_note}: {p_out['output_tokens']} out, {p_out['latency_s']:.1f}s{cache_note}")
            vr = render_and_validate(
                site_dir=site_work_dir, page_slug=page["slug"], cfg=cfg, spec=spec,
            )
            final_p_out = p_out
            final_vr = vr
            if not vr.issues:
                break
            prior_issues = vr.issues
            print(f"      validation issues: {vr.issues[:3]}; retrying...")

        page_meta.append({
            "slug": page["slug"],
            "attempts": attempts_used,
            **{k: v for k, v in final_p_out.items() if k != "html"},
        })
        validation_results.append({
            "slug": page["slug"],
            "ok": final_vr.ok and not final_vr.issues,
            "issues": final_vr.issues,
            "attempts": attempts_used,
            "screenshots": [str(p) for p in final_vr.screenshots.values()],
        })
        if final_vr.issues:
            print(f"    ! {page['slug']}: still has {len(final_vr.issues)} issue(s) after {attempts_used} attempts: {final_vr.issues[:3]}")

    print("  [stage 6] coherence verification (header/footer + tokens)...")
    coh = verify_site(site_work_dir, [p["slug"] for p in spec.page_list])
    print(f"    header_consistent={coh.header_consistent} footer_consistent={coh.footer_consistent}")
    print(f"    distinct_font_families={coh.distinct_font_families} distinct_colors={coh.distinct_colors}")

    # Persist enough state that --package can run later without regenerating.
    (site_work_dir / "_brand_spec.json").write_text(json.dumps(spec.to_dict(), indent=2))
    site_summary = {
        "site_id": spec.site_id,
        "ok": True,
        "n_pages": len(spec.page_list),
        "n_dark_mode_pages": len(spec.dark_mode_pages),
        "validation": validation_results,
        "coherence": coh.__dict__,
        "tokens_in": brief_out["input_tokens"] + lib_out["input_tokens"] + sum(p["input_tokens"] for p in page_meta),
        "tokens_out": brief_out["output_tokens"] + lib_out["output_tokens"] + sum(p["output_tokens"] for p in page_meta),
    }
    (site_work_dir / "_summary.json").write_text(json.dumps(site_summary, indent=2))
    return site_summary



def cmd_generate(cfg) -> int:
    """Phase 1 — generate websites to _work/. No Harbor packaging."""
    print(f">>> Phase 1: GENERATE (no packaging)")
    print(f">>> N_TASKS={cfg.n_tasks}, PAGES_PER_SITE={cfg.pages_per_site_range}")
    print(f">>> work root: {WORK_ROOT}")
    print(f">>> renderer:  {cfg.renderer_model}")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    summary: list[dict] = []
    started = time.time()

    for i in range(cfg.n_tasks):
        idx = i + 1
        print(f"\n===== site {idx}/{cfg.n_tasks} =====")
        rng = random.Random(f"{cfg.seed}-pages-{idx}")
        n_pages = rng.randint(*cfg.pages_per_site_range)

        spec = sample_brand_spec(idx, seed=cfg.seed)
        resolve_page_list(spec, n_pages, rng)
        print(f"  spec: {spec.business_name} / {spec.domain['name']} / {spec.archetype['name']}")
        print(f"        {n_pages} pages: {[p['slug'] for p in spec.page_list]}")
        if spec.dark_mode_pages:
            print(f"        dark mode pages: {spec.dark_mode_pages}")

        site_work_dir = WORK_ROOT / spec.site_id
        if site_work_dir.exists():
            shutil.rmtree(site_work_dir)
        site_work_dir.mkdir(parents=True)

        try:
            site_summary = _generate_one(spec, site_work_dir, cfg)
            summary.append(site_summary)
        except Exception as e:
            print(f"  FAILED: {e}")
            traceback.print_exc()
            summary.append({"site_id": spec.site_id, "ok": False, "error": str(e)})

    elapsed = time.time() - started
    (WORK_ROOT / "_smoke_summary.json").write_text(json.dumps({
        "elapsed_s": elapsed,
        "n_tasks_requested": cfg.n_tasks,
        "n_tasks_generated": sum(1 for s in summary if s.get("ok")),
        "tokens_in_total": sum(s.get("tokens_in", 0) for s in summary if s.get("ok")),
        "tokens_out_total": sum(s.get("tokens_out", 0) for s in summary if s.get("ok")),
        "sites": summary,
    }, indent=2))

    n_ok = sum(1 for s in summary if s.get("ok"))
    print(f"\n>>> done in {elapsed:.1f}s. generated {n_ok}/{cfg.n_tasks} sites")
    print(f">>> work root: {WORK_ROOT}")
    print(f">>> inspect:")
    for s in summary:
        if s.get("ok"):
            d = WORK_ROOT / s["site_id"]
            html_files = sorted(d.glob("*.html"))
            shots = sorted((d / "screenshots").glob("*.png")) if (d / "screenshots").exists() else []
            print(f"     {d}")
            print(f"       {len(html_files)} HTMLs, {len(shots)} screenshots")
    print(f"\n>>> when satisfied, package with: .venv/bin/python -m pipeline.eval_gen.create_websites --package")
    return 0 if n_ok == cfg.n_tasks else 1



# The Modal entrypoint (create_websites_modal.py) is the only invocation path
# for this module. cmd_generate is called directly from there; there is no
# local CLI. Packaging is handled by pipeline/package.py.
