#!/usr/bin/env python3
"""
Render an HTML file (or local URL) to a PNG via Playwright + Chromium.

Used both:
  - Locally (inside Docker), to produce the reference PNG that the agent sees.
  - Inside the verifier container, to render the agent's output.

Same code path → same Chromium version → reproducible.

Usage:
  render.py <html_path_or_url> <output_png> [--viewport WIDTHxHEIGHT]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def _is_off_origin(request_url: str, source_url: str) -> bool:
    """Return True if request_url targets a different origin than source_url.

    For local file:// renders, ANY http(s) request is off-origin — the agent
    must not pull from CDNs, fonts.googleapis, hotlinked images, etc.
    """
    src = urlparse(source_url)
    req = urlparse(request_url)
    if src.scheme == "file":
        return req.scheme in {"http", "https"}
    return (req.scheme, req.netloc) != (src.scheme, src.netloc)


def render(
    source: str,
    output_png: Path,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    full_page: bool = True,
    settle_ms: int = 500,
    fail_on_off_origin: bool = True,
) -> dict:
    """Render the page and return metadata about what was rendered.

    Raises RuntimeError if `fail_on_off_origin=True` and any off-origin
    network request happens during render.
    """
    if "://" not in source:
        source_url = Path(source).absolute().as_uri()
    else:
        source_url = source

    console_messages: list[dict] = []
    network_requests: list[dict] = []
    off_origin: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=1,
        )
        page = context.new_page()

        page.on(
            "console",
            lambda msg: console_messages.append(
                {"type": msg.type, "text": msg.text, "location": msg.location}
            ),
        )

        def on_request(req):
            entry = {
                "method": req.method,
                "url": req.url,
                "resource_type": req.resource_type,
            }
            network_requests.append(entry)
            if _is_off_origin(req.url, source_url):
                off_origin.append(entry)

        page.on("request", on_request)

        # `load` rather than `networkidle`: networkidle waits up to 30s for
        # quiet network, which deadlocks the verifier when the agent links to
        # an unreachable CDN. We capture all requests via the event handler;
        # we don't need to wait for them.
        page.goto(source_url, wait_until="load")

        try:
            page.evaluate("document.fonts && document.fonts.ready")
        except Exception:
            pass
        page.wait_for_timeout(settle_ms)

        output_png.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output_png), full_page=full_page, type="png")

        browser_version = browser.version
        browser.close()

    meta = {
        "source": source_url,
        "output": str(output_png),
        "viewport": {"width": viewport_width, "height": viewport_height},
        "full_page": full_page,
        "chromium_version": browser_version,
        "console": console_messages,
        "network": network_requests,
        "off_origin_requests": off_origin,
    }

    if fail_on_off_origin and off_origin:
        # Don't raise — return the failure in the metadata so the caller can
        # decide. Anti-cheat / grader uses this signal to penalize external
        # resource use without hard-failing the render pipeline.
        meta["off_origin_violation"] = True
    return meta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Path or URL to render")
    parser.add_argument("output", help="Output PNG path")
    parser.add_argument("--viewport", default="1440x900", help="WIDTHxHEIGHT, default 1440x900")
    parser.add_argument("--no-full-page", action="store_true", help="Capture viewport only, not full page")
    parser.add_argument("--meta", help="Write a JSON metadata sidecar to this path")
    parser.add_argument("--allow-off-origin", action="store_true", help="Don't flag external requests")
    args = parser.parse_args()

    try:
        w, h = (int(x) for x in args.viewport.lower().split("x"))
    except Exception:
        print(f"bad viewport: {args.viewport}", file=sys.stderr)
        return 2

    meta = render(
        source=args.source,
        output_png=Path(args.output),
        viewport_width=w,
        viewport_height=h,
        full_page=not args.no_full_page,
        fail_on_off_origin=not args.allow_off_origin,
    )

    if args.meta:
        Path(args.meta).write_text(json.dumps(meta, indent=2))

    print(f"rendered {meta['source']} → {meta['output']}  (chromium {meta['chromium_version']})")
    if meta["console"]:
        print(f"  {len(meta['console'])} console message(s):")
        for m in meta["console"][:5]:
            print(f"    [{m['type']}] {m['text']}")
    if meta.get("off_origin_requests"):
        print(f"  WARNING: {len(meta['off_origin_requests'])} off-origin request(s)")
        for r in meta["off_origin_requests"][:5]:
            print(f"    {r['method']} {r['resource_type']} {r['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
