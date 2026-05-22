"""Create reference websites on Modal — same code, deterministic Linux env.

Local prerequisites (one-time):

    pip install modal
    modal token new
    modal secret create anthropic-api-key ANTHROPIC_API_KEY=sk-ant-...

Usage:

    # Phase 1 — generate websites on Modal; sync back to local for inspection
    modal run pipeline/eval_gen/create_websites_modal.py::generate

    # Inspect at reference_sites/ (downloaded from the Modal volume)
    open reference_sites/001-*/screenshots/*.png

    # Phase 2 — package the generated sites as Harbor task directories
    modal run pipeline/eval_gen/create_websites_modal.py::package

After packaging, tasks/ holds the Harbor task directories.

What's on Modal vs local:
  - Modal container runs all LLM calls (Stages 2–4), Playwright rendering
    (Stage 5), and packaging (Stage 9). The container image pins Chromium
    + fonts so the reference matches what the grader sees.
  - Local entrypoint just kicks off the function and syncs the output
    volume back to the local filesystem when it completes.

Cost: ~$0.05 of Modal compute for smoke (5 sites × ~6 min on a small CPU
container). The LLM API spend (~$3–5) dominates total cost regardless.
"""
from __future__ import annotations

from pathlib import Path

import modal

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Image: Ubuntu 24.04 + Playwright (matches pipeline/render_on_modal.py and
# the verifier container) + the anthropic SDK + our eval_gen package source.
# ---------------------------------------------------------------------------

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("ca-certificates", "curl", "fonts-liberation", "fonts-dejavu", "fontconfig")
    .pip_install(
        "playwright==1.49.0",
        "pillow==11.0.0",
        "numpy==2.1.3",
        "anthropic>=0.40.0",
        "scikit-image>=0.22.0",
        "scipy>=1.12.0",
    )
    .run_commands(
        "playwright install --with-deps chromium",
        "fc-cache -f -v > /dev/null 2>&1 || true",
    )
    # Bring the entire pipeline/ directory into /work/pipeline so
    # `from pipeline.eval_gen...` and `from pipeline.grader...` resolve.
    .add_local_dir(str(REPO_ROOT / "pipeline"), remote_path="/work/pipeline")
)


app = modal.App("worktrial-create-websites-v7", image=image)

# Persistent volume for the generated output. Phase 1 writes reference_sites/<site>/
# here; Phase 2 reads it back to assemble Harbor task directories under
# the same volume at smoke/<site>/. The local entrypoint downloads the
# volume contents to the user's filesystem after each phase.
output_volume = modal.Volume.from_name(
    "worktrial-eval-gen-v6", create_if_missing=True
)

VOLUME_MOUNT_PATH = "/work/output"
ANTHROPIC_SECRET = modal.Secret.from_name("anthropic-api-key")


# ---------------------------------------------------------------------------
# Container functions
# ---------------------------------------------------------------------------


