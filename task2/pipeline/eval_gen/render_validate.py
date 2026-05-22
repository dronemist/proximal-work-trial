"""Stage 5 — Playwright render + structural validation.

Reuses pipeline/render.py for the actual screenshot capture so the eval-set
references are produced by the SAME render path the grader will use to
render the agent's submission. That's our determinism contract.

For the smoke wave we render locally (not on Modal). The Modal-based render
(pipeline/render_on_modal.py) is the production path; switching is a
one-import change.

Validation rules (smoke):
- Render must succeed (no Playwright exception).
- No <script> tags with non-empty content (no-JS constraint).
- No @keyframes / animation: properties (static-only constraint).
- No off-origin requests during render (catches Google Fonts misconfig).
- DOM depth >= 4 and tag count >= 15 (WebSight-floor).
- Heuristic: no lorem ipsum unless brief explicitly asked for it.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.eval_gen.config import REPO_ROOT, DEFAULT


# Load the shipped render.py without forcing a package layout.
_render_path = REPO_ROOT / "pipeline" / "render.py"
_spec = importlib.util.spec_from_file_location("render_mod", _render_path)
_render_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_render_mod)


@dataclass
class ValidationResult:
    ok: bool
    site_id: str
    page_slug: str
    issues: list[str] = field(default_factory=list)
    screenshots: dict[str, Path] = field(default_factory=dict)   # viewport -> path
    render_meta: dict = field(default_factory=dict)              # viewport -> meta


_SCRIPT_TAG = re.compile(r"<script\b[^>]*>(.+?)</script>", re.IGNORECASE | re.DOTALL)
_KEYFRAMES = re.compile(r"@keyframes\b|\banimation\s*:", re.IGNORECASE)
_LOREM = re.compile(r"\blorem\s+ipsum\b", re.IGNORECASE)
_EXTERNAL_FONT_LINK = re.compile(
    r"""<link[^>]+href\s*=\s*["'](https?:)?//(fonts\.googleapis\.com|fonts\.gstatic\.com|use\.typekit\.net|fonts\.bunny\.net)""",
    re.IGNORECASE,
)
_EXTERNAL_URL_IN_CSS = re.compile(
    r"""@import\s+(?:url\()?["']?https?://|url\(\s*["']?https?://""",
    re.IGNORECASE,
)
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.IGNORECASE)


def _normalize_hex(h: str) -> str:
    """Normalize hex colors to canonical 6-char lowercase form for set comparison.
    #abc -> #aabbcc; #aaBBcc -> #aabbcc; #aabbccdd -> #aabbcc (alpha dropped).
    """
    s = h.lower().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    elif len(s) == 8:
        s = s[:6]
    return f"#{s}"


def _check_brand_discipline(html: str, spec, issues: list[str]) -> None:
    """Inspect inline <style> blocks for off-brand hex colors and font-family
    declarations. Catches the case where the agent bypasses the design system
    (styles.css) and hardcodes colors / fonts per page.

    `spec` is the BrandSpec for this site, with .palette and .typography.
    """
    if spec is None:
        return

    brand_hexes = set()
    for mode in ("light", "dark"):
        for v in (spec.palette.get(mode) or {}).values():
            if isinstance(v, str) and v.startswith("#"):
                brand_hexes.add(_normalize_hex(v))
    brand_font_stacks = {
        spec.typography["heading"]["stack"].strip().lower(),
        spec.typography["body"]["stack"].strip().lower(),
        spec.typography["mono"]["stack"].strip().lower(),
    }

    inline_css = "\n".join(_STYLE_BLOCK.findall(html))
    if not inline_css.strip():
        return

    found_hexes = {_normalize_hex(m.group(0)) for m in _HEX_COLOR.finditer(inline_css)}
    off_brand_hexes = found_hexes - brand_hexes
    # Allow a small slop budget — pages legitimately introduce 0-2 status
    # colors (e.g., subtle backgrounds). > 5 means the page bypassed the
    # design system.
    OFF_BRAND_COLOR_BUDGET = 5
    if len(off_brand_hexes) > OFF_BRAND_COLOR_BUDGET:
        sample = sorted(off_brand_hexes)[:8]
        issues.append(
            f"page declared {len(off_brand_hexes)} off-brand hex colors in inline <style> (e.g., {sample}); "
            f"use CSS variables from styles.css (var(--color-accent), etc.) instead of raw hex"
        )

    found_families = set()
    for m in _FONT_FAMILY.finditer(inline_css):
        # Strip whitespace / quotes; lowercase for matching.
        fam = m.group(1).strip().rstrip(";").lower()
        # Skip var(...) — that's a token reference, not a raw font.
        if fam.startswith("var("):
            continue
        found_families.add(fam)
    off_brand_fonts = {f for f in found_families if f not in brand_font_stacks}
    if off_brand_fonts:
        issues.append(
            f"page declared off-brand font-family in inline <style>: {sorted(off_brand_fonts)[:3]}; "
            f"use the system stacks already defined in styles.css (no per-page font-family overrides)"
        )


