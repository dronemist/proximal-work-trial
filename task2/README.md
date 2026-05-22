# Task 2 — Animation Support

Extends the Task 1 pipeline (static website replication) to generate and grade websites with CSS animations.

## Eval Generation

The generation pipeline adds animations to reference websites via a spec-driven approach.

**Animation primitives** (`pipeline/eval_gen/spec_library/animations.py`):
- 10 entrance animations (fade-in, fade-up, fade-down, fade-left, fade-right, scale-up, scale-down, clip-reveal-up, blur-in, rotate-in) — fire once on page load
- 5 ambient animations (pulse, float, shimmer, glow, spin-slow) — loop infinitely for subtle background motion
- 2 stagger patterns (sequential, cascade) for grouped elements
- 6 easing curves
- 3 complexity tiers: simple (1-2 entrance, 0-1 ambient), medium (2-4 entrance, 1-2 ambient, stagger), hard (3-5 entrance, 2-3 ambient, stagger)

**How it works**:
1. `sample_animation_spec()` picks entrance + ambient animations, assigns durations/delays/easings per the complexity tier
2. `format_animation_spec_for_prompt()` converts the spec to prose for the LLM prompt — tells it which elements to animate and how
3. `collect_keyframes_css()` gathers all `@keyframes` rules for inclusion in `styles.css`
4. `resolve_animation_spec()` on `BrandSpec` wires it all together at site generation time

**Capture** (`pipeline/eval_gen/render_validate.py`):
- `capture_animation_keyframes()` — pauses all animations via the Web Animations API immediately after page load, seeks to 0%/50%/100% of the animation timeline, screenshots at each point. Saves `.animations.json` metadata (duration, delay, iterations, easing, keyframes, target elements).
- `capture_animation_filmstrip()` — captures 10 frames evenly spaced across the entrance animation timeline, stitches into a labeled grid PNG. Timeline is based on entrance-only duration so short entrance animations aren't lost in long ambient loops. Saved to `screenshots/filmstrips/`.
- `capture_animation_video()` — records a 5-second WebM video of the page with animations playing naturally, using Playwright's built-in video recording. One video per viewport. Saved to `screenshots/videos/`.

**Config** (`pipeline/eval_gen/config.py`):
- `ANIMATED` config preset sets `animation_mode="css"` and `animation_complexity="medium"`
- `animation_keyframe_pcts` controls which progress points to screenshot (default: 0%, 50%, 100%)

**Modal** (`pipeline/eval_gen/create_websites_modal.py`):
- `generate_animated` entrypoint — defaults to 1 site, 1 page for quick iteration
- Output stored under `task2/<run_suffix>/` on the Modal volume for per-run isolation
- `download --run-suffix <suffix>` pulls a specific run

## Grader

The grader detects animated tasks and combines static + animation scores.

**Overall scoring**:
```
final_score = 0.65 * static_score + 0.35 * animation_score
```

**Static score** — unchanged from Task 1: structured metrics (text, SSIM, block match, palette, typography, position) + VLM judge on screenshots.

**Animation score** — hybrid of structured metrics and VLM:
```
animation_score = 0.40 * structured_metrics + 0.60 * vlm_animation
```

**Structured animation metrics** (`pipeline/grader/animation_metrics.py`):
- `keyframe_ssim` (weight 0.50) — SSIM across keyframe screenshots at 0%/50%/100%
- `animation_count` (weight 0.20) — ratio of reference vs candidate animation count
- `timing_similarity` (weight 0.15) — Hungarian-matched duration/delay comparison
- `property_match` (weight 0.15) — Jaccard similarity over animated CSS properties

**VLM animation judge** (`pipeline/grader/vlm_judge.py`):
- `judge_animation()` sends reference + candidate filmstrip PNGs to Claude Sonnet
- Evaluates: animation presence, motion direction/type, timing/pacing, stagger pattern, visual end state
- Falls back to structured-only if no API key is set

**Detection and capture** (`pipeline/grader/grade.py`):
- Animated tasks detected by presence of `.animations.json` files in the reference directory
- Agent animation keyframes captured using the same Web Animations API approach as the reference pipeline
- Agent filmstrips and videos captured for VLM comparison
- All animation details written to `subscores.json`

## Open Questions / Not Yet Solved

**Hover animations**: CSS transitions on `:hover` (button color shifts, card scale-ups, underline slides) are common on real websites but hard to evaluate. The core problem is element matching — a "Contact Us" button in the reference might be at a completely different DOM position in the candidate. We'd need to discover all hoverable elements, semantically match them across ref vs candidate, then trigger hover on each, wait for the transition, and compare. Playwright can `element.hover()` to trigger transitions, but the choreography (which elements, in what order, how to match across different DOMs) is fragile. The VLM could judge "does this site have nice hover effects" from a video of someone mousing around, but producing a deterministic, comparable capture is the unsolved part.

**Scroll-triggered animations**: Elements that animate in as the user scrolls down (e.g., Intersection Observer patterns). Playwright can `window.scrollTo()` step by step, but the capture script needs to know how far to scroll, how fast, and where animated elements live. This adds significant complexity to both generation (telling the LLM to use scroll-triggered animations without JS — pure CSS `scroll-timeline` is still limited) and capture (deterministic scroll choreography).

**JS-driven animations**: Libraries like GSAP, Framer Motion, Lottie. Agents would need to pick and use the right library, and the current no-JS constraint would need to be relaxed. Grading becomes harder because the Web Animations API may not expose JS-driven animations the same way. Likely requires a fundamentally different capture approach (video-only, no structured metrics).

