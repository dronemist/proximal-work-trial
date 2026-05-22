# Eval-set generation pipeline (`pipeline/eval_gen/`)

Generates multi-page reference websites and packages each as a Harbor task directory. Stages 0–9 of the pipeline described in `research/eval_generation_synthesis.md`. **Stage 10 (Harbor job submission) is done manually** — this code stops at writing task directories to disk.

## Layout

```
pipeline/eval_gen/
├── README.md                    # this file
├── config.py                    # tunables: N_TASKS, PAGES_PER_SITE, smoke config
├── spec_library/                # Stage 0 — primitive data
│   ├── palettes.py              # color palettes (Tailwind, Primer, Polaris, ...)
│   ├── typography.py            # font pairings
│   ├── spacing.py               # spacing/radius scales
│   ├── domains.py               # 15 domain page-lists
│   ├── archetypes.py            # layout archetypes
│   └── business_names.py        # procedural name generator
├── generator/                   # Stages 1–4 — LLM calls
│   ├── client.py                # Anthropic SDK wrapper
│   ├── brand_spec.py            # Stage 1: sample DESIGN.md-style brand spec
│   ├── brief.py                 # Stage 2: brief (single-call for smoke; VS later)
│   ├── library.py               # Stage 3: per-site component library
│   └── pages.py                 # Stage 4: iterative per-page HTML
├── render_validate.py           # Stage 5: Playwright render + structural checks
├── packaging/                   # Stage 9 — emit Harbor task directories
│   ├── harbor_task.py
│   └── templates/               # task.toml, instruction.md templates
└── create_websites.py                 # entry point: generate 5 task directories
```

## Smoke wave

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY=...

# Generate 5 task directories under tasks_generated/smoke/
python -m pipeline.eval_gen.create_websites
```

Output: 5 Harbor task directories at `tasks_generated/smoke/<NN>-<slug>/`. Each directory is self-contained — copy into the project's `tasks/` to run via Harbor.

## Smoke-wave simplifications vs the full synthesis

To keep the smoke wave focused on integration-test correctness (catch plumbing failures, not statistical calibration), several full-pipeline features are disabled here:

- **Stage 2** — single-call brief, no Verbalized Sampling (added in pilot wave).
- **Stage 6** — header byte-equality + CSS-token variance only; no DreamSim (deferred to pilot wave on GPU Modal).
- **Stage 7** — no VLM critic; rejected sites are surfaced by structural validation only.
- **Stage 8** — print a coverage report; no enforced thresholds at N=5.
- Renderer is **Claude Sonnet only** (no multi-model mixing).
- `PAGES_PER_SITE = [5, 7]` for the smoke wave (smaller than the [7, 10] production default; faster, cheaper).

All disabled features are stubs in the code with TODO markers, ready to be filled in when scaling beyond smoke.

## Grader

The grader is **not** generated here. It's copied verbatim from `pipeline/grader/` + `pipeline/render.py` into each task's `tests/` directory. If the central grader changes, regenerate the task directories.
