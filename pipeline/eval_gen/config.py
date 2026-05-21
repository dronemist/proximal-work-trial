"""Pipeline tunables.

The two main knobs the synthesis calls out are N_TASKS and PAGES_PER_SITE.
Smoke-wave defaults are set here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class GenConfig:
    n_tasks: int = 5
    pages_per_site_range: tuple[int, int] = (5, 7)
    oversample_factor: float = 1.0  # smoke: no oversample, every site ships
    seed: int = 42

    # Stage 4 — rendering. Smoke uses a single Sonnet renderer; mixed models
    # come in later phases.
    renderer_model: str = "claude-opus-4-7"
    library_model: str = "claude-opus-4-7"
    brief_model: str = "claude-opus-4-7"
    max_tokens_per_page: int = 32_000
    temperature: float = 0.9

    # Output paths
    # Reference sources (HTML/CSS/screenshots/metadata) — read by
    # pipeline/build_task.py at task-build time.
    reference_sites_root: Path = field(default_factory=lambda: REPO_ROOT / "reference_sites")

    # Harbor task scaffolds (task.toml, instruction.md, environment/, tests/,
    # solution/). build_task.py later populates environment/reference/ and
    # tests/reference_truth/ with rendered PNGs.
    output_root: Path = field(default_factory=lambda: REPO_ROOT / "tasks")
    grader_src_dir: Path = field(default_factory=lambda: REPO_ROOT / "pipeline" / "grader")
    render_src_path: Path = field(default_factory=lambda: REPO_ROOT / "pipeline" / "render.py")
    reference_env_template_dir: Path = field(
        default_factory=lambda: REPO_ROOT / "tasks" / "002-lumen-multipage" / "environment"
    )

    # Stage 5 — render validation viewports. Match existing
    # pipeline/grader/grade.py VIEWPORTS exactly so the generated tasks reuse
    # the shipped grader unchanged.
    # Desktop-only smoke (R12) — responsive references unreliable; mobile/tablet
    # references degraded the RL gradient. Re-enable per-viewport for pilot
    # only after the reference generator can produce responsive output reliably.
    viewports: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {
            "desktop": (1440, 900),
        }
    )

    # Stage 5 structural floor
    min_dom_depth: int = 4
    min_tag_count: int = 15

    # Parallelism knobs (smoke defaults to 1/1 — sequential, unchanged).
    parallel_sites: int = 1            # Modal containers running concurrently
    parallel_viewports: int = 1        # Playwright contexts per page (1 = sequential)

    # Screenshot height clip. 0 = no clip (true full-page). Use a positive
    # value (e.g. 20000) in pilot/production to guard against pathological
    # tall-page renders triggering memory spikes in concurrent contexts.
    screenshot_max_height: int = 0

    # Modal container memory (MB). Smoke fits in 4 GB; pilot bumps to 8 GB
    # to give the 3-way concurrent viewport renders headroom.
    modal_memory_mb: int = 4096


# Single shared config. `n_sites` is passed at runtime via the Modal CLI
# entrypoint. Parallelism is on by default (sites fan out across Modal
# containers via `.map()`).
DEFAULT = GenConfig(
    pages_per_site_range=(5, 5),
    parallel_sites=5,
    parallel_viewports=3,
    screenshot_max_height=0,
    modal_memory_mb=8192,
)
