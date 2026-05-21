#!/usr/bin/env python3
"""
Phase 1 grader entrypoint.

Inputs:
  --agent-html      Path to agent's HTML directory (typically /app)
  --reference-dir   Directory containing reference PNGs (typically /tests/reference_truth)
  --output-dir      Directory to write subscores, diffs, anticheat report
  --reward-file     Path to write the scalar reward (default: /logs/verifier/reward.txt)
  --render          If passed, also renders the agent's HTML to PNGs first

Phase 1 simplifications:
  - Single page (index.html)
  - Single viewport (desktop 1440x900)
  - Single metric (SSIM)
  - Two anti-cheat checks
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add this script's dir + parent's pipeline/ to path so we can import siblings
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from anticheat import check_directory  # noqa: E402
from metrics import ssim  # noqa: E402


def render_agent_output(agent_html_dir: Path, render_out_dir: Path) -> dict:
    """Render every HTML file in the agent's output dir to a desktop PNG."""
    import importlib.util

    # Locate render.py — sibling of grader/, or in same dir if copied
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
        out_png = render_out_dir / f"{stem}.desktop.png"
        meta = render_mod.render(
            source=str(html_path),
            output_png=out_png,
            viewport_width=1440,
            viewport_height=900,
            full_page=True,
        )
        rendered[stem] = meta
    return rendered


def grade_one_page(reference_png: Path, candidate_png: Path) -> dict:
    return {"ssim": ssim(reference_png, candidate_png).__dict__}


def compose(per_page_scores: dict, anticheat_multiplier: float) -> float:
    if not per_page_scores:
        return 0.0
    per_page = [s["ssim"]["score"] for s in per_page_scores.values()]
    base = sum(per_page) / len(per_page)
    return float(base * anticheat_multiplier)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-html", required=True)
    ap.add_argument("--reference-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--reward-file", default="/logs/verifier/reward.txt")
    ap.add_argument("--render", action="store_true", help="Render agent HTML first")
    args = ap.parse_args()

    agent_html_dir = Path(args.agent_html)
    reference_dir = Path(args.reference_dir)
    output_dir = Path(args.output_dir)
    reward_file = Path(args.reward_file)

    output_dir.mkdir(parents=True, exist_ok=True)
    reward_file.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()

    # 1. Anti-cheat first — if violated, we still grade but apply the penalty
    ac = check_directory(agent_html_dir)
    (output_dir / "anticheat.json").write_text(
        json.dumps(
            {"penalty_multiplier": ac.penalty_multiplier, "violations": ac.violations},
            indent=2,
        )
    )

    # 2. Render agent's HTML if requested
    if args.render:
        render_meta = render_agent_output(agent_html_dir, output_dir / "rendered")
        (output_dir / "render_meta.json").write_text(json.dumps(render_meta, indent=2))
        candidate_dir = output_dir / "rendered"
    else:
        candidate_dir = agent_html_dir

    # 3. Score each reference page against the candidate's render
    per_page_scores: dict[str, dict] = {}
    missing_pages: list[str] = []
    for ref_png in sorted(reference_dir.glob("*.png")):
        stem = ref_png.stem  # e.g., "index.desktop"
        page_name = stem.split(".")[0]  # "index"
        candidate_png = candidate_dir / f"{page_name}.desktop.png"
        if not candidate_png.exists():
            missing_pages.append(page_name)
            per_page_scores[page_name] = {
                "ssim": {"name": "ssim", "score": 0.0, "extra": {"missing": True}}
            }
            continue
        per_page_scores[page_name] = grade_one_page(ref_png, candidate_png)

    # 4. Compose final reward
    reward = compose(per_page_scores, ac.penalty_multiplier)

    # 5. Write everything
    subscores = {
        "per_page": per_page_scores,
        "anticheat_multiplier": ac.penalty_multiplier,
        "anticheat_violations": len(ac.violations),
        "missing_pages": missing_pages,
        "reward": reward,
        "wall_clock_seconds": time.time() - started,
    }
    (output_dir / "subscores.json").write_text(json.dumps(subscores, indent=2))
    reward_file.write_text(f"{reward}\n")

    print(json.dumps(subscores, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
