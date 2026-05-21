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
import shutil
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "pipeline" / "task_template"

sys.path.insert(0, str(REPO_ROOT / "pipeline" / "grader"))
from viewports import VIEWPORTS


def _instruction(page_stems: list[str]) -> str:
    template = (TEMPLATE / "instruction.md.template").read_text()
    n_pages = len(page_stems)
    vp_names = list(VIEWPORTS.keys())
    n_screenshots = n_pages * len(vp_names)
    page_listing = "\n".join(
        "  ".join(f"{p}.{vp}.png" for vp in vp_names) for p in page_stems
    )
    return template.format(
        n_screenshots=n_screenshots,
        n_pages=n_pages,
        page_listing=page_listing,
        app_listing="\n".join(f"/app/{p}.html" for p in page_stems),
    )


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


def scaffold(name: str, source_dir: Path | None = None) -> Path:
    src = (source_dir or REPO_ROOT / "reference_sites") / name
    dst = REPO_ROOT / "tasks" / name
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
    for grader_file in ("grade.py", "metrics.py", "anticheat.py", "vlm_judge.py", "viewports.py"):
        shutil.copy2(pipeline / "grader" / grader_file, dst / "tests" / grader_file)
    shutil.copy2(pipeline / "render.py", dst / "tests" / "render.py")

    # Copy proxy.py into the agent environment
    shutil.copy2(pipeline / "proxy.py", dst / "environment" / "proxy.py")

    # Rewrite instruction.md
    (dst / "instruction.md").write_text(_instruction(htmls))

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
