# caliper

Core package. Evidence-based iteration framework for agent stacks. Built on
top of [Inspect AI](https://inspect.aisi.org.uk/).

This is one of four packages in the caliper workspace. See the workspace
root README and `docs/architecture.md` for the full picture.

## What lives here

- `caliper.protocols` — typed contracts (`SolverState`, `Strategy`, `TaskMetadata`)
- `caliper.parsers` — generic text parsing (shell-aware command extraction, ANSWER blocks)
- `caliper.runtime` — subprocess + .env helpers
- `caliper.solvers` — generic agent loops (text-protocol, strategy-loop)
- `caliper.scorers` — generic scorers (json verdict parser, judge, lazy detection, multi-dim base)
- `caliper.metrics` — pricing tables and cost calculation
- `caliper.report` — bucket aggregation, A/B compare, multi-dim reports
- `caliper.datasets` — generic loaders for public benchmarks
- `caliper.mocks` — mock-tool framework (no specific mocks)
- `caliper.strategies` — `Strategy` Protocol class (no specific implementations)

## What does NOT live here

Anything tool-specific, scenario-specific, or benchmark-data. Those go in
the adapter packages (`caliper-browser-pilot`, `caliper-computer-pilot`,
`caliper-chatbot`).

**Hard rule:** `caliper` never imports from any `caliper-*` adapter. The
dependency arrow always points one way.
