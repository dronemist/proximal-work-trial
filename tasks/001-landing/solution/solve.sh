#!/bin/bash
# Oracle solution: writes the canonical reference HTML to /app/index.html.
# Used by `harbor run --agent oracle` as the "perfect agent" sanity check —
# this should score reward = 1.0. If it doesn't, the grader is broken.
#
# We embed the reference inline via heredoc rather than copying from /tests/,
# because the oracle's solve.sh runs in the AGENT container, which does not
# have /tests/ mounted.
set -euo pipefail

cat > /app/index.html <<'REFERENCE_HTML'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lumen — Analytics that ships</title>
<style>
  :root {
    --bg: #0b1020;
    --panel: #131a33;
    --ink: #e7ecff;
    --muted: #9aa7d1;
    --accent: #6a8cff;
    --accent-2: #b794ff;
    --border: #232a47;
    --radius: 14px;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: radial-gradient(1200px 600px at 80% -10%, rgba(106,140,255,0.18), transparent 60%),
                radial-gradient(900px 500px at -10% 110%, rgba(183,148,255,0.12), transparent 60%),
                var(--bg);
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
    line-height: 1.55;
  }
  .container { max-width: 1120px; margin: 0 auto; padding: 0 32px; }

  header.nav {
    padding: 22px 0;
    border-bottom: 1px solid var(--border);
  }
  .nav-inner { display: flex; align-items: center; justify-content: space-between; }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; letter-spacing: 0.2px; }
  .brand-mark {
    width: 28px; height: 28px; border-radius: 8px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
  }
  .nav-links { display: flex; gap: 28px; }
  .nav-links a { color: var(--muted); text-decoration: none; font-size: 14px; }
  .nav-links a:hover { color: var(--ink); }
  .nav-cta {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #0a0f24; text-decoration: none;
    padding: 8px 16px; border-radius: 999px;
    font-size: 14px; font-weight: 600;
  }

  section.hero {
    padding: 96px 0 72px;
    text-align: center;
  }
  .eyebrow {
    display: inline-block;
    color: var(--muted);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.02);
    padding: 6px 12px; border-radius: 999px;
    font-size: 12px; letter-spacing: 0.6px; text-transform: uppercase;
  }
  h1.headline {
    font-size: 56px; line-height: 1.05; margin: 22px auto 18px;
    max-width: 820px; font-weight: 700; letter-spacing: -0.5px;
  }
  h1.headline span {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  p.sub {
    color: var(--muted); font-size: 18px; max-width: 640px;
    margin: 0 auto 32px;
  }
  .cta-row { display: flex; gap: 14px; justify-content: center; }
  .btn {
    display: inline-block; padding: 12px 22px; border-radius: 10px;
    font-size: 15px; font-weight: 600; text-decoration: none; line-height: 1;
  }
  .btn-primary {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #0a0f24;
  }
  .btn-ghost {
    background: transparent; color: var(--ink);
    border: 1px solid var(--border);
  }

  section.features { padding: 64px 0 96px; }
  .features-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 22px;
  }
  .card {
    background: linear-gradient(180deg, var(--panel), #0f1530);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px;
  }
  .card-icon {
    width: 36px; height: 36px; border-radius: 9px;
    background: rgba(106,140,255,0.16);
    border: 1px solid rgba(106,140,255,0.32);
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 18px; color: var(--accent); font-weight: 700;
  }
  .card h3 { margin: 0 0 8px; font-size: 18px; }
  .card p { margin: 0; color: var(--muted); font-size: 14px; }

  footer.site-footer {
    border-top: 1px solid var(--border);
    padding: 28px 0;
    color: var(--muted);
    font-size: 13px;
  }
  .footer-inner { display: flex; justify-content: space-between; align-items: center; }
  .footer-links { display: flex; gap: 22px; }
  .footer-links a { color: var(--muted); text-decoration: none; }
</style>
</head>
<body>
  <header class="nav">
    <div class="container nav-inner">
      <div class="brand">
        <div class="brand-mark"></div>
        <span>Lumen</span>
      </div>
      <nav class="nav-links">
        <a href="#features">Features</a>
        <a href="#pricing">Pricing</a>
        <a href="#docs">Docs</a>
        <a href="#changelog">Changelog</a>
      </nav>
      <a class="nav-cta" href="#start">Get started</a>
    </div>
  </header>

  <section class="hero">
    <div class="container">
      <span class="eyebrow">New · v3 release</span>
      <h1 class="headline">Analytics that <span>ships</span> with your product.</h1>
      <p class="sub">Track what matters, ignore the rest. Lumen gives your product team realtime signals without the dashboard sprawl.</p>
      <div class="cta-row">
        <a class="btn btn-primary" href="#start">Start free</a>
        <a class="btn btn-ghost" href="#demo">Book a demo</a>
      </div>
    </div>
  </section>

  <section class="features" id="features">
    <div class="container">
      <div class="features-grid">
        <div class="card">
          <div class="card-icon">◆</div>
          <h3>Event streams</h3>
          <p>One-line SDK, autocaptured events, sane defaults out of the box.</p>
        </div>
        <div class="card">
          <div class="card-icon">▲</div>
          <h3>Cohorts</h3>
          <p>Slice by anything. Save once, share with your whole team.</p>
        </div>
        <div class="card">
          <div class="card-icon">●</div>
          <h3>Realtime</h3>
          <p>Sub-second freshness on the dashboards that page your on-call.</p>
        </div>
      </div>
    </div>
  </section>

  <footer class="site-footer">
    <div class="container footer-inner">
      <div>© 2026 Lumen Labs, Inc.</div>
      <div class="footer-links">
        <a href="#privacy">Privacy</a>
        <a href="#terms">Terms</a>
        <a href="#status">Status</a>
      </div>
    </div>
  </footer>
</body>
</html>
REFERENCE_HTML

echo "wrote /app/index.html ($(wc -c < /app/index.html) bytes)"
