"""limit_strategy_agent — Phase 3b placeholder.

# TODO M3b.1: implement the agent loop with Strategy hooks.
#
# Sketch (from docs/chatbot-maxturns.md §4.2):
#
#   from caliper.protocols import Strategy, SolverState
#   from inspect_ai.solver import solver, Solver
#
#   @solver
#   def limit_strategy_agent(strategy: Strategy, max_turns: int = 10) -> Solver:
#       async def solve(state, generate):
#           ss = state.store_as(SolverState)
#           for turn_idx in range(max_turns):
#               strategy.before_turn(turn_idx, max_turns, state)
#               result = await generate(state)
#               # ... handle tool calls, etc ...
#               if budget_exhausted(state):
#                   termination = strategy.on_limit_reached(state, ...)
#                   ss.agent_answer = termination.text or ""
#                   state.metadata["termination_kind"] = termination.kind
#                   return state
#           return state
#       return solve
#
# Note: this is structurally different from caliper.solvers.text_protocol_agent
# because it uses Inspect AI's native tool calling, NOT a text protocol.
# That's why it lives here, not in core. If a future scenario needs the
# same shape, we promote (rule-of-three).
"""
