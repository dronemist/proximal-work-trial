# Design Decisions

The key architectural choices behind the pipeline and grading system, grouped by area.

---

## 1. Data Generation

### Generate, Don't Crawl

The task specification requires that websites are generated, not crawled. We embraced this constraint because it also gives us significant advantages:
- **Perfect ground truth.** We have the exact HTML+CSS that produced each reference screenshot, which becomes the oracle solution.
- **Controlled complexity.** We choose the difficulty distribution rather than inheriting whatever the web happens to have.
- **No legal/licensing risk.** Generated content is original.
- **Reproducibility.** Given a seed, every site is deterministic.

The tradeoff is that LLM-generated sites are stylistically narrower than real websites. We mitigate this with diversity by construction (below) and acknowledge it as a [limitation](limitations.md#single-generator-model).

### Diversity by Construction, Not Sampling

Random generation with LLMs collapses to a narrow aesthetic — typically clean SaaS landing pages. We force diversity by defining 5 independent axes (domain, archetype, palette, typography, theme) and shuffling each independently with deterministic seeds. Site *i* gets `pool[i % pool_size]` from each shuffled pool, guaranteeing no two sites in a batch share any axis value.

This matters for RL: if two tasks share a domain AND an archetype, the agent could overfit to that combination rather than learning general design replication. See [Pipeline — Stage 1](data-generation.md#stage-1-brand-spec-sampling) for the full mechanism.

### Shared Component Library Per Site

Each site has a single `styles.css` that all pages share, rather than per-page styles. This mirrors real web development (a design system consumed by multiple pages) and makes the task harder: the agent must discover the underlying system from screenshots, not just pixel-match individual pages. It also enforces cross-page consistency — shared headers, footers, color tokens, and component patterns. See [Pipeline — Stage 3](data-generation.md#stage-3-component-library-stylescss) for how the library is generated.

### Multi-Viewport Generation

Early pipeline runs revealed that LLMs are weak at generating genuinely responsive CSS — ~30% of reference pages overflowed at mobile despite retry loops. When the reference itself isn't responsive, a properly-responsive agent submission actually scores *worse* (the responsive layout doesn't match the cropped reference), inverting the gradient. We resolved this through improved generation prompts, overflow validation with retries, and validating reference sites for responsiveness before inclusion. This validation step is load-bearing. See [Pipeline — Stage 5](data-generation.md#stage-5-render--validate) for the full validation checklist and [Results](results.md) for the empirical observations.

### Validation at Generation Time and Grading Time

Every reference page passes structural validation, anti-cheat checks, and cross-page coherence verification before inclusion. The same checks run again at grading time on agent output — ensuring the reference never contains patterns that would be penalized if an agent reproduced them. Each check exists because of a specific failure discovered during development: ~30% of early pages overflowed at mobile, off-origin font imports caused silent render drift, and ~18% of agent trials (9/50) were false-positive flagged by the anticheat system for faithfully reproducing inline SVG icons and data URIs that the reference itself contained.

See [Data Generation — Stage 5](data-generation.md#stage-5-render--validate) for the full validation checklist and [Data Generation — Why Validation Was Hard](data-generation.md#why-validation-was-hard-and-necessary) for the iteration story.

---

## 2. Grading Philosophy

### Continuous Composite Scoring, Not Pass/Fail

A single pixel-similarity metric conflates many failure modes and gives no gradient signal for RL. We decompose the score into 8 independent axes — each measuring a different quality (layout structure, color accuracy, text fidelity, typography, pixel similarity, positional accuracy, responsiveness, semantic match). This tells the agent *what* it got wrong, not just *how wrong* it is.

Each metric returns a continuous score in [0.0, 1.0]. There are no cliff edges where a good change hurts the score — every improvement in any visual dimension increases the reward. See [Grading — Metric Suite](grading.md#metric-suite) for the full breakdown.

### Harmonic Aggregation Punishes Inconsistency

We use harmonic mean across viewports (within a page) and across pages (within a site). A site that nails 4 pages but completely misses the 5th scores much lower than one that does all 5 at 70%. A page with perfect desktop but broken mobile scores lower than one that is adequate everywhere.

This is deliberate: for multi-page responsive design replication, consistency matters more than peak performance. Arithmetic mean would hide failures; harmonic mean surfaces them. See [Grading — Three-Tier Aggregation](grading.md#three-tier-aggregation) for the full aggregation diagram.

### VLM as Ceiling, Overflow as Multiplier

Overflow and VLM judge have weight 0 in the arithmetic mean but are applied separately to the composite. The locked v6 form is:

```text
base       = min(structured, vlm_score)
composite  = base × (0.5 + 0.5 × overflow_score)
```

This separation exists because each measures a qualitatively different axis:
- **VLM judge** acts as a `min()` ceiling on the structured score. It catches semantic errors that no structured metric covers (wrong chart shapes, fabricated UI elements, mismatched icons). During calibration we found VLM's discrimination was too weak in the middle band to be a reliable weighted metric (Oracle-vs-Claude gap of only 0.044), but it works well as a ceiling that pulls down scores on qualitative mismatches. See [`grade.py`](../pipeline/grader/grade.py).
- **Overflow** acts as a multiplicative factor on the (already VLM-capped) base. A fully non-responsive page (overflow_score = 0) drags the composite down by 50%; a fully responsive page (overflow_score = 1) leaves it untouched. We chose a multiplier over a `min()` here because responsiveness is a graded failure — a page can be partially broken at mobile — and we want that partiality reflected smoothly rather than clamped. See [`grade.py`](../pipeline/grader/grade.py) and [`metrics.py`](../pipeline/grader/metrics.py).

The two ceilings stack: VLM caps content-fidelity errors, then overflow scales the result by responsiveness. A page that looks right but doesn't reflow loses up to half its score; a page that reflows perfectly but has fabricated content is capped by VLM.

### Anti-Cheat Philosophy

The reference HTML/CSS *is* the ground truth, and at grading time the reference PNGs sit on disk inside the container. Without anti-cheat, the dominant strategy is trivially: copy the reference into `/app/` and score 1.0. The anti-cheat layer exists to make that strategy fail, and to make near-variants of it fail (embedding the reference as a base64 data URI, fetching it over the network, wrapping it in an iframe, encoding it as one giant SVG path). Four principles shape the design:

**1. Defense in depth, three layers.** Static checks scan the source HTML/CSS (data-URI size, iframe/canvas/object/embed tags, raster image files, oversized inline SVGs, byte-identical copies of reference PNGs). Dynamic checks read the rendered DOM and Playwright request log (off-origin HTTP requests, post-render SVG bbox vs viewport). Network checks read the logging proxy's CONNECT log. Each layer catches things the others can't — a CSS-only fetch trick that bypasses the static scan still appears in the proxy log; a static SVG that looks fine in source but renders huge is caught by the rendered-bbox check. See [Grading — Anti-Cheat System](grading.md#anti-cheat-system) for the full check list.

**2. Logging proxy over firewall.** Modal containers run on gVisor, which doesn't support iptables, so kernel-level network blocking isn't an option. We use a userspace HTTPS proxy that logs every CONNECT — fully observable, and converting it to a blocking proxy is a one-line change. We deliberately log rather than block during eval because seeing *what* the agent tries to fetch is more useful than silently denying it; the proxy catches CDN hotlinking, image fetching, npm pulls, and any hostname-addressed request. See [Grading — Network Proxy](grading.md#network-proxy-observability-layer).

**3. Asymmetric penalties for eval vs RL.** For eval, any violation triggers a flat **0.1× multiplier** — a single cheat attempt drops a 0.8 score to 0.08. This is categorical because at eval time we want a clean signal: "did this trial cheat or not?" For RL training, that cliff destroys gradient — the agent has no way to learn *which* violation to fix. So RL uses a softer subtractive penalty: 0.05 per distinct violation type, capped at 0.20. Same checks, two penalty modes, picked at scoring time.

**4. Symmetric validation: the reference must pass the same checks.** Early calibration found 9/50 trials (18%) were clobbered by false positives — the agent faithfully reproduced an inline SVG icon or a small data URI that the *reference itself* contained, and got penalised for it. We fixed this by running every anti-cheat check on the reference at generation time and rejecting any reference that doesn't pass. This is load-bearing: it's why `data_image_uri` has a 2KB threshold (small icons in the reference are legitimate), why `oversized_svg` requires both >50% viewport area *and* >4KB body (so a faithful small inline SVG isn't a violation), and why we have the symmetric validation principle in §1.

**5. The agent doesn't know what's checked.** [`instruction.md`](../../tasks/v9/001-gov-services-v7adv/instruction.md) tells the agent only the task ("replicate these screenshots"), the output paths, the viewports, and a short list of generic constraints (HTML/CSS only, no JS, no external resources, avoid horizontal overflow). It does *not* mention any specific anti-cheat check, the structured metrics, VLM judging, or the harmonic aggregation. This is deliberate: we measure faithful replication, not score-hacking against a known rubric. The module docstring in [`anticheat.py`](../pipeline/grader/anticheat.py) records exactly which internals are withheld.

---

## 3. Infrastructure

### Framework-Agnostic Grading via Headless Render

The grader renders agent output in headless Chromium and grades the *rendered result*, not the source code. This means the same grader works for HTML+CSS today and for React+Tailwind or SolidJS in future parts — adding a framework only requires that it renders to HTML. The grader cares about what the user sees, not how the code is written.

### Same Renderer Everywhere

`render.py` is used by the reference generator, the packager, and the grader. Same Chromium version, same viewport sizes, same font stack, same Linux container image. This eliminates cross-platform rendering drift (macOS vs Linux, different Chromium versions, different system fonts). Oracle solutions score exactly 1.000 — any deviation would indicate a renderer inconsistency. See [Pipeline — Ensuring Training Data Correctness](data-generation.md#ensuring-training-data-correctness) for the full list of determinism guarantees.

---

## 4. Iterative Calibration

The reward function went through 8 calibration steps, each motivated by a specific failure mode observed in real agent trials. Key discoveries: SSIM zero-padding triple-counted truncation; palette needed bg/fg splitting for dark themes; block_match saturated at 400 blocks; overflow measured the wrong width when `overflow:hidden` was set; anticheat had 18% false positives from legitimate icons. See [Grading — Calibration History](grading.md#calibration-history) for the full story.

The calibration process itself is a key design output: it demonstrates that the reward function was empirically validated, not just theoretically motivated.