def static_html_checks(
    html: str, issues: list[str], css: str = "", spec=None, animated: bool = False,
) -> None:
    """Scan generated HTML (and optionally the shared CSS) for forbidden constructs.

    `css` may be the contents of styles.css; passing it scans for things that
    won't appear in the HTML (e.g., `@keyframes` inside the shared stylesheet).
    `spec` enables brand-discipline checks (off-brand hex colors, off-brand
    font-family declarations) against the site's palette + typography.
    `animated` when True skips the @keyframes rejection (Part 2 tasks).
    """
    for m in _SCRIPT_TAG.finditer(html):
        body = m.group(1).strip()
        if body:
            issues.append(f"non-empty <script> tag found ({len(body)} chars)")
            break
    if not animated:
        if _KEYFRAMES.search(html):
            issues.append("animation/@keyframes detected in HTML (static-pages constraint)")
        if css and _KEYFRAMES.search(css):
            issues.append("animation/@keyframes detected in styles.css (static-pages constraint)")
    else:
        if not _KEYFRAMES.search(css) and not _KEYFRAMES.search(html):
            issues.append("animated task but no @keyframes found in HTML or styles.css")
    if _LOREM.search(html):
        issues.append("lorem ipsum leakage")
    if _EXTERNAL_FONT_LINK.search(html):
        issues.append("external font <link> found (system-fonts-only constraint)")
    combined = html + "\n" + css
    if _EXTERNAL_URL_IN_CSS.search(combined):
        issues.append("external URL in CSS @import or url() (offline constraint)")
    _check_brand_discipline(html, spec, issues)


# ---------------------------------------------------------------------------
# Library-level validation (Stage 3)
# ---------------------------------------------------------------------------

# Kitchen-sink HTML exercising the primitives every site library is supposed
# to ship: container, header/nav, grid, card, button, form input, table.
# If the library has a min-width/fixed-width on any of these (or on body/html),
# rendering this at 375px will overflow and the check fires before we burn 25
# page-attempts on a bad library.
_LIBRARY_SMOKE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>library smoke</title>
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header class="site-header">
  <nav class="nav"><a href="#">Home</a><a href="#">Docs</a><a href="#">Pricing</a></nav>
</header>
<main class="container">
  <h1>Heading</h1>
  <p>A paragraph of body copy to exercise typography and line-height tokens.</p>
  <section class="grid grid-3">
    <article class="card"><div class="card__body"><h3>Card</h3><p>Lorem dolor sit.</p></div></article>
    <article class="card"><div class="card__body"><h3>Card</h3><p>Lorem dolor sit.</p></div></article>
    <article class="card"><div class="card__body"><h3>Card</h3><p>Lorem dolor sit.</p></div></article>
  </section>
  <form class="stack">
    <label>Name<input type="text" placeholder="Jane"></label>
    <label>Email<input type="email" placeholder="jane@example.com"></label>
    <button class="btn btn--primary" type="button">Submit</button>
  </form>
  <table>
    <thead><tr><th>Col A</th><th>Col B</th><th>Col C</th><th>Col D</th></tr></thead>
    <tbody>
      <tr><td>row 1a</td><td>row 1b</td><td>row 1c</td><td>row 1d</td></tr>
      <tr><td>row 2a</td><td>row 2b</td><td>row 2c</td><td>row 2d</td></tr>
    </tbody>
  </table>
