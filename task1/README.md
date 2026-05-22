# Design-to-Code RL Environment

A scalable pipeline for generating RL environments that test coding agents' ability to replicate multi-page website designs from screenshots.

## What This Is

Given reference screenshots of a multi-page website, a coding agent must produce HTML+CSS that visually replicates the design across desktop, tablet, and mobile viewports. The grading is continuous (0.0–1.0), multi-axis (layout, color, typography, content, visual), and cheat-resistant.

The pipeline generates websites from scratch (no crawling), packages them as [Harbor](https://harborframework.com/) tasks, and includes a grader that produces smooth reward signals suitable for RL training.

## Repository Structure

```
├── docs/
│   ├── data-generation.md          # How websites are generated + infrastructure design decisions
│   ├── grading.md           # Metric suite, aggregation, anti-cheat, why it works for RL
│   ├── results.md           # Evaluation scores + observations on model behavior
│   ├── task-showcase.md     # Visual gallery of the 13 tasks
│   └── limitations.md       # Honest assessment + future work (animations, frameworks)
├── pipeline/
│   ├── eval_gen/            # Website generation (brand spec → brief → library → pages)
│   ├── grader/              # Grading (metrics.py, vlm_judge.py, anticheat.py)
│   ├── render.py            # Playwright rendering (same code for reference + verifier)
│   ├── render_on_modal.py   # Modal-based rendering (deterministic Linux environment)
│   ├── package.py           # Scaffold + render Harbor tasks
│   ├── scaffold_task.py     # Harbor task scaffolding from template
│   └── task_template/       # Canonical Harbor task template
├── tasks/                   # 13 ready-to-run Harbor tasks
│   ├── 001-gov-services-v7adv/    (5 pages, light theme, gov services)
│   ├── 002-restaurant-ops-v7adv/  (5 pages, dark theme, restaurant ops)
│   ├── ...
│   ├── 010-nonprofit-donations-v7adv/
│   ├── 011-hello-portfolio-v9/    (5 pages, portfolio)
│   ├── 012-hello-recipes-v9/
│   └── 001-conference-event-v9/   (8 pages, mixed theme, conference)
└── results/                 # Evaluation results from Opus runs
```

## Quick Start

### Run an existing task with Harbor

```bash
harbor run tasks/001-gov-services-v7adv --agent claude
```

### Generate new tasks

```bash
pip install modal anthropic playwright
modal token new
modal secret create anthropic-api-key ANTHROPIC_API_KEY=sk-ant-...

# Generate 5 sites with 5 pages each
modal run pipeline/eval_gen/create_websites_modal.py::generate --run-suffix myrun

# Download results
modal run pipeline/eval_gen/create_websites_modal.py::download --what both
```

### Package pre-existing reference sites

```bash
python pipeline/package.py reference_sites/001-my-site
```

## Key Design Decisions

Detailed in the docs, but the highlights:

1. **Multi-viewport grading** — Desktop + tablet + mobile, aggregated with harmonic mean. Forces genuine responsive design.
2. **8 complementary metrics** — Pixel (SSIM), structural (block match, position), semantic (text, palette, typography), visual (VLM judge), and integrity (overflow). No single metric can be gamed.
3. **Harmonic aggregation** — One bad page or viewport tanks the whole score. Rewards consistency.
4. **Anti-cheat** — 6 checks (image copy, raster files, oversized SVGs, off-origin requests, data URIs, embed tags). Any violation → 0.1× multiplier.
5. **Same renderer everywhere** — Reference PNGs, agent output, and grader all use the same Playwright+Chromium on the same OS. Eliminates drift.
6. **Diversity by construction** — 15 domains × 15 archetypes × 12 palettes × 3 themes, shuffled to guarantee no axis reuse within a batch.

## Documentation

| Doc | What it covers |
|-----|---------------|
| [Design Decisions](docs/design-decisions.md) | Key architectural choices and why they were made |
| [Pipeline](docs/data-generation.md) | Generation stages, Modal parallelism, multi-viewport rendering, training data correctness |
| [Grading](docs/grading.md) | Metric suite, weights, aggregation, anti-cheat, why it works for RL |
| [Results](docs/results.md) | Evaluation scores, score distributions, model behavior observations |
| [Task Showcase](docs/task-showcase.md) | Visual gallery of all 13 tasks with diversity breakdown |
| [Limitations](docs/limitations.md) | Current limitations + future work (animations, frameworks, DreamSim) |
