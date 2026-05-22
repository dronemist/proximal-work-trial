# Key Design Decisions

This file logs the key design decisions made while building the design-to-code RL environment recipe. It will inform the final write-up. Entries are append-only; decisions that are later revised should be noted with a strikethrough and a revision entry below.

---

## Project Context

Work trial: build a scalable pipeline that creates RL environments for testing coding agents' ability to replicate multi-page website designs in code. The pipeline is built on the Harbor framework (harborframework.com), uses Claude Code with Opus 4.7 as the agent under test, and grades the agent's HTML/CSS output against generated reference websites.

Key requirements:
- Generate websites from scratch (cannot crawl)
- 5+ pages per website
- Continuous (not discrete) grading
- Good distribution of website types
- Functionality is out of scope — design fidelity only
- Parts 2 and 3 (later): animations, React+CSS, React+Tailwind, Solid+Tailwind

---

## Research Findings (background, not decisions)

### Initial scan
- **Harbor task structure:** `task.toml`, `instruction.md`, `environment/Dockerfile`, `tests/test.sh` (writes reward to `/logs/verifier/reward.txt`), `tests/test_outputs.py`, `solution/solve.sh`. Verifier runs in a separate container context from the agent.
- **Closest prior work — Design2Code (Stanford SALT NLP):** uses CLIP visual similarity + element-level matching (block position, text, color). Central conclusion: no single metric captures design fidelity well.
- **FrontierSWE:** uses average ranking + dominance metric + test-pass-rate@5 as partial reward. Informs the composite-with-continuous-signal approach.

### Deep literature survey (see `research/`)
Three lit reviews conducted on 2026-05-21:

- **`research/visual_grading_metrics.md`** — Headline: **the design-to-code field has already abandoned SSIM/LPIPS.** Ghildyal & Liu (ECCV 2022) quantified that SSIM flips rank on 3–14% of pairs after 1–3 px shifts that humans don't perceive. Design2Code/WebCode2M/IW-Bench/Sketch2Code all use **Block-Match** (Hungarian-matched element bboxes + per-block text/color/position) rather than pixel metrics. Newer work (Web2Code, DesignBench, UI-Bench, Vercel v0) uses **MLLM-as-judge**. DreamSim/DINOv2 are the consensus learned perceptual metrics elsewhere in vision but **have not been adopted in published web-replication benchmarks** — a literature gap we could exploit.
- **`research/generation_diversity.md`** — Headline: **synthetic-only LLM-generated websites collapse to a narrow SaaS-landing aesthetic.** WebCode2M measured 50× fewer tokens, 6× fewer tags, 2× shallower DOM than real pages. Recommended four-layer defense: (1) **primitive seeding** from real design tokens (palettes/fonts/spacing/archetypes — **novel, no published precedent**), (2) **Verbalized Sampling** (arXiv 2510.01171, 2–3× diversity at constant quality), (3) multi-model/multi-temperature mixing, (4) critic-filter via VLM judge. Track diversity with **Vendi Score over CLIP embeddings**.
- **`research/cross_page_consistency.md`** — Headline: **no published design-to-code benchmark grades multi-page coherence.** This is white space. Since our task spec mandates 5+ pages, building a cross-page consistency reward is a uniquely valuable contribution. Transferable methods: palette EMD/KL (FontGAN, Free-Lunch Color), typography embedding distance, DreamSim/CLIP-I across page pairs (ConsiStory, StoryDiffusion), header-DOM diff (TreeBLEU). Aggregate **multiplicatively** (per-page × (1 − λ·cross-page-variance)) per "Trickle-down RLHF" 2309.16155 and Intra-Trajectory Consistency 2506.09096.

### Reviewer pass
Critique in `reviews/001-design-review.md`, response in `reviews/001-design-review.response.md`. Major redirections (folded into revised decisions below):
- Reference-set is single-generator-bounded — needs multi-generator + human seeds.
- Hard-zero anti-cheat will collapse early RL training — needs graded penalties for training, hard-zero for held-out eval only.
- DOM-IoU is brittle and leaks Claude's markup conventions — replace with pixel-space segmentation OR follow Design2Code's Block-Match (literature consensus).
- LPIPS wrong for web screenshots — switch to DreamSim + text-region masking, tiled.
- Min/harmonic mean over viewports, not arithmetic mean.
- ±20px viewport jitter is theater — randomize widths continuously.
- 9 additional attack vectors (iframe srcdoc, inline SVG reproduction, CSS data URIs, `content: url()`, `@import data:`, render race conditions, font races, OCR adversarial text, animation timing).

---

## Decisions

### 1. Grading is a weighted composite of orthogonal components
**Date:** 2026-05-21
**Decision:** Final reward is a weighted sum of five components:
- **Visual Similarity (35%)** — SSIM + LPIPS on full-page screenshots
- **Layout Structure (25%)** — DOM bounding-box IoU of major sections
- **Text Content (15%)** — fuzzy string matching per-region
- **Color Accuracy (10%)** — dominant palette + histogram comparison
- **Responsive Fidelity (15%)** — score at 3 viewports (mobile/tablet/desktop), averaged

**Reasoning:**
- No single metric captures design fidelity well — this is Design2Code's central empirical finding. A composite is required to get a useful gradient signal for RL.
- The five components are *mostly orthogonal*, so each contributes independent signal rather than redundant variance. This produces a well-formed gradient for RL.
- Weights reflect what humans notice first: visual > layout > text > color, with responsive as a structural check that also doubles as an anti-cheat (see Decision 4).
- All components are continuous, satisfying the "continuous, not discrete" grading requirement.

**Tradeoffs / alternatives considered:**
- **LPIPS vs CLIP for visual similarity:** chose LPIPS. CLIP captures "feels like the same kind of page" which is too loose for exact replication — we want pixel-level fidelity, which LPIPS is designed for. CLIP would give partial credit for semantic similarity even when the design is wrong.
- **Pure pixel diff (MSE):** rejected — too brittle to small offsets that a human would consider correct.
- **Single end-to-end learned scorer:** rejected — opaque, hard to debug failure modes, and can't tell the agent *why* it lost points.
- **Equal weights:** rejected — visual fidelity is the headline goal; structure/text/color are corroborating signals.

---

### 2. Framework-agnostic grading via headless render
**Date:** 2026-05-21
**Decision:** Render the agent's output in headless Chromium, then screenshot and grade against the reference screenshots. Grade the rendered DOM, not the source code.

**Reasoning:**
- This makes the same grader work unchanged for Part 3 (React + CSS, React + Tailwind, Solid + Tailwind). The grader cares about what the user sees, not the source language.
- Aligns with the actual evaluation criterion: design fidelity is a property of the rendered page.
- Decouples grader development from framework support — adding a new framework only requires that it renders to HTML/CSS, which all of them do.

**Tradeoffs / alternatives considered:**
- **AST/source-level comparison:** rejected — framework-specific, brittle, and doesn't measure what we care about (visual output).
- **Per-framework graders:** rejected — multiplies maintenance burden across Parts 2 and 3.

---

### 3. Evalset generation pipeline
**Date:** 2026-05-21
**Decision:**
- Define a website taxonomy: SaaS landing, e-commerce, blog/magazine, portfolio, dashboard, documentation, restaurant/local business, event/conference, educational, nonprofit.
- Use Claude to generate complete 5+ page HTML/CSS sites from structured prompts specifying: category, business concept, design style (minimalist/bold/corporate/creative/brutalist/etc.), complexity tier, specific challenges (grids, gradients, etc.).
- Render + screenshot each page at 3 breakpoints — screenshots become ground truth shown to the agent.
- Strip generated source code — the agent never sees source.
- Use stratified sampling across categories with explicit complexity tiers (simple/medium/hard).

**Reasoning:**
- **Generate, don't crawl:** required by the prompt, and independently desirable for (a) legal/licensing safety, (b) perfect ground truth — we have the exact source the screenshot came from, (c) controlled complexity distribution, (d) no external network or rot dependencies in CI.
- **Taxonomy + stratified sampling:** the requirement is "good distribution of website types." Explicit categories make the distribution auditable and prevent mode collapse during generation.
- **Complexity tiers:** lets us evaluate at different difficulty levels and produce learning curves rather than a single scalar.
- **Strip source before showing to agent:** prevents the agent from trivially copying generated code; forces the model to actually reason from the visual.

**Tradeoffs / alternatives considered:**
- **Crawling real sites:** rejected — explicit project constraint, plus legal and reproducibility issues.
- **Hand-authored sites:** rejected — doesn't scale to 50–100 sites; defeats the "scalable pipeline" requirement.
- **Free-form generation without taxonomy:** rejected — would skew toward whatever the LLM defaults to (likely SaaS landing pages), hurting distribution quality.

---

