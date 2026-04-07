# Caliper

> Evidence-based iteration for agent stacks.

Caliper is a thin layer on top of [Inspect AI](https://inspect.aisi.org.uk/)
that adds the discipline you actually need when iterating on an agent system:
variance measurement, judge anti-bug parsing, lazy-behavior detection, cost &
cache tracking, and bucketed A/B comparison.

## Why does this exist

Building agents is easy. **Knowing whether your last change made things better
is hard.** Most teams iterate on tools, prompts, and strategies based on
intuition because there's no cheap way to A/B test a single design decision
with statistical rigor.

Caliper was extracted from 8 weeks of iterating on
[browser-pilot](https://github.com/relixiaobo/browser-pilot). Across those 8
rounds we discovered that the highest-leverage improvements weren't in the
agent loop or the tools — they were in the **measurement layer**. Three of the
biggest wins came from finding bugs in *how we measured*, not in how we built.

Caliper bakes those measurement-discipline lessons into a reusable framework so
you don't have to rediscover them.

## What it gives you

- **Structured judge** with anti-substring-bug JSON parsing
- **Lazy detection**: catches "describe-don't-do" agent cheating
- **Stale-reference tolerance** for time-sensitive benchmark answers
- **Cost & cache tracking** with per-model pricing tables
- **Variance measurement** with N≥2 enforced as default
- **Bucketed reporting** so model strengths/weaknesses are visible per task category
- **A/B comparison** between configs with noise-floor analysis
- **Self-evaluation**: caliper's own components are tested with caliper

## What it doesn't do

- It's **not an agent framework** (use Inspect AI / smolagents / LangChain for that)
- It's **not a benchmark dataset** (it works with WebVoyager, your own tasks, mock tasks)
- It's **not a model provider** (Inspect AI handles that)

## Status

**Phase 0 — Documentation scaffolding** (current). No runnable code yet. The
project is being designed in `docs/` first, then implemented in Phase 1.

See [docs/roadmap.md](docs/roadmap.md) for the plan.

## Quick links

- [Why this exists](docs/why.md) — the case for evidence-based iteration
- [Methodology](docs/methodology.md) — the 5 core principles
- [Architecture](docs/architecture.md) — how it composes with Inspect AI
- [Self-evaluation](docs/self-evaluation.md) — how caliper tests itself
- [Lessons learned](docs/lessons-learned.md) — the 8-week story
- [Roadmap](docs/roadmap.md) — phases, milestones, effects tracking

## License

MIT — see [LICENSE](LICENSE).
