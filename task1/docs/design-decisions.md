# Design Decisions

Key architectural choices behind the pipeline and grading system, grouped by area.

---

## 1. Data Generation

### Generate, Don't Crawl

The task spec requires generated, not crawled, websites — and the constraint pays off: we get perfect ground truth (the exact HTML+CSS becomes the oracle), controlled difficulty, no licensing risk, and seed-level reproducibility. The tradeoff is stylistic narrowness, mitigated by diversity-by-construction (below) and acknowledged as a [limitation](limitations.md#single-generator-model).

### Diversity by Construction, Not Sampling

Random LLM generation collapses to clean SaaS landing pages. We force diversity by shuffling 5 independent axes (domain, archetype, palette, typography, theme) with deterministic seeds, so site *i* gets `pool[i % pool_size]` from each — no two sites in a batch share any axis value. This matters for RL: shared domain + archetype invites overfitting. See [Pipeline — Stage 1](data-generation.md#stage-1-brand-spec-sampling).

### Parallel Site Generation, Sequential Page Generation

Sites run in parallel across Modal containers (one container per site), but pages within a site run sequentially. Parallel-across-sites cuts wall-clock from hours to minutes at 100+ site batches; sequential-within-site preserves shared state — every page sees the same brief and the same `styles.css`, so navigation, footer, and component usage stay consistent. Parallelising pages would risk divergent header/footer implementations across the same site. Within a container, the render step parallelises across viewports (3 Chromium contexts at once), reclaiming the obvious win without breaking site-level coherence. See [Pipeline — Modal Parallelism](data-generation.md#infrastructure-modal-parallelism).

### Multi-Viewport, Validated for Responsiveness

LLMs are weak at responsive CSS — ~30% of early reference pages overflowed at mobile. A non-responsive reference inverts the gradient: a properly-responsive agent submission scores *worse* because its layout doesn't match the cropped reference. Fixed via overflow validation with retries before inclusion; this validation step is load-bearing. See [Pipeline — Stage 5](data-generation.md#stage-5-render--validate).

### Symmetric Validation: Reference Must Pass Same Checks as Agent

Every anti-cheat and structural check runs on the reference at generation time and on agent output at grading time. Originally only the agent was checked, and 18% (9/50) of trials were clobbered by false positives — agents faithfully reproducing an inline SVG icon or small data URI from the *reference itself*. Now any reference that wouldn't pass agent-time checks is rejected upfront. See [Data Generation — Stage 5](data-generation.md#stage-5-render--validate).

---

## 2. Grading Philosophy

### Continuous Composite, Not Pass/Fail

A single pixel-similarity metric conflates failure modes and gives no RL gradient. We decompose into 8 axes (layout, color, text, typography, pixel, position, responsiveness, semantic). Every metric is continuous on [0, 1] — no cliff edges where a good change hurts the score. See [Grading — Metric Suite](grading.md#metric-suite).

### Harmonic Aggregation Punishes Inconsistency

Harmonic mean across viewports (within a page) and across pages (within a site). One broken page or one broken viewport drags the whole score down — arithmetic mean would hide failures. See [Grading — Three-Tier Aggregation](grading.md#three-tier-aggregation).

### VLM as Ceiling, Overflow as Multiplier

```text
base       = min(structured, vlm_score)
composite  = base × (0.5 + 0.5 × overflow_score)
```

- **VLM judge** as `min()` ceiling — catches qualitative errors (wrong chart shapes, fabricated UI, semantic mismatches) that no structured metric covers. Calibration showed VLM's discrimination is too weak in the middle band to be a weighted metric (Oracle–Claude gap 0.044), but it works as a one-sided cap.
- **Overflow** as multiplier — responsiveness is a graded property, so a smooth `0.5 + 0.5·x` factor reflects partial breakage better than a hard `min()`. A fully non-responsive page loses 50%.

### Anti-Cheat

The reference PNGs sit on disk in the agent's container, so the trivial winning strategy is "copy reference, score 1.0". Four choices defeat it and its near-variants (data URI, iframe, network fetch, giant SVG):

- **Three-layer defense.** Static source scan, dynamic rendered-DOM check, network proxy log. See [Grading — Anti-Cheat](grading.md#anti-cheat-system).
- **Logging proxy, not firewall.** gVisor blocks iptables; a userspace HTTPS proxy logs every CONNECT and is one line away from blocking.
- **Asymmetric penalties.** Eval: flat 0.1× multiplier (clean cheat/no-cheat signal). RL: subtractive `0.05 × distinct_violations`, capped at 0.20 (preserves gradient).
- **Rubric withheld from the agent.** `instruction.md` lists task and output paths only — no metrics, weights, ceilings, or checks. We measure replication, not rubric-gaming.

---

## 3. Infrastructure

### Framework-Agnostic Grading via Headless Render

The grader renders agent output in headless Chromium and grades the *rendered result*. Adding React/Tailwind/SolidJS later requires only that it renders to HTML — the grader cares about what the user sees, not how the code is written.

### Same Renderer Everywhere

`render.py` is used by the generator, packager, and grader — same Chromium version, viewports, font stack, container image. Eliminates macOS/Linux drift. Oracle solutions score exactly 1.000; any deviation indicates renderer inconsistency. See [Pipeline — Ensuring Training Data Correctness](data-generation.md#ensuring-training-data-correctness).

