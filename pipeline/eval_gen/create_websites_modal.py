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
    )
    .run_commands(
        "playwright install --with-deps chromium",
        "fc-cache -f -v > /dev/null 2>&1 || true",
    )
    # Bring the entire pipeline/ directory into /work/pipeline so
    # `from pipeline.eval_gen...` and `from pipeline.grader...` resolve.
    .add_local_dir(str(REPO_ROOT / "pipeline"), remote_path="/work/pipeline")
)


app = modal.App("worktrial-create-websites-v4", image=image)

# Persistent volume for the generated output. Phase 1 writes reference_sites/<site>/
# here; Phase 2 reads it back to assemble Harbor task directories under
# the same volume at smoke/<site>/. The local entrypoint downloads the
# volume contents to the user's filesystem after each phase.
output_volume = modal.Volume.from_name(
    "worktrial-eval-gen-output", create_if_missing=True
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

    cfg = config.DEFAULT
    config.REPO_ROOT = Path("/work")
    cfg.output_root = Path(VOLUME_MOUNT_PATH) / "tasks"
    cfg.reference_sites_root = Path(VOLUME_MOUNT_PATH) / "reference_sites"
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


@app.function(
    timeout=1800,
    volumes={VOLUME_MOUNT_PATH: output_volume},
    cpu=2.0,
    memory=4096,
)
def package_remote() -> dict:
    """Phase 2 on Modal: package the already-generated _work/ sites as Harbor tasks."""
    import sys
    sys.path.insert(0, "/work")

    from pipeline.eval_gen import config, create_websites
    config.REPO_ROOT = Path("/work")
    config.DEFAULT.output_root = Path(VOLUME_MOUNT_PATH) / "tasks"
    config.DEFAULT.reference_sites_root = Path(VOLUME_MOUNT_PATH) / "reference_sites"
    create_websites.WORK_ROOT = config.DEFAULT.reference_sites_root

    exit_code = create_websites.cmd_package(config.DEFAULT)
    output_volume.commit()

    summary_path = config.DEFAULT.output_root / "_package_summary.json"
    summary = {}
    if summary_path.exists():
        import json
        summary = json.loads(summary_path.read_text())
    return {"exit_code": exit_code, "summary": summary}


# ---------------------------------------------------------------------------
# Volume <-> local sync helpers
# ---------------------------------------------------------------------------


def _download_volume_subtree(remote_prefix: str, local_dir: Path) -> int:
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
            n += _download_volume_subtree(entry.path, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as f:
                for chunk in output_volume.read_file(entry.path):
                    f.write(chunk)
            n += 1
    return n


# ---------------------------------------------------------------------------
# Local entrypoints
# ---------------------------------------------------------------------------


@app.local_entrypoint()
def generate(n_sites: int = 5, run_suffix: str = ""):
    """Phase 1 — generate `n_sites` reference websites in parallel.

    Sites fan out across Modal containers via `.map()`. Per-site pipeline
    (brief → library → pages → render → coherence) runs sequentially inside
    each container. Per-site config (page count, viewports, models, etc.)
    comes from config.DEFAULT.

    Examples:
        modal run pipeline/eval_gen/create_websites_modal.py::generate
        modal run pipeline/eval_gen/create_websites_modal.py::generate --n-sites 10
        modal run pipeline/eval_gen/create_websites_modal.py::generate --run-suffix v2
    """
    import random as _random
    import secrets as _secrets
    from pipeline.eval_gen.config import DEFAULT as cfg
    from pipeline.eval_gen.generator.brand_spec import (
        sample_brand_specs,
        resolve_page_list,
    )

    # Per-run random suffix — every site_id in this run is tagged with it
    # so parallel/repeated runs don't clobber each other's directories on
    # the shared Modal volume. It's also folded into the spec shuffle seed
    # so each run produces a genuinely different set of sites, not just
    # renamed dirs. Caller can pin a value (e.g. "v2") for reproducibility.
    if not run_suffix:
        run_suffix = _secrets.token_hex(2)
    print(f">>> Phase 1: n_sites={n_sites}, run_suffix={run_suffix!r}, "
          f"pages_per_site={cfg.pages_per_site_range}, "
          f"parallel_viewports={cfg.parallel_viewports}")

    # Pre-compute the FULL spec for each site locally. Shuffle-then-iterate
    # guarantees no two sites in the same run share an axis value (up to
    # the smallest pool size — see brand_spec.sample_brand_specs).
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
    print(f">>> {n_ok}/{len(results)} sites generated")

    print(">>> downloading reference_sites/ from Modal volume...")
    local_ref = REPO_ROOT / "reference_sites"
    n_files = _download_volume_subtree("/reference_sites", local_ref)
    print(f">>> downloaded {n_files} file(s) -> {local_ref}")
    print(f">>> inspect screenshots at {local_ref}/<site>/screenshots/")
    print(f">>> when satisfied, run:  modal run pipeline/eval_gen/create_websites_modal.py::package")


@app.local_entrypoint()
def package():
    """Run Phase 2 on Modal, then sync tasks/ back to local."""
    print(">>> kicking off Phase 2 on Modal...")
    result = package_remote.remote()
    print(f">>> Modal function returned exit_code={result['exit_code']}")

    print(">>> downloading tasks/ from Modal volume...")
    local_smoke = REPO_ROOT / "tasks"
    n_files = _download_volume_subtree("/tasks", local_smoke)
    print(f">>> downloaded {n_files} file(s) -> {local_smoke}")
    print(f">>> next: harbor run {local_smoke}/<site> --agent claude")