### 4. Anti-cheat violations = hard zero
**Date:** 2026-05-21
**Decision:** Any detected anti-cheat violation results in a score of 0.0, not a graduated penalty. (User-confirmed.)

**Documented attack vectors and mitigations:**
1. **Screenshot embedding** (base64 data URIs / external images): reject any image URIs not in spec; check file size; verify the DOM has real structure rather than a single `<img>`.
2. **Absolute-positioning everything:** caught implicitly by the responsive fidelity component (absolute layouts break across viewports); additional static-analysis penalty if >50% of elements use absolute positioning.
3. **Invisible text overlay:** extract text via OCR on the rendered screenshot, not just DOM scrape — cross-check visible text vs DOM-only text.
4. **Single-viewport overfitting:** grade at 3 viewports; randomize the grading viewport by ±20px so exact pixel coordinates can't be memorized.
5. **Test script tampering:** Harbor's verifier-container isolation prevents agent access to `/tests/` and `/logs/verifier/`; additionally checksum the grading scripts.
6. **Training-data retrieval:** use unique business names, copy, and color combinations per task; include deliberate design quirks; check output doesn't contain unexpected framework signatures (e.g., Bootstrap classes) when those frameworks weren't requested.
7. **Minimal viable render** (blank page with the right background color): enforce a minimum DOM complexity threshold; partially self-defends via low SSIM/LPIPS on near-blank pages.

**Reasoning:**
- Cleaner RL signal: the model learns "do not do this category of thing" rather than "do this less." A graduated penalty creates an exploit gradient — the model can learn to do a *little* cheating if the marginal cost is below the marginal gain.
- Anti-cheat violations are categorical, not continuous quality issues — treating them as such matches their nature.
- User explicitly accepted the tradeoff that this creates a cliff (a borderline-legitimate page could score zero on a false positive). Mitigation: keep detectors conservative and prefer false negatives over false positives.

**Tradeoffs / alternatives considered:**
- **Graduated penalties:** rejected for the gradient-exploit reason above.
- **No anti-cheat:** rejected — Goodhart's law on a composite metric guarantees exploitation, especially under RL.

---

### 5. Out-of-scope for Part 1
**Date:** 2026-05-21
**Decision:** The following are explicitly out of scope for Part 1 (user-confirmed):
- **Inter-page navigation:** pages are graded independently and averaged. We are judging design, not link structure.
- **Functionality:** forms, JS interactivity, and any dynamic behavior are not graded.

**Reasoning:**
- The project prompt explicitly says "functionality is out of scope — design fidelity only." Keeping Part 1 narrow lets us produce a sharper grader and ship more polished tasks.
- Averaging per-page scores keeps the grader simple and the signal interpretable; cross-page consistency can be a later component if needed.

**Tradeoffs / alternatives considered:**
- **Grading navigation:** rejected for Part 1 — adds a discrete pass/fail dimension that doesn't fit the continuous-grading requirement and isn't part of "design fidelity."
- **Grading whole-site coherence (e.g., shared header/footer):** considered — deferred. Could be a future component but isn't needed to meet the Part 1 bar.

---

### 6. Budget posture
**Date:** 2026-05-21
**Decision:** No hard budget cap on Claude API generation calls. (User-confirmed.) Estimated cost: $0.50–$2.00 per generated 5-page site. Plan: generate 50–100 sites for the eval set; ship at least 10 final tasks for the deliverable.

**Reasoning:**
- Generation is a one-time cost that produces a reusable artifact (the eval set), so amortized cost per evaluation is low.
- 50–100 sites gives enough headroom to filter aggressively for quality and still ship 10 polished tasks.
- The user explicitly de-prioritized cost optimization at this stage in favor of quality.

**Tradeoffs / alternatives considered:**
- **Hard cap per site:** rejected — would force premature optimization of the generation prompt before we know what quality bar matters.
- **Smaller eval set (e.g., 10 sites):** rejected — leaves no room for filtering; one bad generation becomes 10% of the eval.

---

## Revisions (post-research + post-review)

> Append-only revisions below. Original decisions are preserved above for audit trail. Where a revision supersedes an earlier decision, the original is noted with ~~strikethrough~~ pointers.

### R1. Per-page grading — switch from pixel composite to Block-Match + perceptual + structural
**Date:** 2026-05-21
**Supersedes:** ~~Decision 1's "SSIM + LPIPS visual similarity"~~ and ~~"DOM-IoU on major sections"~~.

**Decision:** Per-page reward is a weighted composite of three families plus content sub-scores:

1. **Element-level Block-Match (Design2Code-style, literature standard):** detect visual element blocks (text/image rectangles), Hungarian-match candidate-to-reference by bbox IoU, then compute per-block sub-scores:
   - **Position** — distance between normalized bbox centers
   - **Text** — character-level Sørensen-Dice
   - **Color** — CIEDE2000 perceptual color difference
   - Aggregate score is area-weighted ratio of matched-to-total.
2. **Perceptual similarity (novel for web):** **DreamSim** (NeurIPS 2023; DINOv2-backbone refresh Oct 2024) on full-page screenshots, tiled into viewport-height chunks, with **text regions masked via OCR before scoring** (text gets its own channel via Block-Match). This is a deliberate departure from the literature's "no learned perceptual metric for web" gap.
3. **Structural similarity:** **TreeBLEU** (WebCode2M, WWW 2025) — fraction of 1-height DOM subtrees in candidate that match reference. Replaces the discarded DOM-IoU. Note: TreeBLEU does rely on DOM tags, but as a *structural* check it's a much weaker signal than as a *layout* metric, and is the established standard.
4. **Responsive fidelity:** score the page at 3 viewport widths sampled **continuously** within mobile/tablet/desktop bands (per revision R6). Aggregate via **harmonic mean** across viewports, not arithmetic mean — a categorical mobile failure must drag the score down.

**Reasoning:**
- The visual-grading research (`research/visual_grading_metrics.md`) is conclusive: SSIM/LPIPS are pixel-shift-sensitive in ways humans don't perceive (3–14% rank flips at 1–3 px shift). The whole field has moved to element matching + structural metrics + (newer work) VLM-as-judge.
- Block-Match is translation-tolerant by design: a section shifted vertically by 50px still matches under Hungarian assignment as long as bbox IoU > threshold.
- DreamSim covers what Block-Match cannot — overall *gestalt* of the design (whitespace, hierarchy, vibe). Using it for web is novel; using it text-masked is novel-er.
- TreeBLEU is structural rather than layout — replaces the brittle "major sections" idea with something measurable.

