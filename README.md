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

**Phase 1 — M1.1 complete + workspace restructure** (current).

Caliper is a **uv workspace** containing four sibling Python packages:

| Package | Role | Status |
|---|---|---|
| `caliper` | Core framework — protocols, parsers, scorers, generic solvers | M1.1 complete |
| `caliper-browser-pilot` | Adapter for the `bp` CLI (browser-pilot v8 baseline) | bp_agent done; 12 tasks land in M1.3 |
| `caliper-computer-pilot` | Adapter for the `cu` CLI (computer-pilot) | Skeleton; implementation in Phase 3a |
| `caliper-chatbot` | Scenario package for chatbot maxTurns A/B (1500 lines, 9 strategies) | Skeleton; implementation in Phase 3b. Full design in [`docs/chatbot-maxturns.md`](docs/chatbot-maxturns.md) |

See [docs/roadmap.md](docs/roadmap.md) for the milestone plan and
[docs/architecture.md](docs/architecture.md#workspace-layout--single-git-repo-multiple-python-packages)
for the workspace contract.

## Quick links

- [Why this exists](docs/why.md) — the case for evidence-based iteration
- [Methodology](docs/methodology.md) — the 5 core principles
- [Architecture](docs/architecture.md) — how it composes with Inspect AI
- [Test sets](docs/test-sets.md) — where tasks come from, how to vet them, the 5-layer strategy
- [Self-evaluation](docs/self-evaluation.md) — how caliper tests itself
- [Lessons learned](docs/lessons-learned.md) — the 8-week story
- [Chatbot maxTurns scenario](docs/chatbot-maxturns.md) — the second worked example: termination-strategy A/B
- [Roadmap](docs/roadmap.md) — phases, milestones, effects tracking

## License

MIT — see [LICENSE](LICENSE).
