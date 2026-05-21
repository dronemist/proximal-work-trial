"""Stage 9 — write a Harbor task directory for one generated site.

Per-site output layout (mirrors tasks/002-lumen-multipage):

    tasks_generated/smoke/<NN-slug>/
    ├── task.toml
    ├── instruction.md
    ├── environment/
    │   ├── Dockerfile               (copied verbatim from tasks/002-lumen-multipage)
    │   ├── entrypoint.sh            (copied verbatim)
    │   ├── proxy.py                 (copied verbatim)
    │   └── reference/               (per-page screenshots — what the agent sees)
    │       ├── {page}.{viewport}.png ...
    ├── tests/
    │   ├── grade.py                 (copied verbatim from pipeline/grader/)
    │   ├── metrics.py               (copied verbatim from pipeline/grader/)
    │   ├── anticheat.py             (copied verbatim from pipeline/grader/)
    │   ├── render.py                (copied verbatim from pipeline/render.py)
    │   ├── test.sh                  (copied verbatim from tasks/002-lumen-multipage/tests/)
    │   └── reference_truth/         (ground truth — same PNGs, verifier-only)
    │       ├── {page}.{viewport}.png ...
    ├── solution/
    │   └── solve.sh                 (base64 tar.gz of HTMLs + styles.css)
    └── _generated/                  (provenance — not used by Harbor)
        ├── brand_spec.json
        ├── brief.txt
        └── coherence_report.json

The per-task grader files (tests/*.py + tests/test.sh + environment/*) are
copied directly from the existing pipeline so the agent runs against the
shipped grader untouched. If pipeline/grader/ changes, regenerate.
"""
from __future__ import annotations

import base64
import io
import json
import shutil
import tarfile
from dataclasses import asdict
from pathlib import Path

from pipeline.eval_gen.config import REPO_ROOT, DEFAULT
from pipeline.eval_gen.generator.brand_spec import BrandSpec


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Files copied verbatim from existing pipeline & a reference task.
# We use 002-lumen-multipage as the template because it's already multi-page.
GRADER_SRC_FILES = ["grade.py", "metrics.py", "anticheat.py"]
ENV_SRC_FILES = ["Dockerfile", "entrypoint.sh", "proxy.py"]


def _copy_grader_files(target_tests_dir: Path, cfg=DEFAULT) -> None:
    """Copy grade.py, metrics.py, anticheat.py from pipeline/grader/, plus
    pipeline/render.py (which the grader sources at runtime), into the
    task's tests/ directory.
    """
    target_tests_dir.mkdir(parents=True, exist_ok=True)
    for fname in GRADER_SRC_FILES:
        src = cfg.grader_src_dir / fname
        shutil.copy(src, target_tests_dir / fname)
    shutil.copy(cfg.render_src_path, target_tests_dir / "render.py")

    # test.sh copied from the existing multipage task — viewport-agnostic
    # shell wrapper that just invokes the grader.
    template_test_sh = REPO_ROOT / "tasks" / "002-lumen-multipage" / "tests" / "test.sh"
    shutil.copy(template_test_sh, target_tests_dir / "test.sh")
    (target_tests_dir / "test.sh").chmod(0o755)


def _copy_env_files(target_env_dir: Path, cfg=DEFAULT) -> None:
    target_env_dir.mkdir(parents=True, exist_ok=True)
    src = cfg.reference_env_template_dir
    for fname in ENV_SRC_FILES:
        shutil.copy(src / fname, target_env_dir / fname)
    (target_env_dir / "entrypoint.sh").chmod(0o755)


def _write_task_toml(
    target_dir: Path,
    spec: BrandSpec,
    n_pages: int,
) -> None:
    template = (TEMPLATES_DIR / "task.toml.template").read_text()
    text = template.format(
        task_name=spec.site_id,
        n_pages=n_pages,
        domain_label=spec.domain["label"],
        domain_keyword=spec.domain["name"],
        domain_name=spec.domain["name"],
        archetype_name=spec.archetype["name"],
    )
    (target_dir / "task.toml").write_text(text)


def _write_instruction(target_dir: Path, spec: BrandSpec) -> None:
    template = (TEMPLATES_DIR / "instruction.md.template").read_text()
    n_pages = len(spec.page_list)
    page_listing = "\n".join(
        f"{p['slug']}.desktop.png" for p in spec.page_list
    )
    app_listing = "\n".join(f"/app/{p['slug']}.html" for p in spec.page_list)
    text = template.format(
        n_screenshots=n_pages,
        n_pages=n_pages,
        page_listing=page_listing,
        app_listing=app_listing,
    )
    (target_dir / "instruction.md").write_text(text)


