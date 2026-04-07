# Why Caliper Exists

## The thesis

> The hardest part of building agents is not building the agent.
> It's knowing whether your last change made things better or worse.

Most teams iterate on agent tools, prompts, and termination strategies based
on intuition and small-sample manual checks. They ship changes that "feel
better", they don't notice regressions until users complain, and they argue
about design choices because nobody has data.

This isn't a model problem. It's a **measurement infrastructure** problem. You
don't know what improved your system until you can measure it cheaply,
repeatably, and with statistical discipline.

Caliper exists to be that measurement infrastructure.

## The questions caliper helps you answer

Concretely, caliper is built to make these questions cheap to answer with
real numbers:

- "Did adding this new tool to my agent actually help, or just shuffle which
  tasks succeed?"
- "My SKILL.md grew from 800 to 2000 tokens. Is the longer prompt actually
  worth the cost, or is the model ignoring most of it?"
- "Should the maxTurns limit be 10, 15, or 20? What's the precision/cost
  curve look like?"
- "When the agent hits maxTurns, is force-finalize better than hard-cut for
  user experience? Or is it just trading one failure mode for another?"
- "Switching from Sonnet to Haiku saves 80% on cost. How much accuracy do I
  actually lose?"
- "Is my prompt cache actually being hit? Or did my last skill.md edit
  invalidate the prefix and triple my real cost without me noticing?"
- "When I ask the model to call tool X with args {a, b, c}, does it pick the
  right tool? Does it pick X for situations where it shouldn't?"
- "When I refactor a tool's output format from JSON to compact text, does
  agent performance improve, stay flat, or degrade?"
- "Two runs of the same task on the same model gave different results. Is
  this signal or noise? How many runs do I need before I can claim an
  improvement?"

These are the questions that determine whether an agent product is good or
bad. They are also questions that **no existing tool answers cleanly**.

## Why existing tools don't fit

### Agent runtimes (LangChain, smolagents, pi-mono, OpenAI Agents SDK, ...)

These are designed for *running* agents in production. Their abstractions
optimize for shipping a working agent: streaming, retries, hooks, observability
for users. But they hide the things you need for *iterating* — token-level
cost, cache hit rates, per-turn timing, deterministic replay, A/B harness.

When you try to use them as eval frameworks, you end up writing the eval layer
yourself anyway, on top of an abstraction that wasn't designed for it.

### LLM eval frameworks (lm-evaluation-harness, OpenAI Evals, DeepEval, ...)

These are built for evaluating *model outputs*, not agent loops. They assume a
single-turn setup: prompt in, response out, score. Multi-turn agent tool use
is either an afterthought or completely unsupported.

### Observability tools (Langfuse, Phoenix, LangSmith, ...)

These show you what happened in production, but they don't give you a
framework for *iterating with intent*. There's no concept of "I want to run the
same task with config A and config B and compare them with statistical rigor".
They're great for diagnosing production issues, not for guiding development.

### Inspect AI (the closest fit)

[Inspect AI](https://inspect.aisi.org.uk/) is the one serious general-purpose
agent eval framework. UK's AI Safety Institute uses it to evaluate frontier
models on dangerous capability benchmarks. It has Task / Solver / Scorer
abstractions, multi-provider support, sandboxing, a web viewer, and built-in
prompt cache token tracking.

**Caliper is not a competitor to Inspect AI — it builds on top of it.**

What caliper adds is the *iteration discipline* that Inspect AI doesn't impose
out of the box:

| Inspect AI gives you | Caliper adds |
|---|---|
| Multi-provider LLM API | Cost calculation in $ (with per-model pricing) |
| Cache token tracking (I/CW/CR/O) | Cache hit rate as a first-class metric |
| Custom scorers | A scorer library with anti-bug judge parsing, lazy detection, stale-ref tolerance |
| Eval sets | Bucketed reporting: per-task-category pass rate, per-bucket cost |
| Epochs (multi-run) | N≥2 enforced with warnings; CV / noise floor reported |
| Web viewer | A/B comparison viewer that diffs two eval runs |
| Tool use abstraction | A "text protocol" solver that wraps CLI tools without function-call schemas |

The vast majority of the agent eval problem is already solved by Inspect AI.
Caliper is the ~500 lines on top that bake in the lessons we learned by
getting them wrong first.

## What kind of project this is

Caliper is **not**:

- A new agent framework
- A new benchmark dataset
- A new model provider abstraction
- A general-purpose ML eval tool

Caliper **is**:

- A small Python package on top of Inspect AI
- A library of opinionated scorers, metrics, and reports
- A methodology, encoded as code and as documentation
- A benchmark of itself (see [self-evaluation.md](self-evaluation.md))

## How it relates to browser-pilot

The browser-pilot project is the **first consumer** of caliper, and the place
where the methodology was discovered through painful trial and error. The 8
rounds of iteration described in [lessons-learned.md](lessons-learned.md)
happened in `browser-pilot/tests/agent/run.py`, a 670-line Python script that
will be migrated to caliper in Phase 1.

Other planned consumers (chatbot maxTurns strategies, computer-pilot) will
validate that caliper's abstractions are actually general, not just
browser-shaped.

## What success looks like

Caliper succeeds if:

1. **A team can run a full A/B comparison of two agent configurations and
   trust the result** without having debugged a judge bug, a substring
   parsing bug, a stale reference, or a cache invalidation surprise. (We hit
   all four during browser-pilot iteration.)

2. **A change to a prompt or a tool can be validated against a baseline in
   under 10 minutes** with a single command, producing a report that says
   "this change is real" or "this is within noise".

3. **The framework can evaluate itself**: caliper's own scorers and
   metrics are tested against labeled cases using the framework's own
   primitives. This is the strongest test that the abstractions are general.

If we ship Phase 1 (browser-pilot migration) and the framework can produce
the v9 cost-aware baseline within ±5% of the existing v8 baseline numbers,
we'll have proof that the abstractions work.
