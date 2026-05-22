"""
Scaffold a new design-replication task from a reference site.

Reads `<source-dir>/<name>/*.html`, creates `tasks/<name>/` by cloning
`pipeline/task_template/` (the canonical template), and rewrites
`instruction.md` with the actual page list discovered from the source HTMLs.

Usage:
  python pipeline/scaffold_task.py <name>
  python pipeline/scaffold_task.py 001-gov-services-v4
  python pipeline/scaffold_task.py 001-legal-practice-v7 --source-dir reference_sites_viewport
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import shutil
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "pipeline" / "task_template"

sys.path.insert(0, str(REPO_ROOT / "pipeline" / "grader"))
from viewports import VIEWPORTS


def _summarize_animations(screenshots_dir: Path, page_stems: list[str]) -> dict:
    """Extract a human-readable animation summary from the reference screenshots dir.

    Uses only the first viewport per page to avoid inflating counts (the same
    animations appear at every viewport).
    """
    vp_names = list(VIEWPORTS.keys())
    all_animations: list[dict] = []
    filmstrip_files: list[str] = []
    loaded_pages: set[str] = set()

    for stem in page_stems:
        for vp in vp_names:
            meta_path = screenshots_dir / f"{stem}.{vp}.animations.json"
            if meta_path.exists() and stem not in loaded_pages:
                loaded_pages.add(stem)
                all_animations.extend(json.loads(meta_path.read_text()))
            filmstrip = screenshots_dir / "filmstrips" / f"{stem}.{vp}.filmstrip.png"
            if filmstrip.exists():
                filmstrip_files.append(f"{stem}.{vp}.filmstrip.png")

    if not all_animations:
        return {}

    seen: dict[str, dict] = {}
    for a in all_animations:
        name = a.get("name", "unknown")
        iters = a.get("iterations", 1)
        kind = "looping" if iters == float("inf") or iters > 10 else "entrance"
        props = set()
        for kf in a.get("keyframes", []):
            for k in kf:
                if k not in ("offset", "easing", "composite", "computedOffset"):
                    props.add(k)
        key = f"{name}|{kind}"
        if key not in seen:
            seen[key] = {
                "name": name,
                "kind": kind,
                "duration_ms": a.get("duration", 0),
                "props": props,
                "count": 0,
            }
        seen[key]["count"] += 1
        seen[key]["props"] |= props

    return {
        "total_count": len(all_animations),
        "unique_animations": list(seen.values()),
        "filmstrip_files": filmstrip_files,
    }


def _build_animation_section(anim_summary: dict) -> str:
    """Build the animation section for instruction.md."""
    lines = [
        "",
        "---",
        "",
        "**Animations:** This design includes CSS animations. Your output will be graded "
        "on both static appearance AND animation fidelity. The `/reference/` directory "
        "includes filmstrip PNGs showing how animations progress over time — use these "
        "as visual reference.",
        "",
        "The following animations are used:",
        "",
    ]

    for a in anim_summary["unique_animations"]:
        props_str = ", ".join(sorted(a["props"]))
        count_note = f" (×{a['count']})" if a['count'] > 1 else ""
        kind_label = "looping/ambient" if a["kind"] == "looping" else "entrance"
        lines.append(
            f"- **`{a['name']}`** — {kind_label}, ~{int(a['duration_ms'])}ms, "
            f"animates: {props_str}{count_note}"
        )

    lines.extend([
        "",
        "Filmstrip references (in `/reference/filmstrips/`):",
        "",
    ])
    for f in anim_summary["filmstrip_files"]:
        lines.append(f"- `{f}`")

    lines.extend([
        "",
        "**Animation grading:** The grader captures your animations at 0%, 50%, and 100% "
        "progress and compares against reference keyframes. It also generates a filmstrip "
        "of your output and uses a VLM judge to compare it against the reference filmstrip. "
        "Animation name, count, timing, and animated CSS properties all contribute to the "
        "animation score.",
        "",
        "**Tips:**",
        "- Use `@keyframes` with matching animation names",
        "- Match durations and delays approximately",
        "- Use `animation-fill-mode: both` for entrance animations",
        "- Stagger entrance animations with increasing `animation-delay`",
        "",
    ])
    return "\n".join(lines)


def _instruction(page_stems: list[str], anim_summary: dict | None = None) -> str:
    template = (TEMPLATE / "instruction.md.template").read_text()
    n_pages = len(page_stems)
    vp_names = list(VIEWPORTS.keys())
    n_screenshots = n_pages * len(vp_names)
    page_listing = "\n".join(
        "  ".join(f"{p}.{vp}.png" for vp in vp_names) for p in page_stems
    )
    content = template.format(
        n_screenshots=n_screenshots,
        n_pages=n_pages,
        page_listing=page_listing,
        app_listing="\n".join(f"/app/{p}.html" for p in page_stems),
    )
    if anim_summary:
        content += _build_animation_section(anim_summary)
    return content


def _build_solve_sh(site_dir: Path, page_stems: list[str]) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        css_path = site_dir / "styles.css"
        if css_path.exists():
            tf.add(css_path, arcname="styles.css")
        for stem in page_stems:
            html_path = site_dir / f"{stem}.html"
            if html_path.exists():
                tf.add(html_path, arcname=f"{stem}.html")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    chunked = "\n".join(b64[i:i + 76] for i in range(0, len(b64), 76))
    return (
        "#!/bin/bash\n"
        "# Oracle solution: extracts the canonical reference site into /app/.\n"
        "set -euo pipefail\n\n"
        "base64 -d <<'B64' | tar xzf - -C /app/\n"
        f"{chunked}\n"
        "B64\n\n"
        'echo "wrote /app/ contents:"\n'
        "ls /app/\n"
    )


def scaffold(name: str, source_dir: Path | None = None, output_root: Path | None = None) -> Path:
    src = (source_dir or REPO_ROOT / "reference_sites") / name
    dst = (output_root or REPO_ROOT / "tasks") / name
    if not src.is_dir():
        raise SystemExit(f"missing reference site: {src}")
    htmls = sorted(p.stem for p in src.glob("*.html") if p.is_file())
    if not htmls:
        raise SystemExit(f"no .html files in {src}")

    if dst.exists():
        print(f"[scaffold] removing existing {dst}")
        shutil.rmtree(dst)

    shutil.copytree(TEMPLATE, dst)

    # Copy grader files from canonical locations into tests/
    pipeline = REPO_ROOT / "pipeline"
    for grader_file in ("grade.py", "metrics.py", "anticheat.py", "vlm_judge.py", "viewports.py", "animation_metrics.py"):
        shutil.copy2(pipeline / "grader" / grader_file, dst / "tests" / grader_file)
    shutil.copy2(pipeline / "render.py", dst / "tests" / "render.py")

    # Copy proxy.py into the agent environment
    shutil.copy2(pipeline / "proxy.py", dst / "environment" / "proxy.py")

    # Copy animation reference files if present
    screenshots_dir = src / "screenshots"
    anim_summary: dict | None = None
    if screenshots_dir.is_dir():
        anim_summary = _summarize_animations(screenshots_dir, htmls) or None
        if anim_summary:
            env_ref = dst / "environment" / "reference"
            ver_ref = dst / "tests" / "reference_truth"
            env_ref.mkdir(parents=True, exist_ok=True)
            ver_ref.mkdir(parents=True, exist_ok=True)

            for meta_file in screenshots_dir.glob("*.animations.json"):
                shutil.copy2(meta_file, ver_ref / meta_file.name)

            for kf_png in screenshots_dir.glob("*.anim_*pct.png"):
                shutil.copy2(kf_png, ver_ref / kf_png.name)

            filmstrips_src = screenshots_dir / "filmstrips"
            if filmstrips_src.is_dir():
                for target in (env_ref, ver_ref):
                    filmstrips_dst = target / "filmstrips"
                    filmstrips_dst.mkdir(parents=True, exist_ok=True)
                    for fp in filmstrips_src.glob("*.filmstrip.png"):
                        shutil.copy2(fp, filmstrips_dst / fp.name)

            n_anim_files = (
                len(list(screenshots_dir.glob("*.animations.json")))
                + len(list(screenshots_dir.glob("*.anim_*pct.png")))
                + (len(list(filmstrips_src.glob("*.filmstrip.png"))) if filmstrips_src.is_dir() else 0)
            )
            print(f"  animation files: {n_anim_files} copied to reference dirs")

    # Rewrite instruction.md
    (dst / "instruction.md").write_text(_instruction(htmls, anim_summary))

    # Write oracle solution
    solve_sh = dst / "solution" / "solve.sh"
    solve_sh.write_text(_build_solve_sh(src, htmls))
    solve_sh.chmod(0o755)

    # Patch task.toml placeholder
    toml = dst / "task.toml"
    toml.write_text(toml.read_text().replace("__TASK_NAME__", name))

    print(f"[scaffold] {name}: {len(htmls)} page(s) → {dst}")
    print(f"  pages: {', '.join(htmls)}")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--source-dir", type=Path, default=None,
                    help="Root dir containing <name>/. Default: reference_sites/")
    args = ap.parse_args()
    source_dir = args.source_dir.resolve() if args.source_dir else None
    scaffold(args.name, source_dir=source_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