</main>
</body>
</html>
"""


def validate_library_css(
    css: str,
    site_dir: Path,
    cfg=DEFAULT,
    animated: bool = False,
) -> list[str]:
    """Render a small kitchen-sink page against the freshly-generated library
    at the configured desktop viewport and surface library-level breakage:

      - horizontal overflow at desktop (the library defines a primitive
        wider than the viewport — rare but seen once at ~1453px)
      - off-origin requests (catches Google Fonts in @import url())
      - @keyframes / animation declarations (static mode only; skipped when animated=True)
      - external URLs in @import / url() (offline constraint)

    `site_dir` is a working directory where `styles.css` is already written
    (so the smoke HTML can `<link>` to it via relative path). We write the
    smoke HTML into the same dir under `_library_smoke.html`, render, and
    delete the smoke HTML afterwards so it doesn't pollute the per-site
    output. Screenshot is retained at `_library_smoke.<viewport>.png` for
    debugging if the check fails.
    """
    issues: list[str] = []

    if not animated and _KEYFRAMES.search(css):
        issues.append("library declares @keyframes / animation (static-only constraint)")
    if _EXTERNAL_URL_IN_CSS.search(css):
        issues.append("library uses external URL in @import or url(...) (offline constraint)")

    smoke_html = site_dir / "_library_smoke.html"
    smoke_html.write_text(_LIBRARY_SMOKE_HTML)

    screenshots_dir = site_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    OVERFLOW_TOLERANCE_PX = 5
    smoke_pngs: list[Path] = []

    for vp_name, (vp_w, vp_h) in cfg.viewports.items():
        out_png = screenshots_dir / f"_library_smoke.{vp_name}.png"
        smoke_pngs.append(out_png)
        try:
            meta = _render_mod.render(
                source=str(smoke_html),
                output_png=out_png,
                viewport_width=vp_w,
                viewport_height=vp_h,
                full_page=True,
                fail_on_off_origin=False,
            )
            scroll_w = meta.get("scroll_width", vp_w)
            if scroll_w > vp_w + OVERFLOW_TOLERANCE_PX:
                issues.append(
                    f"library overflows horizontally at {vp_name} (scrollWidth {scroll_w}px > viewport {vp_w}px) — "
                    f"a primitive in styles.css has a fixed width. "
                    f"Use `max-width` + `width: 100%` for containers and add @media rules to collapse "
                    f"grids/nav at {vp_w}px."
                )
            for req in meta.get("off_origin_requests") or []:
                issues.append(
                    f"library triggers off-origin request to {req.get('url')} — remove any external @import / url()"
                )
                break
        except Exception as e:
            issues.append(f"library smoke render failed at {vp_name}: {type(e).__name__}: {e}")

    # Clean up smoke HTML; keep screenshots only if there were issues.
    try:
        smoke_html.unlink()
    except Exception:
        pass
    if not issues:
        for p in smoke_pngs:
            try:
                p.unlink()
            except Exception:
                pass

    return issues


def render_and_validate(
    *,
    site_dir: Path,
    page_slug: str,
    cfg=DEFAULT,
    spec=None,
) -> ValidationResult:
    """Render one page at all configured viewports.

    site_dir/<page_slug>.html must already exist. Screenshots are written to
    site_dir/screenshots/<page_slug>.<viewport>.png and metadata to
    site_dir/screenshots/<page_slug>.<viewport>.meta.json.
    """
    res = ValidationResult(ok=True, site_id=site_dir.name, page_slug=page_slug)

    html_path = site_dir / f"{page_slug}.html"
    if not html_path.exists():
        res.ok = False
        res.issues.append(f"missing HTML: {html_path}")
        return res

    animated = spec is not None and bool(getattr(spec, "animation_spec", None))

    html_text = html_path.read_text(errors="replace")
    css_path = site_dir / "styles.css"
    css_text = css_path.read_text(errors="replace") if css_path.exists() else ""
    static_html_checks(html_text, res.issues, css=css_text, spec=spec, animated=animated)

    screenshots_dir = site_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    off_origin_seen: list[dict] = []
    viewport_results = _render_all_viewports(
        html_path=html_path,
        screenshots_dir=screenshots_dir,
        page_slug=page_slug,
        cfg=cfg,
    )
    # Horizontal-overflow tolerance: allow ~5px slop for scrollbar / rounding.
    OVERFLOW_TOLERANCE_PX = 5
    for vp_name, (ok, meta_or_err) in viewport_results.items():
        if not ok:
            res.ok = False
            res.issues.append(f"render failed at {vp_name}: {meta_or_err}")
            continue
        meta = meta_or_err
        out_png = screenshots_dir / f"{page_slug}.{vp_name}.png"
        res.screenshots[vp_name] = out_png
        res.render_meta[vp_name] = meta
        # Responsive-fit check: at every configured viewport (desktop-only
        # in smoke per R12), the page should fit without horizontal overflow.
        # With full_page=True an overflowing page also produces an oversized
        # PNG that mismatches the SUT — caught here as a retry trigger.
        viewport_w = cfg.viewports[vp_name][0]
        scroll_w = meta.get("scroll_width", viewport_w)
        if scroll_w > viewport_w + OVERFLOW_TOLERANCE_PX:
            res.issues.append(
                f"page overflows horizontally at {vp_name} (scrollWidth {scroll_w}px > viewport {viewport_w}px) — "
                f"design is not responsive; remove fixed widths / `min-width` on top-level containers"
            )
        # ZERO off-origin requests allowed — the grader's anti-cheat
        # (pipeline/grader/anticheat.py:detect_off_origin) flags any
        # off-origin request the agent's render makes. The reference must
        # follow the same rule so the oracle solve.sh scores ~1.0.
        for req in meta.get("off_origin_requests") or []:
            off_origin_seen.append(req)
        if meta.get("console"):
            errors = [c for c in meta["console"] if c.get("type") == "error"]
            if errors:
                res.issues.append(f"{vp_name}: {len(errors)} console error(s)")

    if off_origin_seen:
        res.issues.append(
            f"off-origin requests during render: {[r['url'] for r in off_origin_seen[:3]]} "
            "(reference must be fully offline; this would trigger anti-cheat at grade time)"
        )

    # Animation keyframe capture + filmstrip (Part 2 tasks only)
    # Run even if there are non-fatal issues (e.g. overflow warnings) —
    # only skip if a render actually failed.
    has_render_failure = any("render failed" in iss for iss in res.issues)
    if animated and not has_render_failure:
        for vp_name, (w, h) in cfg.viewports.items():
            try:
                anim_result = capture_animation_keyframes(
                    html_path=html_path,
                    screenshots_dir=screenshots_dir,
                    page_slug=page_slug,
                    viewport_w=w,
                    viewport_h=h,
                    keyframe_pcts=cfg.animation_keyframe_pcts,
                    vp_name=vp_name,
                )
                if not anim_result["animation_metadata"]:
                    res.issues.append(f"{vp_name}: no animations detected at runtime (expected animations from spec)")
            except Exception as e:
                res.issues.append(f"{vp_name}: animation capture failed: {e}")

            try:
                capture_animation_filmstrip(
                    html_path=html_path,
                    screenshots_dir=screenshots_dir,
                    page_slug=page_slug,
                    viewport_w=w,
                    viewport_h=h,
                    vp_name=vp_name,
                )
            except Exception as e:
                res.issues.append(f"{vp_name}: filmstrip capture failed: {e}")

    # DOM-depth + tag-count check via simple text parsing.
    tag_count, depth = _estimate_dom_metrics(html_text)
    if tag_count < cfg.min_tag_count:
        res.issues.append(f"tag count {tag_count} < floor {cfg.min_tag_count}")
    if depth < cfg.min_dom_depth:
        res.issues.append(f"DOM depth {depth} < floor {cfg.min_dom_depth}")

    # Smoke wave: surface issues but don't hard-fail. The user inspects every site.
    return res


def _render_all_viewports(
    *,
    html_path: Path,
    screenshots_dir: Path,
    page_slug: str,
    cfg,
) -> dict[str, tuple[bool, object]]:
    """Render every viewport for one page. Smoke runs sequential, single-browser-
    per-viewport (uses the shipped pipeline/render.py). Pilot+ runs in a shared
    browser, optionally with concurrent viewport contexts.

    Returns: {vp_name: (ok, meta_dict_or_error_str)}
    """
    results: dict[str, tuple[bool, object]] = {}
    if cfg.parallel_viewports <= 1 and cfg.screenshot_max_height <= 0:
        # Smoke path — unchanged behavior: one browser launch per viewport.
        for vp_name, (w, h) in cfg.viewports.items():
            out_png = screenshots_dir / f"{page_slug}.{vp_name}.png"
            try:
                meta = _render_mod.render(
                    source=str(html_path),
                    output_png=out_png,
                    viewport_width=w,
                    viewport_height=h,
                    full_page=True,
                    fail_on_off_origin=False,
                )
                results[vp_name] = (True, meta)
            except Exception as e:
                results[vp_name] = (False, str(e))
        return results

    # Pilot+ path — single shared browser, optional concurrency, optional clip.
    return _render_all_viewports_shared(
        html_path=html_path,
        screenshots_dir=screenshots_dir,
        page_slug=page_slug,
        cfg=cfg,
    )


def _render_all_viewports_shared(
    *,
    html_path: Path,
    screenshots_dir: Path,
    page_slug: str,
    cfg,
) -> dict[str, tuple[bool, object]]:
    """Pilot/production path: one Chromium browser, one context per viewport.

    Playwright sync_api is NOT thread-safe across contexts, so we don't use
    ThreadPoolExecutor — we render contexts sequentially within a single
    browser session. The savings vs. smoke come from amortizing the ~1s
    browser cold-start across all viewports (so per-page wall clock drops
    from ~3s overhead to ~1s) and from the screenshot-height clip avoiding
    runaway memory on tall pages.

    For true concurrent viewport rendering we'd need playwright.async_api +
    asyncio.gather — left for a later iteration if the wall-clock matters.
    """
    from playwright.sync_api import sync_playwright
    from urllib.parse import urlparse

    results: dict[str, tuple[bool, object]] = {}
    source_url = f"file://{html_path.resolve()}"

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for vp_name, (w, h) in cfg.viewports.items():
                out_png = screenshots_dir / f"{page_slug}.{vp_name}.png"
                try:
                    meta = _render_one_in_browser(
                        browser=browser,
                        source_url=source_url,
                        out_png=out_png,
                        viewport_w=w,
                        viewport_h=h,
                        max_height=cfg.screenshot_max_height,
                    )
                    results[vp_name] = (True, meta)
                except Exception as e:
                    results[vp_name] = (False, f"{type(e).__name__}: {e}")
        finally:
            browser.close()

    return results


def _render_one_in_browser(
    *,
    browser,
    source_url: str,
    out_png: Path,
    viewport_w: int,
    viewport_h: int,
    max_height: int,
) -> dict:
    from urllib.parse import urlparse

    console: list = []
    requests_log: list = []
    off_origin: list = []

    ctx = browser.new_context(
        viewport={"width": viewport_w, "height": viewport_h},
        device_scale_factor=1,
    )
    page = ctx.new_page()
    page.on("console", lambda m: console.append({"type": m.type, "text": m.text}))

    def on_request(req):
        entry = {"method": req.method, "url": req.url, "resource_type": req.resource_type}
        requests_log.append(entry)
        src = urlparse(source_url)
        rq = urlparse(req.url)
        if src.scheme == "file" and rq.scheme in {"http", "https"}:
            off_origin.append(entry)

    page.on("request", on_request)
    page.goto(source_url, wait_until="load")
    try:
        page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
    except Exception:
        pass
    page.wait_for_timeout(500)

    # Responsive-fit check: capture scrollWidth so the caller can flag
    # horizontal overflow at small viewports. We tolerate 1px rounding.
    try:
        scroll_w = int(page.evaluate("() => document.body.scrollWidth"))
    except Exception:
        scroll_w = viewport_w

    # Screenshot height guard — bounds the pixel buffer at ~max_height to
    # prevent OOMs on pathological tall pages. 0 means uncapped.
    out_png.parent.mkdir(parents=True, exist_ok=True)
    if max_height > 0:
        try:
            body_h = int(page.evaluate("() => document.body.scrollHeight"))
        except Exception:
            body_h = viewport_h
        clip_h = min(body_h, max_height)
        page.screenshot(
            path=str(out_png),
            clip={"x": 0, "y": 0, "width": viewport_w, "height": clip_h},
        )
        if body_h > max_height:
            console.append({"type": "info", "text": f"clipped screenshot: body {body_h}px -> {max_height}px"})
    else:
        page.screenshot(path=str(out_png), full_page=True, type="png")

    ctx.close()

    return {
        "source": source_url,
        "output": str(out_png),
        "viewport": {"width": viewport_w, "height": viewport_h},
        "scroll_width": scroll_w,
        "full_page": max_height <= 0,
        "console": console,
        "network": requests_log,
        "off_origin_requests": off_origin,
    }


# ---------------------------------------------------------------------------
# Animation keyframe capture
# ---------------------------------------------------------------------------

_ANIMATION_EXTRACT_JS = """() => {
    const anims = document.getAnimations();
    return anims.map(a => {
        const effect = a.effect;
        const timing = effect ? effect.getComputedTiming() : {};
        const keyframes = effect ? effect.getKeyframes() : [];
        const target = effect && effect.target ? {
            tag: effect.target.tagName,
            className: effect.target.className,
            id: effect.target.id || null,
        } : null;
        return {
            name: a instanceof CSSAnimation ? a.animationName : (a instanceof CSSTransition ? a.transitionProperty : 'unknown'),
            type: a.constructor.name,
            duration: timing.duration || 0,
            delay: timing.delay || 0,
            iterations: timing.iterations || 1,
            easing: timing.easing || 'linear',
            direction: timing.direction || 'normal',
            fillMode: timing.fill || 'none',
            keyframes: keyframes.map(kf => {
                const obj = {};
                for (const [k, v] of Object.entries(kf)) {
                    if (k !== 'composite' && k !== 'computedOffset') obj[k] = v;
                }
                return obj;
            }),
            target: target,
        };
    });
}"""


def capture_animation_keyframes(
    html_path: Path,
    screenshots_dir: Path,
    page_slug: str,
    viewport_w: int,
    viewport_h: int,
    keyframe_pcts: list[float],
    vp_name: str = "desktop",
) -> dict:
    """Capture screenshots at specific animation progress points.

    Uses the Web Animations API to pause and seek all animations, then
    screenshots at each progress percentage. Also extracts animation metadata.

    Returns dict with 'keyframe_screenshots' and 'animation_metadata'.
    """
    import json as _json
    from playwright.sync_api import sync_playwright

    source_url = f"file://{html_path.resolve()}"
    result: dict = {"keyframe_screenshots": {}, "animation_metadata": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            viewport={"width": viewport_w, "height": viewport_h},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        page.goto(source_url, wait_until="load")
        try:
            page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
        except Exception:
            pass

        # Pause all animations immediately — before they can complete.
        # Short entrance animations (300-600ms) finish quickly; pausing
        # first lets us seek back to 0% even after the browser has started
        # playing them.
        page.evaluate("() => document.getAnimations().forEach(a => a.pause())")

        animation_meta = page.evaluate(_ANIMATION_EXTRACT_JS)
        result["animation_metadata"] = animation_meta

        if not animation_meta:
            ctx.close()
            browser.close()
            return result

        max_duration = max((a.get("duration", 0) for a in animation_meta), default=0)
        if max_duration <= 0:
            max_duration = 1000

        for pct in keyframe_pcts:
            target_ms = pct * max_duration
            page.evaluate(f"""() => {{
                document.getAnimations().forEach(a => {{
                    a.pause();
                    a.currentTime = {target_ms};
                }});
            }}""")
            page.wait_for_timeout(50)

            pct_label = f"{int(pct * 100)}pct"
            out_png = screenshots_dir / f"{page_slug}.{vp_name}.anim_{pct_label}.png"
            page.screenshot(
                path=str(out_png),
                full_page=True,
                type="png",
                animations="allow",
            )
            result["keyframe_screenshots"][pct_label] = out_png

        meta_path = screenshots_dir / f"{page_slug}.{vp_name}.animations.json"
        meta_path.write_text(_json.dumps(animation_meta, indent=2))

        ctx.close()
        browser.close()

    return result


def capture_animation_filmstrip(
    html_path: Path,
    screenshots_dir: Path,
    page_slug: str,
    viewport_w: int,
    viewport_h: int,
    vp_name: str = "desktop",
    n_frames: int = 10,
) -> Path | None:
    """Capture n_frames across the animation timeline, stitch into a filmstrip PNG.

    The filmstrip is a horizontal grid of frames, each labeled with its
    timestamp. Used as input for VLM animation judging.

    Returns the path to the filmstrip PNG, or None if no animations found.
    """
    import json as _json
    from PIL import Image, ImageDraw, ImageFont
    from playwright.sync_api import sync_playwright

    source_url = f"file://{html_path.resolve()}"
    frame_pngs: list[Path] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            viewport={"width": viewport_w, "height": viewport_h},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        page.goto(source_url, wait_until="load")
        try:
            page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
        except Exception:
            pass

        page.evaluate("() => document.getAnimations().forEach(a => a.pause())")
        animation_meta = page.evaluate(_ANIMATION_EXTRACT_JS)

        if not animation_meta:
            ctx.close()
            browser.close()
            return None

        # Use entrance-only duration (finite animations) so the filmstrip
        # focuses on entrance animations rather than being dominated by
        # long ambient loops. Fall back to max of all if no finite ones.
        finite_ends = [
            a.get("duration", 0) + a.get("delay", 0)
            for a in animation_meta
            if a.get("iterations", 1) != float("inf") and a.get("iterations", 1) > 0
        ]
        max_duration = max(finite_ends, default=0)
        if max_duration <= 0:
            max_duration = max((a.get("duration", 0) for a in animation_meta), default=1000)
        if max_duration <= 0:
            max_duration = 1000

        filmstrip_dir = screenshots_dir / "_filmstrip_frames"
        filmstrip_dir.mkdir(parents=True, exist_ok=True)

        for i in range(n_frames):
            pct = i / max(n_frames - 1, 1)
            target_ms = pct * max_duration
            page.evaluate(f"""() => {{
                document.getAnimations().forEach(a => {{
                    a.pause();
                    a.currentTime = {target_ms};
                }});
            }}""")
            page.wait_for_timeout(30)

            frame_path = filmstrip_dir / f"{page_slug}.{vp_name}.frame_{i:02d}.png"
            page.screenshot(
                path=str(frame_path),
                full_page=False,
                type="png",
                animations="allow",
            )
            frame_pngs.append(frame_path)

        ctx.close()
        browser.close()

    if not frame_pngs:
        return None

    frames = [Image.open(p) for p in frame_pngs]
    frame_w, frame_h = frames[0].size

    cols = min(5, len(frames))
    rows = (len(frames) + cols - 1) // cols
    label_h = 20
    padding = 2
    strip_w = cols * (frame_w + padding) - padding
    strip_h = rows * (frame_h + label_h + padding) - padding

    filmstrip = Image.new("RGB", (strip_w, strip_h), (255, 255, 255))
    draw = ImageDraw.Draw(filmstrip)

    for idx, frame in enumerate(frames):
        col = idx % cols
        row = idx // cols
        x = col * (frame_w + padding)
        y = row * (frame_h + label_h + padding)

        pct = idx / max(len(frames) - 1, 1)
        ms = pct * max_duration
        draw.text((x + 2, y), f"{int(pct*100)}% ({int(ms)}ms)", fill=(0, 0, 0))
        filmstrip.paste(frame, (x, y + label_h))

    filmstrips_dir = screenshots_dir / "filmstrips"
    filmstrips_dir.mkdir(parents=True, exist_ok=True)
    filmstrip_path = filmstrips_dir / f"{page_slug}.{vp_name}.filmstrip.png"
    filmstrip.save(str(filmstrip_path), optimize=True)

    for fp in frame_pngs:
        try:
            fp.unlink()
        except Exception:
            pass
    try:
        filmstrip_dir.rmdir()
    except Exception:
        pass

    return filmstrip_path


def _estimate_dom_metrics(html: str) -> tuple[int, int]:
    """Rough tag-count + DOM-depth from text. Good enough for the floor check;
    a real parser is overkill for a structural sanity test.
    """
    tag_open = re.compile(r"<(?!/|!)([a-zA-Z][^\s/>]*)", re.IGNORECASE)
    tag_close = re.compile(r"</([a-zA-Z][^\s>]*)", re.IGNORECASE)
    void = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr",
    }
    depth = 0
    max_depth = 0
    count = 0
    i = 0
    n = len(html)
    while i < n:
        ch = html[i]
        if ch != "<":
            i += 1
            continue
        if html.startswith("<!--", i):
            j = html.find("-->", i + 4)
            i = j + 3 if j >= 0 else n
            continue
        if html.startswith("</", i):
            m = tag_close.match(html, i)
            if m:
                depth = max(0, depth - 1)
                i = html.find(">", i) + 1 if html.find(">", i) >= 0 else n
                continue
            i += 1
            continue
        m = tag_open.match(html, i)
        if m:
            name = m.group(1).lower()
            close = html.find(">", i)
            chunk = html[i: close + 1] if close > 0 else html[i:]
            count += 1
            if name not in void and not chunk.rstrip().endswith("/>"):
                depth += 1
                max_depth = max(max_depth, depth)
            i = close + 1 if close > 0 else n
            continue
        i += 1
    return count, max_depth
