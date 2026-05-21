Replicate the website design shown in the reference screenshot.

**Input:** `/reference/index.desktop.png` — a **full-page** screenshot of the website you must replicate, captured at desktop viewport width **1440px** (image height extends below the fold because the page scrolls).

**Output:** Save your HTML/CSS to `/app/`. The file `/app/index.html` will be rendered in headless Chromium at 1440px viewport, captured as a full-page screenshot, and compared to the reference.

**Constraints:**
- HTML and CSS only. Inline styles in `<style>` or `/app/*.css` referenced relatively.
- **The grader runs offline.** External resources (CDNs, web fonts via Google Fonts, hotlinked images) will not load — design for self-contained output.
- No JavaScript is needed; functionality is out of scope.
- Match the visual design — layout, typography, colors, spacing, and content — as closely as you can across the full page, including content below the fold.

The grader is a black box. Focus on producing a faithful visual replica.
