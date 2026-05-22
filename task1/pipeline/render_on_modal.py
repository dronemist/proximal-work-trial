"""
Render reference HTML(s) to PNG(s) on Modal — same OS/Chromium/fonts as the
verifier, eliminating macOS↔Linux render drift.

Supports two modes:

1. **Single-file mode** (Phase 1, back-compat):
   modal run pipeline/render_on_modal.py \\
     --html reference_sites/001-landing/index.html \\
     --output reference_sites/001-landing/screenshots/index.desktop.png \\
     --viewport 1440x900

2. **Batch mode** (Phase 2+): render N HTMLs at M viewports in one Modal call.
   modal run pipeline/render_on_modal.py::batch \\
     --site-dir reference_sites/002-lumen-multipage \\
     --output-dir reference_sites/002-lumen-multipage/screenshots
   Each .html in site-dir gets rendered at every viewport in DEFAULT_VIEWPORTS,
   alongside any non-HTML assets (e.g. styles.css) which are uploaded as-is.
"""
from __future__ import annotations

import sys
from pathlib import Path

import modal

REPO_ROOT = Path(__file__).resolve().parent.parent

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("ca-certificates", "curl")
    .pip_install("playwright==1.49.0", "pillow==11.0.0", "numpy==2.1.3")
    .run_commands(
        "playwright install --with-deps chromium",
        "fc-cache -f -v > /dev/null 2>&1 || true",
    )
)

app = modal.App("worktrial-reference-renderer", image=image)


@app.function(timeout=900)
def render_html(html_bytes: bytes, viewport: str = "1440x900") -> bytes:
    """Single-HTML render. Returns png_bytes + meta JSON separated by sentinel."""
    import json
    import subprocess

    Path("/work").mkdir(exist_ok=True)
    Path("/work/input.html").write_bytes(html_bytes)

    w, h = (int(x) for x in viewport.lower().split("x"))
    png_path, meta_path = Path("/work/output.png"), Path("/work/output.meta.json")
    _render_one(
        source_path="/work/input.html",
        output_png=png_path,
        viewport_w=w,
        viewport_h=h,
        meta_path=meta_path,
    )
    return png_path.read_bytes() + b"\n---META---\n" + meta_path.read_bytes()


@app.function(timeout=1800)
def render_batch(
    files: dict[str, bytes],
    renders: list[dict],
) -> dict[str, bytes]:
    """Batch render: upload `files` to /work/, then render every (html, viewport).

    `renders` is a list of dicts like:
      {"html": "index.html", "output": "index.desktop.png", "viewport": "1440x900"}

    Returns: {output_filename: png_bytes_with_meta}
    """
    from playwright.sync_api import sync_playwright

    workdir = Path("/work")
    workdir.mkdir(exist_ok=True)
    for name, content in files.items():
        path = workdir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    results: dict[str, bytes] = {}
    chromium_version = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        chromium_version = browser.version
        try:
            for r in renders:
                source = workdir / r["html"]
                if not source.exists():
                    raise FileNotFoundError(f"missing source HTML: {source}")
                w, h = (int(x) for x in r["viewport"].lower().split("x"))
                out_png = workdir / r["output"]
                meta = _render_one(
                    source_path=str(source),
                    output_png=out_png,
                    viewport_w=w,
                    viewport_h=h,
                    browser=browser,
                )
                meta["chromium_version"] = chromium_version
                import json as _json

                results[r["output"]] = (
                    out_png.read_bytes()
                    + b"\n---META---\n"
                    + _json.dumps(meta).encode()
                )
                print(f"  rendered {r['html']} @ {r['viewport']} → {r['output']}")
        finally:
            browser.close()

    print(f"batch rendered {len(results)} PNG(s) with chromium {chromium_version}")
    return results


_DOM_DUMP_JS = r"""
() => {
  const out = [];
  const all = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    const s = window.getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || parseFloat(s.opacity) === 0) continue;
    out.push({
      tag: el.tagName.toLowerCase(),
      color: s.color,
      background_color: s.backgroundColor,
      font_family: s.fontFamily,
      font_size_px: parseFloat(s.fontSize) || 0,
      font_weight: s.fontWeight,
      bbox: { x: r.x, y: r.y, w: r.width, h: r.height },
    });
  }
  return {
    elements: out,
    text: document.body ? document.body.innerText : "",
    page: {
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
    },
  };
}
"""


def _is_off_origin(request_url: str, source_url: str) -> bool:
    """Return True if request_url targets a different origin than source_url.

    Mirrors pipeline/render.py:_is_off_origin — kept in sync so the anticheat
    policy is identical regardless of which renderer runs.
    """
    from urllib.parse import urlparse

    src = urlparse(source_url)
    req = urlparse(request_url)
    if src.scheme == "file":
        return req.scheme in {"http", "https"}
    return (req.scheme, req.netloc) != (src.scheme, src.netloc)


