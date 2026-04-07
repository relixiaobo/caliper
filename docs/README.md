# Caliper Documentation

These docs describe what caliper is, why it exists, and how it works.

The project is currently in **Phase 0**: documentation-first design. There's no
code yet — the goal of Phase 0 is to commit to the architecture, methodology,
and roadmap before writing a single line of Python.

## Reading order

### If you're picking up the project to work on it

You need the **operational** docs first, then the narrative:

1. **[context.md](context.md)** — **Start here.** Where the related
   repos live, environment setup, file pointers, the next milestone.
   This is the "agent handoff" doc.

2. **[roadmap.md](roadmap.md)** — Phases, milestones, success criteria,
   the effects tracking table. Find your next checkbox.

3. **[reference/](reference/)** — Verbatim artifacts to port:
   - [baseline-v8.md](reference/baseline-v8.md) — anchor numbers
     Phase 1 must reproduce
   - [curated-tasks.md](reference/curated-tasks.md) — the 12 v8 tasks
     with full goals/refs/buckets
   - [inherited-artifacts.md](reference/inherited-artifacts.md) — judge
     prompt, parser, lazy detection set, snapshot formatter, pricing
     table — the exact code to port

### If you're trying to understand the design

Read the **narrative** docs:

1. **[why.md](why.md)** — The case for evidence-based iteration on agent
   stacks. Why existing eval tools don't fit. What questions caliper helps
   answer.

2. **[methodology.md](methodology.md)** — The 5 core principles that come
   from 8 weeks of painful iteration. Each principle is paired with a concrete
   failure mode that motivated it.

3. **[architecture.md](architecture.md)** — How caliper composes with Inspect
   AI. The layered design. Two example use cases: browser-pilot and chatbot
   maxTurns testing.

4. **[self-evaluation.md](self-evaluation.md)** — Why and how caliper
   evaluates its own components. The dogfooding principle.

5. **[lessons-learned.md](lessons-learned.md)** — The 8-round story of
   browser-pilot iteration. The bugs we found in our own measurement layer
   that inflated all our earlier numbers by 38%.

## Document conventions

- **Decisions** are recorded inline in the relevant doc, not in a separate
  ADR directory. We'll add `decisions/` only when we have a real architectural
  fork that's worth recording formally.
- **Use cases / scenarios** are mentioned as inline examples in the docs that
  use them. There's no separate `scenarios/` directory because scenarios are
  arguments, not categories.
- **Code references** use the form `path/to/file.py:42` so they're navigable
  in editors.
