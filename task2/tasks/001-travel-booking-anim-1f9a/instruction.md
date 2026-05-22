**IMPORTANT: Write all required HTML files plus shared CSS to /app/ before ending your turn. Do not stop after planning or after reading the references — keep going until every file listed in the Output section is written.**

Replicate the multi-page website design shown in the reference screenshots.

**Input:** `/reference/` contains 3 PNG files — one per (page, viewport) pair — named `{page}.{viewport}.png`:

```
properties.desktop.png  properties.tablet.png  properties.mobile.png
```

The 1 pages share a single design system — same nav, footer, colors, typography, button styles — and each page is expected to adapt responsively across the three viewports below. All screenshots are **full-page** captures (height extends below the fold).

| Viewport tag | Width × Height |
| ------------ | -------------- |
| `desktop`    | 1440 × 900     |
| `tablet`     | 768 × 1024     |
| `mobile`     | 375 × 812      |

**Output:** Save HTML + CSS to `/app/`. The grader will look for:

```
/app/properties.html
```

You may use a shared CSS file (e.g. `/app/styles.css`) and link to it from each HTML. Anything in `/app/` is fair game; CSS files can be referenced via relative paths.

**How you'll be graded:**
Each of your HTML files will be rendered in headless Chromium at every viewport listed above and compared to the corresponding reference screenshot. Cross-page consistency matters — a broken page meaningfully lowers your overall score, and so does a layout that breaks at tablet or mobile widths.

**Constraints:**
- HTML and CSS only. The grader runs offline, so external resources (CDNs, web fonts, hotlinked images) will not load. Design self-contained output.
- No JavaScript is needed; functionality is out of scope.
- Aim for visual replication across all 1 pages at every graded viewport — layout, typography, colors, spacing, and content.
- Avoid horizontal overflow at any of the graded viewports (1440 / 768 / 375 px) — content cut off at the edges will be penalized.

The grader is a black box. Focus on producing faithful visual replicas.

---

**Animations:** This design includes CSS animations. Your output will be graded on both static appearance AND animation fidelity. The `/reference/` directory includes filmstrip PNGs showing how animations progress over time — use these as visual reference.

The following animations are used:

- **`blur-in`** — entrance, ~333ms, animates: filter, opacity (×2)
- **`shimmer`** — looping/ambient, ~3320ms, animates: backgroundPositionX, backgroundPositionY (×2)
- **`rotate-in`** — entrance, ~742ms, animates: opacity, transform (×6)

Filmstrip references (in `/reference/filmstrips/`):

- `properties.desktop.filmstrip.png`
- `properties.tablet.filmstrip.png`
- `properties.mobile.filmstrip.png`

Video recordings of the animations (in `/reference/videos/`):

- `properties.desktop.webm`
- `properties.tablet.webm`
- `properties.mobile.webm`

**Animation grading:** The grader captures your animations at 0%, 50%, and 100% progress and compares against reference keyframes. It also generates a filmstrip of your output and uses a VLM judge to compare it against the reference filmstrip. Animation name, count, timing, and animated CSS properties all contribute to the animation score.

**Tips:**
- Use `@keyframes` with matching animation names
- Match durations and delays approximately
- Use `animation-fill-mode: both` for entrance animations
- Stagger entrance animations with increasing `animation-delay`
