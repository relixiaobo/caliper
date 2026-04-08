"""caliper-chatbot — chatbot maxTurns termination-strategy A/B scenario.

**Status: Phase 3b skeleton.** Module placeholders only.

The full design lives in ``docs/chatbot-maxturns.md``. The implementation
plan is:

    strategies/    — 9 LimitStrategy implementations (~700 lines)
    scorers/       — multi-dim chatbot UX judge (~120 lines)
    mocks/         — mock tools for the 5 budget-exhausting tasks (~200 lines)
    tasks/         — the 5 mock task definitions (~300 lines)
    solver.py      — limit_strategy_agent (~150 lines)

Total: ~1500 lines. **This stays in caliper-chatbot, not caliper core.**
The bug surface is intentionally scenario-local. Promotion of any
abstraction to caliper core requires the rule-of-three: it must already
exist in two other adapter packages.
"""