**Tradeoffs / alternatives considered:**
- **MLLM-as-judge (DesignBench / Web2Code path):** considered. Pros: tracks human judgment best, well-established by 2025. Cons: introduces a learned reward model that itself can be gamed, requires expensive judge model in the loop, slower, harder to RL against because the gradient passes through a stochastic VLM. **Decision: deferred to a later phase as a possible cross-check or held-out signal, not the primary reward.**
- **Pure literature replication (Design2Code's exact metric):** rejected — by 2026 the metric is showing its age (CLIP full-page degrades on long pages, no perceptual metric in the stack). Our DreamSim + masked-text component is a genuine improvement.

**Items requiring user confirmation:** weight assignment across (Block-Match, DreamSim, TreeBLEU, Responsive) is deferred to **R3** (human-preference calibration). Placeholder for v1 build: equal weights 0.25 / 0.25 / 0.25 / 0.25.

---

### R2. Add cross-page consistency reward (literature white space)
**Date:** 2026-05-21
**Supersedes:** ~~Decision 5's "pages graded independently and averaged"~~ — partially. Independent per-page scoring stays; we *add* a cross-page consistency term.

**Decision:** Final task reward = `mean(per-page-score) × (1 − λ · cross-page-variance)`, multiplicative. Cross-page consistency decomposed into:
- **Palette consistency** — EMD between extracted color histograms across all N page pairs.
- **Typography consistency** — distance over extracted (font-family, size, weight) tuples.
- **Spacing-token variance** — variance of computed CSS margin/padding/radius values, extracted Dembrandt-style.
- **Style-embedding consistency** — DreamSim pairwise across the N rendered pages, content regions masked.
- **Shared-header DOM identity** — TreeBLEU on a fixed selector (`header`, `nav`) across pages.

**Reasoning:**
- The cross-page research (`research/cross_page_consistency.md`) confirms **no published design-to-code benchmark grades multi-page coherence.** Our spec mandates 5+ pages — building a coherence reward is the most differentiated research contribution available to us.
- Multiplicative aggregation (not additive) is grounded in Trickle-down RLHF 2309.16155 and Intra-Trajectory Consistency 2506.09096 — additive lets the model trade off coherence for per-page polish; multiplicative does not.
- Every sub-component has direct published precedent in adjacent fields (image-gen story consistency, font-style embeddings, palette EMD).

**Tradeoffs / alternatives considered:**
- **Skip cross-page (Decision 5's original stance):** the simplest path. Rejected because (a) it leaves the strongest research-taste signal on the table, (b) 5+ pages is a hard requirement so this is intrinsic to the task definition, (c) the literature gap makes this an obvious contribution.
- **Cross-page as a separate dataset metric (not in the per-task reward):** considered. Rejected because the agent should be incentivized to produce coherent multi-page output during RL, not just at eval time.

**Open:** value of λ (start at 0.3 as a placeholder); whether to weight the five cross-page sub-channels equally or learn the weights with human-preference calibration.

---

### R3. Defer all scoring-weight selection to post-calibration
**Date:** 2026-05-21
**Supersedes:** ~~Decision 1's 0.35/0.25/0.15/0.10/0.15 weights~~. Reviewer was right — these were pulled from intuition.

**Decision:** All scoring weights (per-page component weights, viewport aggregation, cross-page λ) are placeholders until calibrated. Calibration procedure:
1. Generate ~150–200 (agent-output, reference) pairs spanning quality from "blank page" to "near-perfect."
2. Human-rank pairs (small set, ≤200, since we just need a target distribution).
3. Fit weights by maximizing **Kendall's tau** between composite score and human rank.
4. Report tau in the final write-up. If tau < 0.6 we have a grader problem.

**v1 placeholder weights** while building the pipeline: equal weights across all components. Calibrate before locking.

**Reasoning:**
- "The model will learn your grading logic, so if your grading is bad you're just introducing noise" — this is explicitly the bar the prompt set. Calibrating against human preference is the principled answer.
- Deferring weight selection lets us build the full pipeline without committing to a number we cannot defend.

---

### R4. Graded penalties for training, hard-zero for held-out eval only
**Date:** 2026-05-21
**Supersedes:** ~~Decision 4's universal hard-zero~~.
**Status: AWAITS USER CONFIRMATION** — reverses an earlier user-confirmed decision.

**Decision:** Two modes:
- **Training mode:** anti-cheat violations apply a multiplicative penalty in [0.1, 1.0] scaled by violation severity. A confused early-policy emitting `position: absolute` everywhere is penalized but not destroyed.
- **Held-out eval mode:** hard-zero on egregious violations (image-of-reference embedding, iframe-with-reference-content). Soft violations still graded.

**Reasoning:**
- The reviewer's argument is correct: at step 0 of RL, the policy is incompetent. Many violations will be incidental, not adversarial. A zero absorbing state gives no gradient toward "almost not cheating," and the variance kills PPO/GRPO learning for many steps.
- The original cleanness argument was about eval, not training — collapsing those modes was a mistake.

---

### R5. Multi-generator reference set (Claude + GPT + human seeds)
**Date:** 2026-05-21
**Supersedes:** ~~Decision 3's "Use Claude to generate"~~ — single-generator portion.
**Status: AWAITS USER CONFIRMATION**.

**Decision:**
- **Primary generators:** Claude + GPT-class (and Gemini if accessible). Multi-temperature mixing per DataDreamer.
- **Primitive seeding:** every generation prompt is conditioned on a tuple sampled from real design tokens — palette (Coolors/Adobe Color), font pairing (Google Fonts category × weight), spacing scale (Material/Carbon/Polaris), layout archetype (20+ curated genres beyond SaaS — newspaper, brutalist, government portal, doc site, dashboard, e-commerce PDP, etc.).
- **Verbalized Sampling** at generation time — request k=5 designs with probabilities per seed; take the lowest-probability viable one. Per arXiv 2510.01171: ~2–3× diversity gain at constant quality.
- **Critic-filter:** lightweight VLM judge scoring (a) deviation from SaaS-centroid, (b) primitive-fidelity, (c) visual quality. Reject and resample the top-3 most archetypal outputs.
- **Human-authored seeds (~5):** deliberately non-LLM-typical (brutalist, magazine, retro, asymmetric, dense data dashboard). Held out as validity check.
- **Diversity tracking:** **Vendi Score over CLIP embeddings** of screenshots as headline diversity metric. Cross-check against WebCode2M's token/tag/depth gap statistics.

**Reasoning:**
- Synthetic-only collapses (WebCode2M's 50×/6×/2× gap is the canonical evidence).
- Single-generator collapses doubly — eval set becomes a fixed point of the generator's stylistic mean.
- Primitive seeding is a **novel methodology** with no published academic precedent — also a defensible research contribution.

**Tradeoffs / alternatives considered:**
- **Single-generator with strong prompting:** rejected — the literature shows prompting alone is insufficient against typicality bias.
- **Crawl real sites for diversity:** rejected — explicit project constraint.

---

### R6. Anti-cheat coverage expansion + viewport defense overhaul
**Date:** 2026-05-21
**Supersedes:** ~~Decision 4's 7 attack vectors + ±20px viewport jitter~~.

**Decision:** Expanded coverage to 16 attack vectors:

*Already covered (revised):*
1. Image embedding (base64 / external URI) — extend filter to **all MIME types**, including `image/svg+xml` data URIs.
2. Absolute positioning — keep ≥80% threshold (raised from 50%) so incidental use isn't penalized.
3. Invisible text overlay — OCR-vs-DOM cross-check.
4. Single-viewport overfitting — replaced with **continuous viewport-width sampling** in [320, 1600], one width per band, per evaluation. Agent cannot hard-code breakpoints.
5. Test-script tampering — Harbor verifier isolation + checksums.
6. Training-data retrieval — unique business names, copy, palettes; framework-signature check.
7. Minimal-viable-render — content-density floor that **scales with reference complexity**, not fixed.

*New (from review):*
8. `<iframe srcdoc>` / `<object>` / `<embed>` — reject in any output.
9. Inline SVG reproductions — flag single `<svg>` > 50 KB or covering > 70 % of viewport.
10. CSS `content: url(...)` in pseudo-elements — full stylesheet parse.
11. CSS `@import url("data:...")` — full stylesheet parse.
12. Render-time race conditions — grader uses `networkidle0` + `domcontentloaded` + 1 s settle + **post-screenshot mutation re-check** at +200 ms (flag if pixels diverge > ε).
13. Print-vs-screen media split — force `screen` media emulation; spot-check media queries.
14. Font-loading races — block on `document.fonts.ready`; **disable network fonts entirely**, pinned local font stack only.
15. OCR adversarial text / Unicode lookalikes — NFKC-normalize; `confusable-homoglyphs` check.
16. Animation timing — covered by mutation re-check (12) at +200 ms.

**Network isolation:**
- **v1:** iptables egress allowlist for `api.anthropic.com` (refreshed via DNS at container start); **explicitly disable Claude Code's WebSearch, WebFetch, and any other outbound tool** in Claude Code settings.
- **v2 (planned):** egress proxy (envoy or mitmproxy) with SNI pinning; enumerate every endpoint Claude Code touches (statsig, sentry, auth) and whitelist by SNI. Treat `api.anthropic.com` as a potential covert channel.

**Determinism guardrails:**
- Pin Chromium version in the Dockerfile.
- Pin font set (no network fonts).
- Document grader determinism budget — re-running the same output across versions should yield score ± 0.005.

---

### R8. Logging surface locked for Phase 0/1
**Date:** 2026-05-21
**Decision:** Every trial produces this exact directory tree under `/logs/verifier/`:

```
/logs/verifier/
├── reward.txt                          # headline scalar (Harbor convention)
├── run_metadata.json                   # reproducibility: Chromium version, grader hash,
│                                       #   reference hash, task digest, model snapshot,
│                                       #   viewport widths used, random seed
├── trajectory.jsonl                    # Harbor's Claude Code trajectory (every tool call)
├── agent_output/                       # snapshot of /app/ at agent stop
├── agent_summary.json                  # tool-call histogram, final message,
│                                       #   token usage (in/out/cache), wall-clock timing
├── network/
│   ├── dropped.log                     # iptables drops (R7)
│   └── dns_queries.log                 # in-container resolver log (if cheap to add)
├── render/
│   ├── {page}.{viewport}.png           # screenshot of agent's output
│   ├── {page}.{viewport}.console.log   # headless Chromium console (JS errors, broken-render signal)
│   ├── {page}.{viewport}.network.json  # render-time fetches by the agent's page
│   └── {page}.{viewport}.styles.json   # getComputedStyle dump (input to cross-page consistency R2)
└── grading/
    ├── subscores.json                  # per-component × per-page × per-viewport
    ├── diffs/{page}.{viewport}.png     # side-by-side reference vs agent
    └── anticheat.json                  # which checks fired and their thresholds
```

**Reasoning:**
- Four observability questions a reviewer will ask after a trial: (a) what did the agent do? (b) what did it produce? (c) how was it graded? (d) was the run reproducible? This layout answers each in a dedicated subtree.
- Render-time Chromium logs (console + network) are the **broken-render detector** we agreed to in R1 — JS errors at render time are categorical failures, not "uniformly mediocre" scoring artifacts.
- Render-time network log is a second-line anti-cheat: catches external fetches by the *rendered page* (e.g., Tailwind from CDN) even when the *agent container* egress is allowlisted differently.
- Reproducibility metadata is mandatory for the final report — without grader-hash and reference-hash, "re-run scored differently" becomes unfixable.

**Tradeoffs / alternatives considered:**
- **Minimal logs ("just reward.txt"):** rejected — we'd be blind to model behavior, and the trial's main research value is *understanding what the model struggled with*, not the scalar.
- **Maximal logs (full `/proc` snapshots, per-token logprobs):** rejected — too much noise; Claude Code doesn't expose logprobs anyway.
- **Computed-style dump only when needed:** rejected — generating it post-hoc requires re-rendering, which is nondeterministic; capture once at trial time.

---

### R7. Network egress allowlist baked into Dockerfile from Phase 0
**Date:** 2026-05-21
**Refines:** R6's "network isolation" section. R6 left the impression this was a Phase 3 add; user-confirmed to bake it in from the very first task scaffold.

**Decision:** Every agent-container Dockerfile, starting with the Phase 0 smoke-test task, includes:

1. **Default-deny egress.** `iptables` (or `nftables`) `OUTPUT` policy set to `DROP` at container start, via an entrypoint script.
2. **Allowlist by hostname, resolved at container start.** The entrypoint resolves the allowed hosts via DNS once and `iptables -A OUTPUT -d <ip> -j ACCEPT`s each. Allowed set for v1:
   - `api.anthropic.com` (Claude Code → model API)
   - `statsig.anthropic.com` and `sentry.io` (Claude Code telemetry — confirm exact set during Phase 0; deny by default and re-add only what Claude Code actually fails without)
   - DNS resolver (`53/udp` to the container's resolver)
   - Loopback (`127.0.0.0/8`)
3. **Explicit denials** of everything else, including CDNs (`cdn.jsdelivr.net`, `fonts.googleapis.com`, `unpkg.com`, `cdnjs.cloudflare.com`), image hosts, scrape targets, and the public internet at large.
4. **Egress denial logging.** Dropped outbound packets are logged to `/var/log/iptables-drops.log` and copied to `/logs/verifier/network/dropped.log` by the verifier. Lets us see what the agent *tried* to fetch — high-signal for catching cheat attempts.
5. **Claude Code tool disable.** In Claude Code's settings within the container, `WebSearch` and `WebFetch` tools are explicitly disabled. Defense in depth: even if the network allowlist had a hole, the agent can't reach for these.

**Reasoning:**
- Doing this from Phase 0 means every task we ever build has the same security posture — no retrofitting, no "I'll add it later" debt.
- The drop-log is independently valuable as a *signal* — if the agent learns to try `curl jsdelivr.net` for Tailwind, we'll see it in trial logs and can decide whether to flag it as cheating or just an artifact of the model's training.
- Pinned-by-resolved-IP iptables is good-enough v1 (reviewer's preferred SNI proxy remains the v2 plan in R6).

**Tradeoffs / alternatives considered:**
- **Deferring to Phase 3 (original plan):** rejected — every task built before Phase 3 would need a Dockerfile rewrite.
- **No restrictions, trust the model:** rejected — agent could fetch the reference page from a CDN, hotlink images, or `npm install` arbitrary packages that simplify the task in unintended ways. Goodhart-grade exploit surface.
- **Allow all internet, post-hoc detect cheating:** rejected — false negatives are easy and we'd be detecting after the trial completes rather than preventing.

**Bare-bones plan revision:** the egress-allowlist work moves from Phase 3 to Phase 0/1. Phase 3's "verify isolation" step keeps the probe tests (curl/find for `reward.txt`) but treats them as *confirmation*, not implementation.

---

### R9. iptables blocked on Modal/gVisor — switch to userspace HTTPS-proxy for egress logging
**Date:** 2026-05-21
**Supersedes:** R7's iptables-in-Dockerfile mechanism. The *intent* of R7 (enumerate, log, and eventually allowlist egress) is preserved; only the *mechanism* changes.

**Decision:** Use a userspace logging proxy inside the agent container, route all HTTP(S) traffic through it via `HTTPS_PROXY`/`HTTP_PROXY` env vars. Implementation lives at `tasks/000-smoke/environment/proxy.py` (~120 lines of asyncio Python).

**Reasoning:**
- **Modal sandboxes run on gVisor**, Google's userspace kernel for sandboxed containers. Verified by `dmesg` showing `Starting gVisor...` and `iptables: Failed to initialize nft: Protocol not supported`.
- gVisor does not implement iptables/nftables and does not grant `NET_ADMIN`/`NET_RAW`. **No kernel-level egress capture mechanism works on Modal.**
- Userspace HTTPS proxy with `CONNECT` parsing gives us destination host:port for every TLS connection without TLS interception (we just forward bytes after logging the `CONNECT` line).
- Same mechanism extends naturally to **enforcement**: refusing non-allowlisted hosts at the proxy is one `if` statement away.
- Catches all the threats R7 was designed against: CDN hotlinking, image hotlinking, npm registry pulls, reference-page lookups — anything using a hostname.

**Baseline observed egress for a trivial Claude Code trial (smoke-claude-proxy):**
- `downloads.claude.ai:443` (×7) — Claude Code CLI bootstrap
- `api.anthropic.com:443` (×3) — model API
- `archive.ubuntu.com:80` (×2), `security.ubuntu.com:80` (×1) — **HTTP, not HTTPS** — Harbor installs apt deps at trial start, not just at image build
- `claude.ai:443` (×1) — initial handshake
- **No** statsig, sentry, or telemetry hosts observed in this run

**Implications for the eventual allowlist:**
- Must include `*.anthropic.com`, `downloads.claude.ai`, `claude.ai`
- Must include Ubuntu mirrors OR we move all apt installs to image-build time and reject HTTP at trial-start
- Telemetry hosts not observed in trivial trials but may appear in longer ones — monitor

**Tradeoffs / alternatives considered:**
- **iptables** (original R7): infeasible on Modal/gVisor. Could be made to work by switching to `--env docker` for observability runs, but that splits the runtime story.
- **Connection-snapshot polling** (`ss -tn` every 500ms): cheap but misses short-lived connections and only sees established sockets.
- **mitmproxy with installed CA cert**: more powerful but heavier, and TLS interception isn't needed for hostname observability.

**Caveat:** the proxy works because Claude Code's runtime (Python httpx, npm fetch, apt) all respect `HTTPS_PROXY` env vars. If a future tool ignores the env var and connects to a hostname/IP directly via raw sockets, we won't see it. Mitigation: pair with `/etc/resolv.conf` override to a logging DNS resolver — adds DNS lookup as a second observation channel. Deferred to Phase 1 if needed.

---

## Phase 2 outcomes (2026-05-21)

### Three sanity runs on Modal, task `tasks/002-lumen-multipage` (5-page Lumen site, 3 viewports = 15 reference PNGs)

| Agent       | Reward | Wall clock | Notes |
|-------------|--------|------------|-------|
| oracle      | 1.000  | 3m25s      | All 5 pages × 3 viewports = perfect 1.0. Base64-tarball solve.sh works; multi-page rendering + harmonic mean + all new anti-cheat layers pass clean. |
| nop         | 0.000  | 2m32s      | 15/15 missing screenshots; all 5 pages harmonic mean = 0.0 (not the 0.003 EPS floor — confirms missing-page fix from review 003). |
| claude-code | **0.686** | 10m8s   | No anti-cheat violations, all 5 pages produced, every render padded. Meaningful continuous signal in the middle of the distinguishable range. |

### Key empirical findings from Claude's trial

**Per-page-harmonic means:**

| Page      | Mobile | Tablet | Desktop | Harmonic |
|-----------|--------|--------|---------|----------|
| pricing   | 0.706  | 0.784  | 0.791   | **0.758** (best) |
| index     | 0.631  | 0.734  | 0.733   | 0.696    |
| changelog | 0.596  | 0.714  | 0.774   | 0.687    |
| features  | 0.508  | 0.723  | 0.794   | 0.651    |
| docs      | 0.567  | 0.694  | 0.674   | **0.640** (worst) |

**Mobile is Claude's consistent weak spot.** Every page scores lowest on mobile. Features mobile at 0.51 — the 2-column feature-row layout doesn't collapse correctly. **This is exactly the signal the harmonic mean was designed to surface** (R6 decision validated empirically): mobile failure pulls the page score down rather than getting averaged-out by good desktop. With a flat arithmetic mean across viewports, features would score 0.68 instead of 0.65 — masking the actual responsive-design failure.

**Claude consistently undershoots page height.** Almost every render is shorter than the reference (e.g. index desktop: ref 1038px, cand 900px). Padded regions cost 5–15% SSIM. Suggests Claude's CSS produces tighter vertical spacing than our reference's hand-tuned values.

**Most-complex page = lowest score.** Docs (sidebar + content + code blocks + multiple heading levels) scored worst at 0.64. Pricing (3 simple tier cards) scored best at 0.76. The grader's per-page ranking aligns with intuitive task difficulty.

### Anti-cheat: zero false positives, zero violations
All 15 page×viewport candidate renders. None tripped:
- Image-byte-copy detection (no `/reference/*.png` files in `/app/`)
- Off-origin requests during candidate render (proxy log clean — Claude didn't hotlink anything)
- Static HTML/CSS scan (no data:image URIs, no iframes)

### Grader signal range across Phase 2 (n=1)
- Perfect copy (oracle) → 1.000
- Claude's faithful but imperfect replica → 0.686
- All-missing → 0.000

For RL training this is a useful three-band signal. For real evaluation we'd want k≥3 trials per agent (the Phase 1 finding) to characterize variance; same finding likely transfers but isn't measured here.

### Phase 2 grader changes validated
All four fixes from review 003 survived a real Modal run:
- `dataclasses.asdict` (clean nested JSON) ✓
- Missing-page hard-zero (not EPS-floored 0.003) ✓
- Catastrophic-dim threshold (never triggered — would only kick in for >50% size delta) ✓
- VIEWPORTS sanity check (clean — no width warnings) ✓
- Image-byte-copy anti-cheat (no violations triggered, but probe-tested locally) ✓
- Off-origin penalty (zero off-origin requests by Claude — proxy worked) ✓

### Phase 2 checkpoint: the three things this phase validated

Phase 2 is the project's first end-to-end real RL environment. Three distinct pillars had to hold for it to count as working — calling them out so future readers can see what's been demonstrated vs what's still on faith:

#### 1. Website creation pipeline ✅
- Reference site (5 hand-written HTMLs sharing one CSS file) renders identically across reference-generation runs and verifier runs on Modal — proved by oracle scoring 1.000 across all 15 page-viewport pairs.
- `pipeline/render_on_modal.py::batch` produces 15 PNGs in ~30s, with the same Chromium 131 used by the verifier.
- `solution/solve.sh` extracting a base64-encoded tarball works inside Harbor's oracle invocation surface — solve.sh is 122 lines (vs ~800 if we'd heredoc'd 6 files).
- No cross-OS render drift visible (Modal-generated reference + Modal-rendered candidate match exactly when HTML is identical).

#### 2. Anti-cheat ✅
- **Probe-tested locally:** `cp /reference/index.desktop.png /app/index.png` + `<img src="index.png">` correctly trips `reference_image_copy` → 0.1× multiplier → effective reward of 0.0 on what would otherwise look like a perfect-pixel cheat.
- **No false positives on a real agent.** Claude's actual Phase 2 output (5 HTMLs + 1 CSS, ~900 lines) tripped zero anti-cheat checks. No bogus iframe matches, no spurious data-URI flags, no off-origin requests during render.
- **Three independent check layers** now live in `anticheat.py`:
  - `scan_html_css` — static regex scan (data:image URIs, iframe tags)
  - `detect_image_copies` — file-byte equality vs reference PNGs
  - `detect_off_origin` — external resource fetches at render time
- Combined via `run_all_checks(...) → AnticheatResult` so the grader stays orchestration-only.

#### 3. Grader (signal) ✅
- **Continuous and ranked.** Oracle 1.000 > Claude 0.686 > Nop 0.000. The middle band is non-trivial and meaningful.
- **Diagnostic per page-viewport.** Per-page harmonic mean ranks the 5 pages by difficulty in a sensible order (pricing 0.76 > index 0.70 > changelog 0.69 > features 0.65 > docs 0.64), and the per-viewport breakdown reveals mobile as Claude's consistent weak spot.
- **Aggregation choice empirically validated.** Harmonic mean across viewports would punish a 0.05/1.0/1.0 split as 0.137, vs arithmetic mean's 0.683 — exactly the responsive-design signal RL needs.
- All review-003 fixes (image-copy detection, missing-page hard-zero, catastrophic-dim threshold, VIEWPORTS sanity check, off-origin penalty, dataclasses.asdict, fonts.ready arrow form) survived a real Modal trial.

### Code refactor at end of Phase 2 (housekeeping, not a behavior change)
Moved all anti-cheat code from `grade.py` into `anticheat.py` (image-copy detection and off-origin detection, previously inline in the grader). Same behavior, cleaner separation: `metrics.py` = scoring math, `anticheat.py` = all cheat detection, `grade.py` = orchestration only. Verified pre/post by re-running both the legit case (0.866) and the cheat probe (0.087 with 0.1× multiplier) — identical results to pre-refactor.

### Phase 2 cost
- Oracle: ~$0 compute, ~$0.05 Modal time
- Nop: ~$0 + ~$0.05
- Claude: 10m08s + Claude API tokens (5 pages × ~200 lines + sustained context with 15 PNGs ≈ a few dollars in API time)

---

## Phase 1 outcomes (2026-05-21)

### Three sanity runs on Modal, task `tasks/001-landing` (single page, SaaS landing, 1440×998 ref)

| Agent       | Reward | Wall clock | Notes                                                                       |
|-------------|--------|------------|-----------------------------------------------------------------------------|
| oracle      | 1.000  | 1m53s      | SSIM exactly 1.0. Modal-rendered reference matches verifier render byte-for-byte. |
| nop         | 0.000  | 2m21s      | Missing-page fallback (no index.html written).                              |
| claude-code | **0.0 → 0.83 with fix** | 4m59s | Visually faithful replica. Initial 0.0 caused by 16px height mismatch tripping our too-strict dim-mismatch rule. |

**Distinguishable signal bands** observed on this task:
- Perfect copy → 1.000
- Claude's faithful replica → ~0.83 (with padding fix)
- Blank but present → ~0.16
- Cheat data-URI on blank → ~0.016
- Missing entirely → 0.000

### Key Phase 1 finding: hard-fail-on-dim-mismatch was too strict
A 16px (1.6%) height difference between Claude's render and reference triggered our `dim_mismatch=True → score=0.0` rule. Claude's HTML was almost identical visually; the height difference came from padding/margin variations in the hero or features section. Killing the entire score over 16px gave no useful signal.

**Fix decided:** pad shorter image to taller image's height with black before SSIM. Symmetric: penalizes both directions (too-tall and too-short) naturally via the padded regions not matching content. Local re-grade of Claude's existing Modal-rendered PNG with this fix yielded SSIM 0.83 (cropping to shorter dim gave 0.84 — within 0.01 of padding; padding chosen for symmetry).

Width mismatch still fails loud — width is fixed at 1440 by `render.py`, so any width drift would be a real bug.

### Claude's behavior observation (one-trial sample, n=1)
- 5 Bash calls, 3 Reads, 2 Writes — disciplined, no exploration outside `/app/` and `/reference/`
- Explicitly looked for a Chromium binary on the agent container (`which chromium chromium-browser google-chrome chrome`) — didn't find one (we deliberately don't install it in the agent image)
- Read PNG dimensions twice via different methods (PIL + raw struct unpack) — useful behavioral signal for "model is checking inputs"
- Did NOT attempt to read `/entrypoint.sh`, `/opt/proxy.py`, `/logs/agent/network/`, or `/tests/` — clean trial

### Hardening backlog (defer, not blocking Phase 2)
User-confirmed to defer. Capturing here so it's not lost:
- `/entrypoint.sh` and `/opt/proxy.py` are world-readable in the agent container. Move to root-owned, mode 0700, run agent as non-root user.
- `/logs/agent/network/egress.jsonl` is the agent's own egress log; agent could `tail` it. `chmod 700 /logs/agent/network` after proxy starts.
- Env vars (HTTPS_PROXY, ANTHROPIC_API_KEY) visible via `printenv` — Harbor's `docker exec` invocation surface is the place to scrub. Worth investigating Harbor's hooks.
- All of the above are observability leaks, not answer-leaks. The reference HTML, grader code, and reward.txt remain structurally inaccessible (verifier-only, never enter agent container).

### Re-run with patched grader — Claude variance finding (n=2)
Re-ran Claude on Modal with the height-padding fix in place to get a clean on-disk artifact (the first trial's `reward.txt` showed 0.0 because the old grader hard-failed on dim mismatch).

| Trial | Modal reward | Candidate size | Architectural choices |
|-------|--------------|----------------|------------------------|
| 1 (first trial, re-graded locally with fix) | 0.828 | 1440×1014 | External CSS file, lowercase `<!doctype>`, smaller container padding |
| 2 (fresh Modal run with new grader) | **0.803** | 1440×1024 | Inlined `<style>` block, uppercase `<DOCTYPE>`, 60px container padding |

**Spread: 0.025 SSIM across two trials.** The grader is deterministic (same PNG → same number), so all of this spread is Claude's run-to-run variance in *design choices*, not measurement noise. The diff between the two outputs shows different architectural decisions (split vs single file, padding values, color names) — not trivial whitespace.

**Implication for eval design:** a single Claude trial does NOT characterize "Claude's ability on a task." Need **k≥3 trials per task** for any reliable signal, and the task spec explicitly calls for k=10 in the final deliverable ("running Claude Code with Opus 4.6 10 times on the task, how well does your grader do at scoring the results?"). The k=10 spec is now empirically justified — we'd expect ~±0.05 spread on n=10, which is enough that an SSIM range of 0.05 between two systems likely isn't a real difference.

### Documentation: Modal as the source of truth for reference rendering
Local-mac Playwright ships Chromium 148 by default; pinned `playwright==1.49.0` (in verifier) ships Chromium 131. To eliminate this drift, all reference PNGs are generated via `pipeline/render_on_modal.py` (Modal job using same image as verifier). The `pipeline/build-reference.sh` Docker-local script is preserved but broken on Apple Silicon — Chromium crashes under QEMU x86_64 emulation. Use Modal for any reference rendering.

---

## Phase 0 outcomes (2026-05-21)

### Phase 0a — Modal + Harbor handshake: **PASSED**
- 3/3 sanity runs on Modal: oracle → 1.0 (47s), nop → 0.0 (15s), Claude Code Opus 4.7 → 1.0 (1m02s).
- Harbor's built-in adapters worked out of the box: `--agent claude-code -m claude-opus-4-7 --env modal`.
- Cold-start time on Modal: ~45s build, ~15s execution. Acceptable for iteration.

### Phase 0b — Logging shakedown: **PASSED**
Harbor produces this artifact tree per trial (covers most of R8 for free):
```
jobs/<job>/<trial>/
├── agent/
│   ├── trajectory.json                # Harbor ATIF-v1.2 normalized (every tool call + metrics)
│   ├── claude-code.txt                # Claude Code raw NDJSON output
│   └── sessions/projects/-app/*.jsonl # Claude Code's native session log
├── verifier/{reward.txt, result.txt, test-stdout.txt}
├── trial.log, config.json, result.json
└── artifacts/manifest.json
```

**Already captured for free (R8 items):**
- Tool-call sequence with arguments and results (trajectory.json)
- Token usage: prompt, completion, cache_creation, cache_read (per step + aggregated)
- Wall-clock timing: `duration_ms`, `duration_api_ms`, `ttft_ms` per turn
- Cost in USD per trial
- Final assistant message
- Permission denials log (`permission_denials: []`)
- Agent version, model snapshot
- Task checksum (`task_checksum`), full agent + environment config (in result.json)

**Still to add ourselves (in Phase 1 `test.sh`):**
- `agent_output/` — snapshot of `/app/` at agent stop (Harbor doesn't snapshot by default)
- `render/` — Chromium screenshots, console.log, network.json, computed styles
- `grading/` — subscores.json, diffs, anticheat.json
- `run_metadata.json` — Chromium version, grader git hash, viewport widths sampled, random seed
- `network/dropped.log` — once iptables is added in Phase 1

### Critical observation (security implication)
Claude Code's default tool surface in the agent container includes `WebSearch`, `WebFetch`, and a long list of others (visible in the init event of `agent/claude-code.txt`). For Phase 1 onward, these must be explicitly disabled via Claude Code config — `bypassPermissions` mode is on by default. R7's network allowlist is necessary but not sufficient; we need both network *and* tool-level denial.

### Plan amendments from Phase 0
- **R7 nuance:** iptables-in-Dockerfile defers to Phase 1 (not absolute Phase 0). Rationale: testing iptables and Modal sandbox NET_ADMIN capability together would conflate failure modes. Validated the loop bare first.
- No other plan changes — proceed to Phase 1 as scoped.

---

### R10. Proxy egress blocking considered but deferred
**Date:** 2026-05-21

**Decision:** The userspace proxy (`environment/proxy.py`) remains logging-only. We considered converting it to a blocking proxy (deny-list or allow-list) but chose not to for now.

**Reasoning:**
- The proxy currently logs all outgoing connections to `egress.jsonl`, which feeds the off-origin anticheat check at render time.
- A blocking proxy would prevent the agent from fetching external resources during execution (not just render), closing the gap where a model could download an image during its build step and serve it locally.
- However, the new `detect_raster_images` anticheat check catches saved image files regardless of how they were obtained, reducing the urgency of network-level blocking.
- Blocking introduces risk of breaking legitimate Claude Code operation (API calls, telemetry) and requires careful allowlist maintenance.
- If needed, converting the proxy to a blocker is a one-`if`-statement change in `proxy.py`.

---

### R11. VLM-as-judge demoted to audit-only weight 0.0 after calibration
**Date:** 2026-05-21

**Decision:** `vlm_judge` (Claude Sonnet 4.6 scoring rendered candidate vs reference PNG pair) stays implemented and runs on every grade, but its weight in `METRIC_WEIGHTS` is set to 0.0. It's logged in subscores.json for interpretation / debugging but does not contribute to the composite reward. The 4 structured metrics (SSIM, Block-Match, OKLab Palette, Typography) carry the score.

**What we measured.** Calibrated against oracle / Claude / nop with VLM weight at 0.20 (equal with other metrics):

| Candidate | VLM mean | VLM range | Other-metric composite |
|---|---|---|---|
| Oracle (identical) | 0.945 | 0.90 – 0.97 | ~0.93 |
| Claude v5 | 0.901 | 0.85 – 0.95 | ~0.55 structured |
| Nop (empty HTML) | 0.000 | 0.00 – 0.00 | 0.002 |

**Why demote:**
- **Doesn't discriminate in the band we care about.** Oracle-vs-Claude VLM gap = 0.044; Oracle-vs-Claude Block-Match gap = 0.513. VLM is ~10× worse at separating "great" from "mediocre."
- **Within-class variance exceeds between-class variance.** Claude's VLM spread is 0.10; the Claude-vs-Oracle gap is 0.044. A lucky Claude page can outscore an unlucky oracle page on VLM alone.
- **Anchors conservatively even on identical renders.** Oracle never exceeds 0.97 despite being pixel-identical and the prompt explicitly defining 1.0 = "visually identical."
- **Catastrophic-failure detection (the one thing VLM does perfectly: nop → 0) is already redundant** with anti-cheat + render-sanity floor.
- **Effect on composite at weight 0.20:** Claude was lifted from ~0.55 to 0.62, but Oracle was lifted equally — preserving ranking but compressing dynamic range without adding information.

**What VLM IS still good for:**
- The `reason` text field is qualitatively informative ("the candidate uses similar dark-mode styling but the hero layout differs").
- Useful as a **diagnostic** when scores look surprising.
- Catastrophic-failure detection works perfectly (nop = 0).
- May become useful with a better-calibrated prompt (anchors, examples, rubric) — left as future work.

**How to apply.** Don't trust VLM-as-judge as a graded metric on design-replication tasks without empirical calibration against oracle/nop on YOUR specific task. The Web2Code/DesignBench literature reports VLM correlates with humans on free-form design judgment; that signal does NOT automatically transfer to "how close is candidate to *this specific reference*." The discriminating range you actually get is what matters, not literature priors.

**Concrete file change:**
```python
# pipeline/grader/metrics.py
METRIC_WEIGHTS = {
    "ssim": 0.25, "block_match": 0.25,
    "palette": 0.25, "typography": 0.25,
    "vlm_judge": 0.0,
}
```

VLM still runs (the 15-pair parallel call), result still lands in subscores.json — just weighted 0.

---

### R12. Drop multi-viewport from the smoke wave — desktop-only references and grading
**Date:** 2026-05-21

**Decision:** Both the eval-generation pipeline and the grader render at a single viewport — desktop, 1440×900 — for the smoke wave. Mobile (375×800) and tablet (768×1024) are removed from `cfg.viewports` and from `pipeline/grader/grade.py:VIEWPORTS`. Responsive-design constraints are stripped from the library and per-page prompts. Multi-viewport is deferred to pilot.

Both reference and grader render with `full_page=True` (one PNG per page, 1440×scroll_height). SUT submissions are rendered identically, so PNG dimensions match; SSIM's both-dim padding handles any residual height drift.

**What we measured.** Across two Modal runs (v2 = `full_page=True`, v3 = `full_page=False` + library-retry-loop + per-page-retry-loop with up to 2 retries on overflow):

| Run | Sites | Pages with mobile overflow at retry exhaustion | Retry recovery rate |
|---|---|---|---|
| v2 | 5 | 7 / 24 pages (29%) | ~22% of failing pages converged |
| v3 | 5 | 8 / 25 pages (32%) | ~70% (better libraries, but tail of hard cases unchanged) |

In v3, three sites had mobile overflow on ≥3 of 5 pages despite the library smoke-validator and per-page retry feedback. The unconverged pages overflow by 30–760px at mobile; the failure mode is structural (wide tables, multi-column dashboards) and the LLM cannot patch it via per-page CSS overrides when the underlying primitives are fixed-width.

**Why drop multi-viewport (gradient-inversion argument):**

The grader uses `full_page=False` viewport-clipping (R12 prerequisite, also locked in this round). At mobile, a 600px-wide reference layout produces a 375px PNG showing only the leftmost 375px of the layout — half-cut elements, hidden right column. A *properly-responsive* SUT renders a clean 375px-wide layout that does NOT match the reference's cropped appearance. SSIM penalises the better-designed candidate. A worse SUT that also overflows to 600px happens to match the cropped reference and scores higher.

The metric's gradient therefore points the wrong way: more skilled agents get lower scores on the very signal we'd want to test (responsive design). Keeping multi-viewport with broken-responsive references gives an **anti-signal** at exactly the dimension we'd intended to measure.

**Why not just keep the retry loops longer.**
- ~30% of pages exhaust retries today; bumping `MAX_VALIDATION_RETRIES` from 2 to 5 might cut that to ~10–15% but ~3 × cost per affected page (~$1/site additional API spend) and a tail of pages still broken.
- The structural overflows (wide tables in dashboard archetypes) are inherent to Sonnet's design choices, not a feedback-channel limitation.
- Time/cost burned on an ambiguous signal isn't earned-back.

**Why not go to `full_page=True` plus large viewport.**
- Would produce 1440×5000+ PNGs and re-introduce the page-length-mismatch problem (SUT producing a shorter page → blank rows in reference padding).
- `full_page=False` is the cleaner contract for a smoke wave.

**Trade-offs accepted.**
- The eval no longer measures responsive design at all. The capability *exists in the model* but isn't graded. We lose one signal axis; the remaining axes (layout, palette, typography, structural fidelity, brand discipline) become higher-resolution.
- Some archetypes that are naturally multi-viewport (e.g., e-commerce admin dashboards) get scored only at their primary form factor. Acceptable for smoke; revisit in pilot.

**How to apply.** In pilot, multi-viewport can come back if the reference generator is replaced (hand-templated `styles.css`, or a model with stronger responsive output) OR if the grading is restructured to compare layout *primitives* rather than pixel screenshots at small viewports. Until then, never re-enable mobile/tablet in `VIEWPORTS` without also confirming the reference renderer reliably produces responsive output — broken-responsive references actively corrupt the RL signal.

**Concrete file changes:**
```python
# pipeline/eval_gen/config.py
viewports = {"desktop": (1440, 900)}

# pipeline/grader/grade.py
VIEWPORTS = {"desktop": (1440, 900)}

# pipeline/eval_gen/generator/library.py, generator/pages.py — strip responsive
# language (no min-width discussion, no @media-collapse instructions, no mobile/
# tablet viewport mentions in system prompts).
```

The per-page and library overflow checks are kept in `render_validate.py` (now they only fire at desktop, which is rarely violated — desktop overflow has been seen exactly once in v3 at 1453px on the deploys page). They're effectively a cheap render-sanity gate now, not a responsive-design gate.

---

## Items requiring user confirmation (carry-forward)

These reverse or extend earlier user-confirmed decisions; collecting them here so they're not lost:

1. **R4: Graded penalties for training, hard-zero for held-out eval only.** Reverses the prior universal hard-zero.
2. **R1 / R5: Switch perceptual metric from LPIPS → DreamSim (text-masked, tiled).** Reverses the prior LPIPS confirmation.
3. **R3: Defer scoring weights to human-preference calibration.** Placeholder equal-weights for v1.
4. **R5: Multi-generator references (Claude + GPT + human seeds) + primitive seeding + Verbalized Sampling + critic-filter.**
5. **R2: Add cross-page consistency reward, aggregated multiplicatively.** Adds scope to Decision 5; the per-page-independent stance is partially reversed.

---

## Phase 2 / v7 observations (2026-05-22)

Findings worth surfacing in the report from the 10×5 v7 trial fleet:

1. **Palette weakness on specific color families.** Claude reliably under-scores on certain palettes — dark-themed pages with cyan/teal accents and pages whose dominant background is a desaturated near-black (e.g. `#0d1117` cyan-tinted vs `#0a1020` navy) consistently show large hue deltas in the palette metric. The agent tends to drift toward "generic dark blue" regardless of the reference's actual tint. Suggests the agent samples color *category* (dark / light / accent) but not the precise hue.

2. **Numeric fidelity is poor.** Across financial dashboards, KPI cards, status counters, and tabular data, the agent rarely transcribes numbers exactly from the reference screenshots. It tends to invent plausible-looking values that match the visual scale but not the literal digits (e.g. "$2,847" in ref → "$2,500" in candidate). Text metric catches some of this; chart-data fabrication is what VLM judge is supposed to catch.

3. **Non-responsive output / inflated widths.** Inspecting the v7 candidate PNGs, the agent often produces pages whose rendered width exceeds the target viewport, especially at tablet (768) and mobile (375). Desktop, tablet, and mobile renders look nearly identical — the agent doesn't actually adapt the layout per viewport, it just lets the desktop design overflow horizontally or get cropped. The `overflow` metric only partially catches this; we should add an explicit responsiveness penalty that compares rendered widths across viewports (or pixel-correlates the three renders against each other — high correlation = no adaptation = penalised).

4. **`block_match` saturated against the `MAX_BLOCKS = 400` cap.** Every v7 page has >400 DOM elements; both ref and candidate were being clipped to exactly 400 → Hungarian forced into 400 matches → many forced pairings of nested wrapper `<div>`s with low IoU → raw mean-IoU pinned ~0.15, sqrt-rescaled score pinned at ~0.4 across all tasks. Pages with <400 elements (security/support: ~250) scored visibly higher (~0.46), confirming saturation. Lowered to `MAX_BLOCKS = 100` (top-K by area): per-(page,vp) variance ~doubled (stdev 0.04 → 0.06, range 0.34–0.65) but cross-task spread stayed tight (stdev 0.034) because bbox-IoU is fundamentally a low-discrimination metric — a 20–40px shift on a matched block yields IoU ≈ 0.3–0.5 even on visually-correct pages. For real layout discrimination, a non-IoU formulation (grid-cell occupancy, or match-or-miss thresholding at IoU > 0.5) would be needed. Leaving block_match at k=100 for now.

5. **Per-test eval variability is narrow, two features carry the discrimination.** Best-of-5 reward across 10 v7 tasks: range 0.48–0.64, stdev 0.053, CV ~9%. Per-feature variance is bimodal: palette (stdev 0.157, range 0.55) and text (stdev 0.125, range 0.36) do almost all the discriminating; block_match (stdev 0.025), ssim (0.047) are nearly flat. So the eval set is good at telling Claude's *known weaknesses* (color identity, numbers/text fidelity) apart, weak at separating overall task difficulty. For benchmarking another agent, mix easy + hard tasks deliberately to stretch the score axis.

6. **`overflow` metric measures the wrong width.** It reads `document.documentElement.scrollWidth` from the DOM dump, which can be much smaller than the actual rendered PNG width (e.g., a page that lays out 574px wide at mobile shows scrollWidth=398 because `overflow:hidden` on `<body>` clips it). Two failure modes: (a) PNG > scrollWidth → metric under-penalises real overflow, (b) `overflow:hidden` on a non-responsive layout → scrollWidth == viewport → metric scores 1.0 while the page still looks like desktop crammed into mobile. Fix: use `overflow_ratio = max(cand_scrollWidth, cand_png_width) / viewport`. Even better: add a "responsiveness" metric that compares cand_desktop vs cand_mobile pixel-correlation — high correlation = agent never adapted = explicit penalty.

7. **Anticheat × structured-reward coupling makes the eval reward bimodal, hurting RL training shape.** Aggregate reward distribution across 50 trials is sharply bimodal: ~22% near 0.0–0.07 and 78% in the 0.40–0.65 band, with an empty dead-zone in 0.10–0.40 — bad for RL gradient. **Cause:** the flat `0.1×` anticheat multiplier clobbered 9 trials whose underlying structured score was a healthy 0.45–0.60 (they wrote real pages but used `data:image` URIs or oversized inline SVGs). Once anticheat is divided out, the structured reward becomes smooth: 47/50 trials in a `[0.40, 0.65]` band with stdev 0.13 — well-shaped for RL.

   **Implication:** decouple constraint from reward. Use structured composite (or arithmetic-mean of metrics, not harmonic) as the **dense training signal**, treat anticheat as a **constraint/penalty term** (fixed subtraction per violation, severity-scaled, not multiplicative). Keep the multiplicative `0.1×` only at **held-out eval** where a hard "you cheated → near-zero" signal is the right semantic. Currently the same formula is used for both regimes, which is fine for eval but flattens learning gradient in training.

8. **Anticheat misclassification — two false-positive surfaces in `anticheat.py`.** Re-examining the 9 trials clobbered by the `0.1×` multiplier (finding #7) shows the violations were not adversarial:
   - **`data_image_uri`** matches any `data:image/...` URI by regex. Reference pages embed small inline SVG icons (logo glyphs, status dots, etc.) as data URIs; agents that reproduce this pattern faithfully trip the check. The check has no payload-size threshold — a 200-byte inline icon and a 200-KB embedded PNG are treated identically. Legitimate icons (<2 KB) should be exempted; a real screenshot-embed cheat base64-encodes to 100 KB+.
   - **`oversized_inline_svg`** parses `<svg width=… height=…>` attributes and flags area > threshold. SVGs declared with percentage units (`width="100%"`) cannot be reasoned about from HTML alone — `_parse_svg_dimensions` should return `None` for percent-width SVGs (caller already drops `None`-area entries) and instead rely on rendered bbox from `dom.json` for the real check. Currently chart tiles and decorative full-width SVGs get flagged despite occupying normal layout area.

   The other three checks (`image_byte_copy`, `off_origin`, `raster_image_file`) fire correctly on the trials inspected. Fix queued in implementation order; until then, the structured (pre-multiplier) score in `subscores_v2.json` is the trustworthy signal for the 9 affected trials.

9. **`end_turn` planning-stall regression in claude-code 2.1.148** (vs 2.1.146): ~13% of trials hit `end_turn` after creating a TODO list and reading references, without ever invoking `Write`. Mitigated by `k=5` (per-task pass rate ≈ 99.9%) and a top-of-instruction "do not stop after planning" directive.

---

## Reward function — LOCKED (v6, 2026-05-22)

After the v9 calibration pass, the design-replication reward is locked to the following shape. All thirteen `tasks/v9/*/tests/{metrics.py,grade.py,anticheat.py,vlm_judge.py}` files are in sync with `pipeline/grader/`.

**Per-(page, viewport) composite**:
```
structured = weighted_arith({ssim, block_match, palette, text, position, typography})
base       = min(structured, vlm_judge)
composite  = base * (0.5 + 0.5 * overflow_score)
```

Weights (sum to 1.0 of *present* metrics; renormalised by `_weighted_arith` when any score is None):
- text 0.20, ssim 0.15, block_match 0.15, palette 0.12, typography 0.10, position 0.10
- overflow weight = 0 (acts only as the partial multiplier above)
- vlm_judge weight = 0 (acts only as the hard min ceiling above)

**Change vs v5:** overflow promoted from soft *ceiling* (`min(composite, 0.5 + 0.5×overflow)`) to partial *multiplier* (`composite × (0.5 + 0.5×overflow)`). v5 capped non-responsive pages at 0.5 but couldn't drag them lower; v6 multiplies — a fully-broken responsive layout (overflow=0) now halves the composite. Eyeball calibration on 008-hr-payroll/time-off mobile (candidate is 588px wide at 375px viewport, missing widgets) pushed final score 0.500 → 0.288, matching the ~0.4 eyeball verdict.

**VLM judge fixes (also new in v6):**
- Downscale screenshots whose max dimension exceeds 7800px before sending (Anthropic API rejects >8000px). Previously 17% of mobile and 2% of tablet pairs silently skipped VLM.
- `VLM_MAX_TOKENS` bumped 256 → 512; tolerant JSON parser handles truncated responses.
- Prompt tightened: explicit caps for wrong-widget-shape (≤0.4), candidate-simpler-than-reference (≤0.4), content fabrication (≤0.4). Removed implicit mobile leniency.

**Per-page aggregation**: harmonic mean across the 3 viewports of that page (worst viewport dominates).
**Per-site aggregation**: harmonic mean across pages × anticheat factor.

**Anticheat factor (decoupled eval vs train)**:
- Eval (`reward = site × penalty_multiplier`): `0.1×` if any violation, else `1.0×`. Hard "you cheated → near-zero" semantic.
- Train (`reward = max(0, site − train_penalty)`): subtractive `0.05 × distinct_violation_types`, capped at 0.20. Preserves RL gradient when the policy writes real pages but trips one violation.

**Calibration history** that shaped v6 (each step validated against eyeball verdicts before next):
1. SSIM cropped to `min(ref, cand)` (not zero-padded) to avoid triple-counting truncation with block_match/position.
2. Palette split into bg/fg channels (fixed the dark-page false-match where text-color was pooled with bg).
3. Palette normaliser tightened to 0.15 OKLab L2 (~15 JNDs) from 0.6.
4. Block_match cap dropped 400 → 100 (was saturating; per-page stdev doubled).
5. Overflow rewritten as symmetric width-diff using `max(scrollWidth, png_width)` so DOM `overflow:hidden` no longer hides real overflow; empty candidates return 0 instead of None.
6. Anticheat `data_image_uri` made size-aware (≥2KB threshold) and `oversized_inline_svg` skips percent-width SVGs from HTML alone — fixed 9 false-positive 0.1× clobberings.
7. Weights rebalanced text→0.20, overflow→0.18 (later moved out of weighted term).
8. **(v5)** Overflow moved from weighted term to soft ceiling so a non-responsive page caps at 0.5.
9. **(v6)** Overflow promoted from soft ceiling to partial multiplier so a fully-broken responsive layout drags the composite by 50%, not just floors at 0.5.
10. **(v6)** VLM downscale-before-send (Anthropic 8000px limit), max_tokens 256→512, tolerant JSON parse — recovered 130 silently-failing VLM calls (17% of mobile).
11. **(v6)** VLM prompt tightened to remove mobile leniency (explicit "reference defines target, do not grant credit for the candidate looking reasonable for mobile"; hard caps on wrong-widget / candidate-simpler-than-reference).

**Variance assessment (v9 set, claude-opus-4-7, k=10)**: cross-task mean-of-means ranges 0.266 → 0.867 (CV ~30%), best-of-10 ranges 0.307 → 0.893. The v9 set added 2 easy "hello" tasks (single-page, simple) and 1 large "conference-event" task (8 pages) on top of the 10 dashboard-style v7adv tasks, stretching the axis from v7's 0.475–0.619 to v9's 0.27–0.89. Healthcare-emr saw 5/10 trials hit the Claude Code 2.1.148 end_turn regression (zero rewards from agent never writing files) — excluded from mean via `n_valid` filter on `reward > 0.01`. Reporting both `mean` (across non-regression trials) and `best` (capability ceiling) gives reliability + ceiling per task.

**Known gaps left for follow-ups (not blockers):**
- Block_match still bbox-IoU based; per-task cross-task stdev is ~0.025 even at k=100. Grid-cell occupancy or match-or-miss thresholding would discriminate more, but the metric is already useful.
- `oversized_inline_svg` stage-2 follow-up (read rendered bbox from `dom.json` instead of regex-parsing HTML) not implemented. The percent-width skip closes the false-positive flood; we lose the (rare) "agent draws entire page as one big SVG" detector. Acceptable because such a hack would still score poorly on text/block_match/VLM.
- `numeric_match` sub-metric (digit-level fidelity) considered but not added — text metric partially captures it, VLM judge catches the worst cases.

---

## Open Questions (TBD — to be resolved before locking the pipeline)

- **DreamSim backbone:** original (CLIP+OpenCLIP+DINO) or DINOv2 refresh (Oct 2024). Latter is stronger but heavier.
- **TreeBLEU vs ignore-DOM:** TreeBLEU still depends on DOM tags, which leaks reference-generator markup conventions. Acceptable as a structural sanity check; not acceptable as a primary signal. Confirm weight stays low.
- **Cross-page λ value:** start at 0.3; tune during calibration.
- **Block-Match block-detection method:** vision-based (segmentation on rendered image) vs DOM-based (bounding boxes from `getBoundingClientRect`). DOM-based is faster and more reliable but again leaks markup conventions. Vision-based is harder to implement but framework-agnostic. Lean vision-based; confirm during prototype.
- **MLLM-as-judge as a held-out cross-check:** worth adding as a separate score we report but don't train on?
- **Grader harness:** pytest vs custom Python script in `test.sh`. Custom script is cleaner for a composite scorer; pytest is the Harbor convention.
- **Multi-page agent input format:** single Harbor task with N reference screenshots, or N tasks chained? Likely single task — cross-page reward needs all pages in one trial.
- **Agent/grader container topology:** confirm Harbor's verifier really does run in a separate container (docs imply yes; verify empirically with a probe task).
- **Modal as the trial runtime:** Harbor supports Modal natively. Plan to use Modal for parallel trial execution once the local end-to-end is working.
