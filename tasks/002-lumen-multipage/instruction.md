Replicate the multi-page website design shown in the reference screenshots.

**Input:** `/reference/` contains one PNG per (page, viewport) pair, named `{page}.{viewport}.png`. With 5 pages × 3 viewports (`desktop`, `tablet`, `mobile`), expect 15 files:

```
index.desktop.png    index.tablet.png    index.mobile.png
features.desktop.png features.tablet.png features.mobile.png
pricing.desktop.png  pricing.tablet.png  pricing.mobile.png
docs.desktop.png     docs.tablet.png     docs.mobile.png
changelog.desktop.png changelog.tablet.png changelog.mobile.png
```

The five pages share a single design system — same nav, footer, colors, typography, button styles — and each page is expected to adapt responsively across the three viewports.

**Output:** Save HTML + CSS to `/app/`. The grader will look for:

```
/app/index.html
/app/features.html
/app/pricing.html
/app/docs.html
/app/changelog.html
```

You may use a shared CSS file (e.g. `/app/styles.css`) and link to it from each HTML. Anything in `/app/` is fair game; CSS files can be referenced via relative paths.

**How you'll be graded:**
Each of your HTML files will be rendered in headless Chromium and compared to the corresponding reference screenshot. The grader currently scores the following viewport(s):

| Viewport tag | Width × Height |
| ------------ | -------------- |
| `desktop`    | 1440 × 900     |
| `tablet`     | 768 × 1024     |
| `mobile`     | 375 × 812      |

A reference screenshot exists for every (page, viewport) pair listed above (filename pattern `{page}.{viewport}.png`). Your score reflects faithfulness across every (page, viewport) pair.

**Constraints:**
- HTML and CSS only. The grader runs offline, so external resources (CDNs, web fonts, hotlinked images) will not load. Design self-contained output.
- No JavaScript is needed; functionality is out of scope.
- Aim for visual replication across all 5 pages — layout, typography, colors, spacing, and content.
- Avoid horizontal overflow at any of the graded viewports (1440 / 768 / 375 px) — content cut off at the edges will be penalized.

The grader is a black box. Focus on producing faithful visual replicas.
