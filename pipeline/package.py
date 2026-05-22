"""
Scaffold + render Harbor tasks in a single Modal session.

Combines scaffold_task.py (local scaffolding) and build_task.py (Modal PNG
rendering) into one command. Processes multiple sites with one Modal app
startup.

Usage:
  python pipeline/package.py reference_sites_viewport/*-v7
  python pipeline/package.py --source-dir reference_sites_viewport --suffix v7
  python pipeline/package.py reference_sites/001-gov-services-v4 --force
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "pipeline" / "grader"))

from viewports import VIEWPORTS
from scaffold_task import scaffold


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_source(source_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(source_dir.rglob("*")):
        if not p.is_file():
            continue
        out[p.relative_to(source_dir).as_posix()] = _sha256(p)
    return out


def resolve_sites(
    paths: list[str],
    source_dir: Path | None,
    suffix: str | None,
) -> list[Path]:
    if paths:
        dirs = [Path(p).resolve() for p in paths]
        for d in dirs:
            if not d.is_dir():
                raise SystemExit(f"not a directory: {d}")
        return sorted(dirs)

    if source_dir is None:
        raise SystemExit("provide site paths or --source-dir")

    source_dir = source_dir.resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"not a directory: {source_dir}")

    dirs = sorted(
        d for d in source_dir.iterdir()
        if d.is_dir() and (suffix is None or d.name.endswith(suffix))
    )
    if not dirs:
        raise SystemExit(f"no matching sites in {source_dir}" +
                         (f" with suffix {suffix!r}" if suffix else ""))
    return dirs


def prepare_render_inputs(source_dir: Path) -> tuple[dict[str, bytes], list[dict]]:
    files: dict[str, bytes] = {}
    htmls: list[Path] = []
    for p in sorted(source_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(source_dir).as_posix()
        if rel.startswith("screenshots/") or rel.startswith("_"):
            continue
        files[rel] = p.read_bytes()
        if p.suffix.lower() in {".html", ".htm"}:
            htmls.append(p)

    renders = []
    for h in htmls:
        for vp_name, (w, ht) in VIEWPORTS.items():
            renders.append({
                "html": h.name,
                "output": f"{h.stem}.{vp_name}.png",
                "viewport": f"{w}x{ht}",
            })
    return files, renders


def write_render_results(
    task_dir: Path,
    source_dir: Path,
    results: dict[str, bytes],
) -> dict:
    env_ref = task_dir / "environment" / "reference"
    ver_ref = task_dir / "tests" / "reference_truth"
    env_ref.mkdir(parents=True, exist_ok=True)
    ver_ref.mkdir(parents=True, exist_ok=True)

    for d in (env_ref, ver_ref):
        for old in list(d.iterdir()):
            if old.is_file():
                old.unlink()

    sep = b"\n---META---\n"
    chromium_version = ""

    for name, payload in results.items():
        png_bytes, meta_bytes = payload.split(sep, 1)
        meta = json.loads(meta_bytes.decode())
        chromium_version = meta.get("chromium_version") or chromium_version

        dom_payload = json.dumps({
            "elements": meta.get("elements") or [],
            "text": meta.get("text") or "",
            "page": meta.get("page") or {},
        })

        for target in (env_ref, ver_ref):
            (target / name).write_bytes(png_bytes)
        (ver_ref / (Path(name).stem + ".dom.json")).write_text(dom_payload)
        print(f"    {name}  ({len(png_bytes):,} bytes)")

    htmls = sorted(p for p in source_dir.glob("*.html") if p.is_file())
    manifest = {
        "source_hashes": _hash_source(source_dir),
        "chromium_version": chromium_version,
        "viewports": {k: list(v) for k, v in VIEWPORTS.items()},
        "pages": [h.stem for h in htmls],
        "built_at": datetime.now(timezone.utc).isoformat(),
        "outputs": {
            "agent_reference": [
                f"{h.stem}.{vp}.png" for h in htmls for vp in VIEWPORTS
            ],
            "verifier_reference_truth": [
                f"{h.stem}.{vp}.{ext}"
                for h in htmls for vp in VIEWPORTS for ext in ("png", "dom.json")
            ],
        },
    }
    manifest_path = task_dir / "tests" / "build_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest


def package_sites(
    site_dirs: list[Path],
    output_root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    print(f"[package] {len(site_dirs)} site(s) to process")

    # Phase 1: scaffold all sites and prepare render inputs
    work_items: list[tuple[Path, Path, dict[str, bytes], list[dict]]] = []
    for site_dir in site_dirs:
        name = site_dir.name
        task_dir = output_root / name
        print(f"\n[scaffold] {name}")

        if dry_run:
            htmls = sorted(p.stem for p in site_dir.glob("*.html") if p.is_file())
            n_renders = len(htmls) * len(VIEWPORTS)
            print(f"  {len(htmls)} pages, {n_renders} renders -> {task_dir}")
            continue

        scaffold(name, source_dir=site_dir.parent)
        files, renders = prepare_render_inputs(site_dir)
        if not renders:
            print(f"  no HTML files in {site_dir}, skipping render")
            continue
        work_items.append((site_dir, task_dir, files, renders))

    if dry_run or not work_items:
        return []

    # Phase 2: single Modal session for all renders
    from render_on_modal import app, render_batch

    built: list[Path] = []
    total_renders = sum(len(r) for _, _, _, r in work_items)
    print(f"\n[render] {total_renders} total screenshots across {len(work_items)} site(s)")

    with app.run():
        for site_dir, task_dir, files, renders in work_items:
            print(f"\n[render] {task_dir.name}: {len(files)} file(s), {len(renders)} screenshot(s)")
            try:
                results = render_batch.remote(files, renders)
                write_render_results(task_dir, site_dir, results)
                built.append(task_dir)
                print(f"[render] {task_dir.name}: done")
            except Exception as e:
                print(f"[render] {task_dir.name}: FAILED — {e}")

    print(f"\n[package] {len(built)}/{len(work_items)} site(s) fully packaged")
    return built


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Scaffold + render Harbor tasks in a single Modal session.",
    )
    ap.add_argument(
        "sites", nargs="*",
        help="Path(s) to site source directories (supports shell glob)",
    )
    ap.add_argument(
        "--source-dir", type=Path, default=None,
        help="Scan this directory for site subdirectories",
    )
    ap.add_argument(
        "--suffix", default=None,
        help="Only include sites whose name ends with this suffix",
    )
    ap.add_argument(
        "--output-root", type=Path, default=None,
        help="Output root for task dirs (default: tasks/)",
    )
    ap.add_argument("--force", action="store_true", help="Rebuild even if not stale")
    ap.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    args = ap.parse_args()

    site_dirs = resolve_sites(args.sites, args.source_dir, args.suffix)
    output_root = (args.output_root or REPO_ROOT / "tasks").resolve()

    print(f"[package] output root: {output_root}")
    for d in site_dirs:
        print(f"  {d.name}")

    built = package_sites(site_dirs, output_root, force=args.force, dry_run=args.dry_run)
    return 0 if built or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