@app.function(
    timeout=3600,
    secrets=[ANTHROPIC_SECRET],
    volumes={VOLUME_MOUNT_PATH: output_volume},
    cpu=2.0,
    memory=8192,
)
def generate_one_site_remote(args: dict) -> dict:
    """One Modal container per site. `.map()` runs these concurrently.

    args = {
        "spec": dict (full BrandSpec serialized via asdict),
        "n_pages": int,
        "run_suffix": str,
    }
    """
    import shutil as _shutil
    import sys as _sys
    import traceback as _traceback

    _sys.path.insert(0, "/work")
    from pipeline.eval_gen import config, create_websites
    from pipeline.eval_gen.generator.brand_spec import BrandSpec

    cfg = config.ANIMATED if args.get("animated", False) else config.DEFAULT
    config.REPO_ROOT = Path("/work")
    run_suffix = args.get("run_suffix", "default")
    run_root = Path(VOLUME_MOUNT_PATH) / "task2" / run_suffix
    cfg.output_root = run_root / "tasks"
    cfg.reference_sites_root = run_root / "reference_sites"
    create_websites.WORK_ROOT = cfg.reference_sites_root

    # Local entrypoint pre-computed the spec (incl. page_list, dark_mode_pages)
    # to guarantee cross-site axis uniqueness. Reconstruct the dataclass here.
    # `theme_mode` is a derived property; strip it from the kwargs since it
    # isn't a field.
    spec_kwargs = {k: v for k, v in args["spec"].items() if k != "theme_mode"}
    spec = BrandSpec(**spec_kwargs)
    n_pages = args["n_pages"]

    site_work_dir = create_websites.WORK_ROOT / spec.site_id
    if site_work_dir.exists():
        _shutil.rmtree(site_work_dir)
    site_work_dir.mkdir(parents=True)

    print(f"=== {spec.site_id}: {spec.business_name} / {spec.domain['name']} "
          f"({n_pages} pages, theme={spec.theme_mode}) ===")
    try:
        site_summary = create_websites._generate_one(spec, site_work_dir, cfg)

        # Package into a Harbor task (scaffold + render PNGs) in the same
        # container — Playwright + Chromium are already available.
        if args.get("package", True):
            _sys.path.insert(0, "/work/pipeline")
            _sys.path.insert(0, "/work/pipeline/grader")
            from package import package_one_local

            tasks_root = run_root / "tasks"
            print(f"  [package] scaffolding + rendering → {tasks_root / spec.site_id}")
            package_one_local(site_work_dir, output_root=tasks_root)

        output_volume.commit()
        return site_summary
    except Exception as e:
        _traceback.print_exc()
        output_volume.commit()
        return {"site_id": spec.site_id, "ok": False, "error": str(e)}


# NOTE: the old single-container `generate_remote` was removed when smoke moved
# to parallel — both `::generate` (smoke) and `::generate_parallel` (pilot) now
# go through `generate_one_site_remote.map(...)`. Restore from git history if a
# pure-sequential fallback is ever needed.


# ---------------------------------------------------------------------------
# Volume <-> local sync helpers
# ---------------------------------------------------------------------------


def _download_volume_subtree(remote_prefix: str, local_dir: Path, depth: int = 0) -> int:
    """Pull every file under `remote_prefix` in the volume to `local_dir`.

    Returns count of files downloaded. Skips directories.
    """
    local_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    try:
        entries = list(output_volume.iterdir(remote_prefix))
    except Exception:
        entries = []
    for entry in entries:
        rel = entry.path[len(remote_prefix):].lstrip("/")
        target = local_dir / rel
        if entry.type == modal.volume.FileEntryType.DIRECTORY:
            if depth < 2:
                print(f"  downloading {entry.path}/...", flush=True)
            n += _download_volume_subtree(entry.path, target, depth + 1)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as f:
                for chunk in output_volume.read_file(entry.path):
                    f.write(chunk)
            n += 1
            if depth < 2:
                print(f"    {rel}", flush=True)
    return n


# ---------------------------------------------------------------------------
# Local entrypoints
# ---------------------------------------------------------------------------


