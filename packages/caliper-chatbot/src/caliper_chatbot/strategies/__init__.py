"""The 9 LimitStrategy implementations — Phase 3b placeholder.

Each strategy implements ``caliper.protocols.Strategy``. See
docs/chatbot-maxturns.md §4.2 for the full code sketches.

Planned modules (one per strategy, ~80 lines each):

    hard_cut.py             — pattern 1, LangChain default
    silent_stop.py          — pattern 2, return whatever's there
    force_finalize_strict.py — pattern 3a, smolagents style
    force_finalize_lenient.py — pattern 3b, CrewAI style
    soft_warn.py            — pattern 4, inject "N turns left"
    pause_turn.py           — pattern 5, Anthropic-style soft pause
    adaptive_budget.py      — pattern 6, extend on progress
    token_budget.py         — pattern 8, switch unit from turns to tokens
    multi_stage.py          — pattern 9, hybrid: warn → finalize → fallback

# TODO M3b.1: implement all 9. Order suggested by docs/chatbot-maxturns.md
# §8 Step 1: HardCut + ForceFinalizeStrict + MultiStage first (most
# differentiated), then expand.
"""