def _populate_reference_dir(
    target_ref_dir: Path,
    site_dir: Path,
    page_slugs: list[str],
    viewport_names: list[str],
) -> int:
    target_ref_dir.mkdir(parents=True, exist_ok=True)
    n_copied = 0
    for slug in page_slugs:
        for vp in viewport_names:
            src = site_dir / "screenshots" / f"{slug}.{vp}.png"
            if not src.exists():
                # Don't fail packaging — the smoke test surfaces partial-render
                # sites for the user to inspect.
                continue
            shutil.copy(src, target_ref_dir / f"{slug}.{vp}.png")
            n_copied += 1
    return n_copied


def _build_solution_tarball(site_dir: Path, page_slugs: list[str]) -> str:
    """Produce base64-encoded tar.gz of the reference HTMLs + styles.css.

    solve.sh extracts this into /app/. Anything in the tarball must be
    a real filename the agent's instruction.md mentions.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        css_path = site_dir / "styles.css"
        if css_path.exists():
            tf.add(css_path, arcname="styles.css")
        for slug in page_slugs:
            html_path = site_dir / f"{slug}.html"
            if html_path.exists():
                tf.add(html_path, arcname=f"{slug}.html")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _write_solve_sh(target_dir: Path, b64_payload: str) -> None:
    """Mirror tasks/002-lumen-multipage/solution/solve.sh format."""
    content = (
        "#!/bin/bash\n"
        "# Oracle solution: extracts the canonical reference site into /app/.\n"
        "# Used only by 'harbor run --agent oracle'; not visible to other agents.\n"
        "# This must score reward ≈ 1.0 — if not, the grader is broken.\n"
        "set -euo pipefail\n\n"
        "base64 -d <<'B64' | tar xzf - -C /app/\n"
        f"{_chunk_base64(b64_payload)}\n"
        "B64\n\n"
        'echo "wrote /app/ contents:"\n'
        "ls /app/\n"
    )
    sol_dir = target_dir / "solution"
    sol_dir.mkdir(parents=True, exist_ok=True)
    (sol_dir / "solve.sh").write_text(content)
    (sol_dir / "solve.sh").chmod(0o755)


def _chunk_base64(s: str, width: int = 76) -> str:
    return "\n".join(s[i : i + width] for i in range(0, len(s), width))


def _write_provenance(
    target_dir: Path,
    spec: BrandSpec,
    brief_text: str,
    coherence_report: dict | None,
) -> None:
    prov_dir = target_dir / "_generated"
    prov_dir.mkdir(parents=True, exist_ok=True)
    (prov_dir / "brand_spec.json").write_text(json.dumps(spec.to_dict(), indent=2))
    (prov_dir / "brief.txt").write_text(brief_text)
    if coherence_report is not None:
        (prov_dir / "coherence_report.json").write_text(json.dumps(coherence_report, indent=2))


def package_site(
    *,
    spec: BrandSpec,
    site_dir: Path,
    brief_text: str,
    coherence_report: dict | None,
    cfg=DEFAULT,
) -> Path:
    """Write the Harbor task scaffold for `spec`.

    site_dir is the `reference_sites/<site_id>/` directory containing:
      - <slug>.html for every page
      - styles.css

    PNGs are NOT copied — `pipeline/build_task.py` is the canonical builder
    that renders PNGs into `environment/reference/` and `tests/reference_truth/`
    after this scaffold exists. Re-running build_task.py is idempotent (manifest
    hash check), so the task is grade-ready after both steps.
    """
    target = cfg.output_root / spec.site_id
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    page_slugs = [p["slug"] for p in spec.page_list]

    _write_task_toml(target, spec, len(page_slugs))
    _write_instruction(target, spec)
    _copy_env_files(target / "environment", cfg=cfg)
    _copy_grader_files(target / "tests", cfg=cfg)
    _write_solve_sh(target, _build_solution_tarball(site_dir, page_slugs))
    _write_provenance(target, spec, brief_text, coherence_report)
    # Hint to operators: run build_task.py to populate the PNGs.
    print(f"  scaffold written -> {target}")
    print(f"  next: python pipeline/build_task.py {target.relative_to(target.parent.parent)}")
    return target