@app.local_entrypoint()
def generate(n_sites: int = 5, run_suffix: str = "", pages: int = 0):
    """Phase 1 — generate `n_sites` reference websites in parallel.

    Sites fan out across Modal containers via `.map()`. Per-site pipeline
    (brief → library → pages → render → coherence) runs sequentially inside
    each container. Per-site config (page count, viewports, models, etc.)
    comes from config.DEFAULT.

    Examples:
        modal run pipeline/eval_gen/create_websites_modal.py::generate
        modal run pipeline/eval_gen/create_websites_modal.py::generate --n-sites 10
        modal run pipeline/eval_gen/create_websites_modal.py::generate --run-suffix v2
        modal run pipeline/eval_gen/create_websites_modal.py::generate --n-sites 1 --pages 8
    """
    import random as _random
    import secrets as _secrets
    from pipeline.eval_gen.config import DEFAULT as cfg
    from pipeline.eval_gen.generator.brand_spec import (
        sample_brand_specs,
        resolve_page_list,
    )

    if pages > 0:
        cfg.pages_per_site_range = (pages, pages)

    if not run_suffix:
        run_suffix = _secrets.token_hex(2)
    print(f">>> Phase 1: n_sites={n_sites}, run_suffix={run_suffix!r}, "
          f"pages_per_site={cfg.pages_per_site_range}, "
          f"parallel_viewports={cfg.parallel_viewports}")

    all_specs = sample_brand_specs(n_sites=n_sites, seed=cfg.seed, run_suffix=run_suffix)
    site_args = []
    for i, spec in enumerate(all_specs):
        idx = i + 1
        rng_pages = _random.Random(f"{cfg.seed}-{run_suffix}-pages-{idx}")
        n_pages = rng_pages.randint(*cfg.pages_per_site_range)
        resolve_page_list(spec, n_pages, rng_pages)
        print(f"    site {idx}: {spec.site_id}  archetype={spec.archetype['name']}  palette={spec.palette['name']}  theme={spec.theme_mode}")
        site_args.append({"spec": spec.to_dict(), "n_pages": n_pages, "run_suffix": run_suffix})

    print(f">>> dispatching {len(site_args)} site jobs (Modal .map())...")
    results = list(generate_one_site_remote.map(site_args))
    n_ok = sum(1 for r in results if r.get("ok"))
    print(f">>> {n_ok}/{len(results)} sites generated + packaged as Harbor tasks")
    print(f">>> download both reference_sites/ and tasks/:")
    print(f">>>   modal run pipeline/eval_gen/create_websites_modal.py::download")
    print(f">>> download tasks only:")
    print(f">>>   modal run pipeline/eval_gen/create_websites_modal.py::download --what tasks")


@app.local_entrypoint()
def retry(site_index: int, n_sites: int = 10, run_suffix: str = ""):
    """Re-run a single failed site by its 1-based index within the original run.

    Recomputes the same spec deterministically (same seed + run_suffix + index)
    and dispatches it to a single Modal container.

    Example:
        modal run pipeline/eval_gen/create_websites_modal.py::retry --site-index 4 --n-sites 10 --run-suffix v7adv
    """
    import random as _random
    from pipeline.eval_gen.config import DEFAULT as cfg
    from pipeline.eval_gen.generator.brand_spec import (
        sample_brand_specs,
        resolve_page_list,
    )

    if not run_suffix:
        raise ValueError("--run-suffix is required for retry (must match the original run)")

    all_specs = sample_brand_specs(n_sites=n_sites, seed=cfg.seed, run_suffix=run_suffix)
    idx = site_index - 1
    if idx < 0 or idx >= len(all_specs):
        raise ValueError(f"site_index {site_index} out of range [1, {len(all_specs)}]")

    spec = all_specs[idx]
    rng_pages = _random.Random(f"{cfg.seed}-{run_suffix}-pages-{site_index}")
    n_pages = rng_pages.randint(*cfg.pages_per_site_range)
    resolve_page_list(spec, n_pages, rng_pages)

    print(f">>> retrying site {site_index}: {spec.site_id}  archetype={spec.archetype['name']}  palette={spec.palette['name']}  theme={spec.theme_mode}")
    result = generate_one_site_remote.remote({"spec": spec.to_dict(), "n_pages": n_pages, "run_suffix": run_suffix})
    ok = result.get("ok", False)
    print(f">>> {'success' if ok else 'FAILED'}: {result}")


