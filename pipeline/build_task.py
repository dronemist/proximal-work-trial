"""
Build script for design-replication tasks.

Canonical source HTMLs live OUTSIDE the task dir, at
`reference_sites/{task_dir.name}/`. Keeping them out of the task dir means
Harbor's task-upload paths (environment/, tests/, solution/, steps/) cannot
possibly ship them into either container — neither the agent nor the verifier
ever sees the source HTMLs.

A task dir has this shape:

  reference_sites/{task}/        ← canonical HTML+CSS  (NOT inside task dir)
    *.html, *.css
  tasks/{task}/
    environment/reference/       ← agent-visible screenshots (built here)
    tests/reference_truth/       ← verifier-visible PNGs + dom.json sidecars (built here)
    tests/build_manifest.json    ← built; records source HTML SHA256s + chromium version

This script reads the source dir, renders everything on Modal exactly once with
a single Chromium version, and writes the derived artifacts to the two target
directories so agent and verifier have matched references.

Idempotent: if the existing manifest's source hashes match current source/,
the build is skipped (use `--force` to rebuild anyway).

Usage:
  python pipeline/build_task.py tasks/002-lumen-multipage
  python pipeline/build_task.py tasks/002-lumen-multipage --force
  python pipeline/build_task.py tasks/002-lumen-multipage --check   # exit 1 if stale
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

VIEWPORTS = {
    "desktop": (1440, 900),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_source(source_dir: Path) -> dict[str, str]:
    """Hash every file in _source/ (relative-path keys, sorted)."""
    out: dict[str, str] = {}
    for p in sorted(source_dir.rglob("*")):
        if not p.is_file():
            continue
        out[p.relative_to(source_dir).as_posix()] = _sha256(p)
    return out


def _source_dir_for(task_dir: Path) -> Path:
    """Canonical source HTMLs live OUTSIDE the task dir at
    `repo_root/reference_sites/{task_name}/`. Keeping them out of `tasks/`
    means Harbor's task uploads cannot ship them into any container.
    """
    return REPO_ROOT / "reference_sites" / task_dir.name


def _is_stale(task_dir: Path) -> tuple[bool, dict | None, dict[str, str]]:
    """Return (stale?, existing_manifest_or_None, current_source_hashes)."""
    manifest_path = task_dir / "tests" / "build_manifest.json"
    current = _hash_source(_source_dir_for(task_dir))
    if not manifest_path.exists():
        return True, None, current
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception:
        return True, None, current
    return manifest.get("source_hashes") != current, manifest, current


def build(task_dir: Path) -> dict:
    """Render references on Modal and write all derived artifacts.

    Returns the manifest dict that was written.
    """
    source_dir = _source_dir_for(task_dir)
    env_ref = task_dir / "environment" / "reference"
    ver_ref = task_dir / "tests" / "reference_truth"
    manifest_path = task_dir / "tests" / "build_manifest.json"

    if not source_dir.is_dir():
        raise SystemExit(
            f"missing source dir {source_dir} (canonical HTMLs should live "
            f"in reference_sites/{task_dir.name}/)"
        )
    htmls = sorted(p for p in source_dir.glob("*.html") if p.is_file())
    if not htmls:
        raise SystemExit(f"no .html files in {source_dir}")

    env_ref.mkdir(parents=True, exist_ok=True)
    ver_ref.mkdir(parents=True, exist_ok=True)
    # Clean stale artifacts so a removed page doesn't linger.
    for d in (env_ref, ver_ref):
        for old in list(d.iterdir()):
            if old.is_file():
                old.unlink()

    # Collect files to upload to the Modal container, preserving relative paths
    # (so relative <link rel="stylesheet"> resolves on the remote side).
    files: dict[str, bytes] = {}
    for p in sorted(source_dir.rglob("*")):
        if p.is_file():
            files[p.relative_to(source_dir).as_posix()] = p.read_bytes()

    # Build the render list: every HTML × every viewport.
    renders = []
    for h in htmls:
        stem = h.stem
        for vp_name, (w, ht) in VIEWPORTS.items():
            renders.append(
                {"html": h.name, "output": f"{stem}.{vp_name}.png", "viewport": f"{w}x{ht}"}
            )

    print(f"[build_task] uploading {len(files)} source file(s); requesting {len(renders)} render(s)")
    # Lazy import so --check mode runs without Modal installed.
    from render_on_modal import app, render_batch  # type: ignore

    with app.run():
        results = render_batch.remote(files, renders)

    sep = b"\n---META---\n"
    chromium_version = ""
    for name, payload in results.items():
        png_bytes, meta_bytes = payload.split(sep, 1)
        meta = json.loads(meta_bytes.decode())
        chromium_version = meta.get("chromium_version") or chromium_version
        # Write to BOTH the agent-visible env/reference dir and the verifier-
        # visible tests/reference_truth dir. Same bytes, same DOM sidecar.
        dom_payload = json.dumps({"elements": _extract_dom_from_meta(meta)})
        for target in (env_ref, ver_ref):
            (target / name).write_bytes(png_bytes)
        # DOM sidecar only the verifier needs (agent never reads DOM).
        (ver_ref / (Path(name).stem + ".dom.json")).write_text(dom_payload)
        print(f"  wrote {name}  ({len(png_bytes):,} bytes)")

    manifest = {
        "source_hashes": _hash_source(source_dir),
        "chromium_version": chromium_version,
        "viewports": {k: list(v) for k, v in VIEWPORTS.items()},
        "pages": [h.stem for h in htmls],
        "built_at": datetime.now(timezone.utc).isoformat(),
        "outputs": {
            "agent_reference": [f"{h.stem}.{vp}.png" for h in htmls for vp in VIEWPORTS],
            "verifier_reference_truth": [
                f"{h.stem}.{vp}.{ext}" for h in htmls for vp in VIEWPORTS for ext in ("png", "dom.json")
            ],
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"[build_task] wrote manifest → {manifest_path}")
    return manifest


def _extract_dom_from_meta(meta: dict) -> list[dict]:
    """The current render_on_modal._render_one writes the dom.json itself, so
    its returned meta doesn't carry the dom array. We re-extract by reading
    the meta's `elements` field if present, else return []."""
    return meta.get("elements") or []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir", help="path to tasks/<name>")
    ap.add_argument("--force", action="store_true", help="rebuild even if not stale")
    ap.add_argument("--check", action="store_true", help="exit 1 if manifest is stale or missing")
    args = ap.parse_args()

    task_dir = Path(args.task_dir).resolve()
    stale, manifest, current_hashes = _is_stale(task_dir)

    if args.check:
        if stale:
            print("STALE: _source/ hashes do not match tests/build_manifest.json")
            if manifest is None:
                print("  (no manifest exists)")
            else:
                old = set(manifest.get("source_hashes", {}).items())
                new = set(current_hashes.items())
                print(f"  changed files: {sorted(k for k, _ in (old ^ new))}")
            return 1
        print("OK: manifest matches _source/")
        return 0

    if not stale and not args.force:
        print(f"[build_task] manifest up to date; skipping (use --force to rebuild)")
        return 0

    build(task_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
