# caliper-chatbot

Caliper scenario package for the **chatbot maxTurns termination-strategy
A/B**. The full experimental design lives in
[`docs/chatbot-maxturns.md`](../../docs/chatbot-maxturns.md).

**Status: Phase 3b skeleton.** This package is intentionally empty except
for module placeholders. Implementation lands in roadmap milestones M3b.*.

## Planned content

| Module | Purpose | Lines (est.) |
|---|---|---|
| `strategies/` | 9 `LimitStrategy` implementations (HardCut, ForceFinalize×2, SoftWarn, PauseTurn, AdaptiveBudget, TokenBudget, MultiStage) | ~700 |
| `scorers/ux_judge.py` | 5-dimensional chatbot UX judge | ~120 |
| `mocks/` | Mock tools for the 5 budget-exhausting tasks | ~200 |
| `tasks/` | The 5 mock task definitions | ~300 |
| `solver.py` | `limit_strategy_agent()` — agent loop with Strategy hooks | ~150 |

**Total: ~1500 lines.** This is comparable to caliper core itself, which
is exactly why the chatbot scenario lives in its own package: it must NOT
inflate caliper core. The bug surface stays scenario-local.

The Strategy *protocol* lives in `caliper.protocols.Strategy` (a
Protocol class with no implementations). This package provides the 9
concrete strategies. New scenarios that need their own strategies
implement the same protocol in their own packages.

## Hard rules

- Never imports from `caliper-browser-pilot` or `caliper-computer-pilot`
- Only depends on `caliper` core
- Promotion of any code to `caliper` core requires the rule-of-three:
  the same abstraction must already exist in at least two other packages.