@app.local_entrypoint()
def generate_animated(n_sites: int = 1, run_suffix: str = "", pages: int = 1, complexity: str = "medium"):
    """Generate animated reference websites on Modal.

    Defaults to 1 site, 1 page for quick iteration. Output is stored under
    a per-run subfolder on the Modal volume.

    Examples:
        modal run pipeline/eval_gen/create_websites_modal.py::generate_animated
        modal run pipeline/eval_gen/create_websites_modal.py::generate_animated --n-sites 3 --pages 5
        modal run pipeline/eval_gen/create_websites_modal.py::generate_animated --complexity hard
    """
    import random as _random
    import secrets as _secrets
    from pipeline.eval_gen.config import ANIMATED as cfg
    from pipeline.eval_gen.generator.brand_spec import (
        sample_brand_specs,
        resolve_page_list,
        resolve_animation_spec,
    )

    cfg.animation_complexity = complexity
    if pages > 0:
        cfg.pages_per_site_range = (pages, pages)

    if not run_suffix:
        run_suffix = f"anim-{_secrets.token_hex(2)}"
    print(f">>> Phase 1 (animated): n_sites={n_sites}, run_suffix={run_suffix!r}, "
          f"pages_per_site={cfg.pages_per_site_range}, "
          f"animation_complexity={complexity}")

    all_specs = sample_brand_specs(n_sites=n_sites, seed=cfg.seed, run_suffix=run_suffix)
    site_args = []
    for i, spec in enumerate(all_specs):
        idx = i + 1
        rng_pages = _random.Random(f"{cfg.seed}-{run_suffix}-pages-{idx}")
        n_pg = rng_pages.randint(*cfg.pages_per_site_range)
        resolve_page_list(spec, n_pg, rng_pages)
        rng_anim = _random.Random(f"{cfg.seed}-{run_suffix}-anim-{idx}")
        resolve_animation_spec(spec, rng_anim, complexity=complexity)
        print(f"    site {idx}: {spec.site_id}  archetype={spec.archetype['name']}  "
              f"palette={spec.palette['name']}  theme={spec.theme_mode}  "
              f"animations={len(spec.animation_spec.get('entrance_animations', []))} entrance")
        site_args.append({
            "spec": spec.to_dict(),
            "n_pages": n_pg,
            "run_suffix": run_suffix,
            "animated": True,
        })

    print(f">>> dispatching {len(site_args)} animated site jobs (Modal .map())...")
    results = list(generate_one_site_remote.map(site_args))
    n_ok = sum(1 for r in results if r.get("ok"))
    print(f">>> {n_ok}/{len(results)} animated sites generated")
    print(f">>> download with:")
    print(f">>>   modal run pipeline/eval_gen/create_websites_modal.py::download")


@app.local_entrypoint()
def download(target_dir: str = "", what: str = "both", run_suffix: str = ""):
    """Download reference_sites/ and/or tasks/ from Modal volume.

    --what controls what to download: "sites", "tasks", or "both" (default).
    --run-suffix downloads a specific run subfolder. If empty, downloads all runs.

    Examples:
        modal run pipeline/eval_gen/create_websites_modal.py::download
        modal run pipeline/eval_gen/create_websites_modal.py::download --run-suffix anim-abc1
        modal run pipeline/eval_gen/create_websites_modal.py::download --what tasks
    """
    base = Path(target_dir).resolve() if target_dir else REPO_ROOT
    remote_prefix = f"/task2/{run_suffix}" if run_suffix else "/task2"
    total = 0

    if what in ("sites", "both"):
        remote = f"{remote_prefix}/reference_sites" if run_suffix else remote_prefix
        local_ref = base / "reference_sites"
        if run_suffix:
            print(f">>> downloading task2/{run_suffix}/reference_sites/ -> {local_ref}")
            n = _download_volume_subtree(remote, local_ref)
        else:
            print(f">>> downloading task2/ -> {base / 'task2'}")
            n = _download_volume_subtree(remote_prefix, base / "task2")
        total += n
        print(f"    {n} file(s)")

    if what in ("tasks", "both"):
        if run_suffix:
            remote = f"{remote_prefix}/tasks"
            local_tasks = base / "tasks"
            print(f">>> downloading task2/{run_suffix}/tasks/ -> {local_tasks}")
            n = _download_volume_subtree(remote, local_tasks)
        else:
            print(f">>> downloading task2/ -> {base / 'task2'}")
            n = _download_volume_subtree(remote_prefix, base / "task2")
        total += n
        print(f"    {n} file(s)")

    print(f">>> downloaded {total} file(s) total")


