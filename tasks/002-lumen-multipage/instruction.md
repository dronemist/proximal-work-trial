Replicate the multi-page website design shown in the reference screenshots.

**Input:** `/reference/` contains 5 PNG files — one per page, rendered at desktop (1440×900) — named `{page}.desktop.png`:

```
index.desktop.png
features.desktop.png
pricing.desktop.png
docs.desktop.png
changelog.desktop.png
```

All screenshots are captured at a 1440px viewport. The five pages share a single design system — same nav, footer, colors, typography, button styles.

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
Each of your HTML files will be rendered in headless Chromium at 1440×900 and compared to the corresponding reference screenshot. Your score aggregates across all 5 pages with a harmonic mean — a single broken page meaningfully lowers your overall score.

**Constraints:**
- HTML and CSS only. The grader runs offline, so external resources (CDNs, web fonts, hotlinked images) will not load. Design self-contained output.
- No JavaScript is needed; functionality is out of scope.
- Aim for visual replication across all 5 pages — layout, typography, colors, spacing, and content.
- Avoid horizontal overflow at the 1440px viewport — content cut off at the edges will be penalized.

The grader is a black box. Focus on producing faithful visual replicas.