def _render_one(
    source_path: str,
    output_png: Path,
    viewport_w: int,
    viewport_h: int,
    browser=None,
    meta_path: Path | None = None,
    settle_ms: int = 500,
) -> dict:
    """Render a single page. Caller may supply a reusable browser for batches."""
    from playwright.sync_api import sync_playwright

    source_url = (
        f"file://{source_path}"
        if not source_path.startswith("file:")
        else source_path
    )

    output_png.parent.mkdir(parents=True, exist_ok=True)
    console: list = []
    requests_log: list = []
    off_origin: list = []
    dom_payload_out: list = []  # _do_render appends the dom payload dict here

    def _do_render(b):
        nonlocal console, requests_log, off_origin
        ctx = b.new_context(viewport={"width": viewport_w, "height": viewport_h}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: console.append({"type": m.type, "text": m.text}))

        def on_request(req):
            entry = {"method": req.method, "url": req.url, "resource_type": req.resource_type}
            requests_log.append(entry)
            if _is_off_origin(req.url, source_url):
                off_origin.append(entry)

        page.on("request", on_request)
        page.goto(source_url, wait_until="load")
        try:
            page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
        except Exception:
            pass
        page.wait_for_timeout(settle_ms)
        page.screenshot(path=str(output_png), full_page=True, type="png")
        try:
            dom_payload = page.evaluate(_DOM_DUMP_JS)
        except Exception as e:
            dom_payload = {"elements": [], "page": {}}
            console.append({"type": "dom_dump_error", "text": str(e)})
        dom_payload_out.append(dom_payload)
        ctx.close()

    if browser is not None:
        _do_render(browser)
    else:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            _do_render(b)
            b.close()

    meta = {
        "source": source_url,
        "output": str(output_png),
        "viewport": {"width": viewport_w, "height": viewport_h},
        "full_page": True,
        "console": console,
        "network": requests_log,
        "off_origin_requests": off_origin,
        "elements": (dom_payload_out[0].get("elements") if dom_payload_out else []) or [],
        "text": (dom_payload_out[0].get("text") if dom_payload_out else "") or "",
        "page": (dom_payload_out[0].get("page") if dom_payload_out else {}) or {},
    }
    if meta_path is not None:
        import json as _json

        meta_path.write_text(_json.dumps(meta, indent=2))
    return meta


@app.local_entrypoint()
def main(
    html: str,
    output: str,
    viewport: str = "1440x900",
):
    """Phase 1 back-compat: render a single HTML."""
    html_path = Path(html).resolve()
    output_path = Path(output).resolve()
    if not html_path.exists():
        raise SystemExit(f"html not found: {html_path}")

    print(f"sending {html_path.stat().st_size} bytes of HTML to Modal...")
    payload = render_html.remote(html_path.read_bytes(), viewport)
    sep = b"\n---META---\n"
    png, meta = payload.split(sep, 1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png)
    output_path.with_suffix(".meta.json").write_bytes(meta)
    print(f"wrote {len(png)} bytes → {output_path}")


@app.local_entrypoint()
def batch(site_dir: str, output_dir: str):
    """Render every .html under site_dir at every default viewport, writing
    {page}.{viewport-name}.png into output_dir.

    Any non-HTML file in site_dir (e.g. styles.css, images) is uploaded as-is
    so relative references inside the HTMLs resolve.
    """
    sys.path.insert(0, str(REPO_ROOT / "pipeline" / "grader"))
    from viewports import VIEWPORTS as DEFAULT_VIEWPORTS

    site = Path(site_dir).resolve()
    out = Path(output_dir).resolve()
    if not site.is_dir():
        raise SystemExit(f"site_dir not found: {site}")
    out.mkdir(parents=True, exist_ok=True)

    # Collect every regular file under site_dir, preserving relative paths.
    files: dict[str, bytes] = {}
    htmls: list[str] = []
    for p in sorted(site.rglob("*")):
        if p.is_dir():
            continue
        # skip the screenshots dir itself if it sits under site_dir
        rel = p.relative_to(site).as_posix()
        if rel.startswith("screenshots/"):
            continue
        files[rel] = p.read_bytes()
        if p.suffix.lower() in {".html", ".htm"}:
            htmls.append(rel)
    if not htmls:
        raise SystemExit(f"no HTML files under {site}")

    renders = []
    for h in htmls:
        stem = Path(h).stem
        for vp_name, (w, vph) in DEFAULT_VIEWPORTS.items():
            renders.append(
                {"html": h, "output": f"{stem}.{vp_name}.png", "viewport": f"{w}x{vph}"}
            )
    print(f"sending {len(files)} file(s); requesting {len(renders)} render(s)")
    results = render_batch.remote(files, renders)

    sep = b"\n---META---\n"
    for name, payload in results.items():
        png, meta = payload.split(sep, 1)
        (out / name).write_bytes(png)
        (out / (Path(name).stem + ".meta.json")).write_bytes(meta)
        print(f"  wrote {len(png):8d} bytes → {out / name}")

    print(f"done. {len(results)} PNGs in {out}")
