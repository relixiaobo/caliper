"""The 5 mock-task definitions — Phase 3b placeholder.

Each task is constructed so that the "correct" path requires K tool calls
and the budget is set to K-2 or K-3, forcing the budget limit. This is
how we isolate strategy effects from task-completion noise.

# TODO M3b.2: implement the 5 task @task definitions:
#
#   research_grants.py   (k_min=15, budget_for_test=8)
#   debug_auth.py        (k_min=9,  budget_for_test=6)
#   shopping_compare.py  (k_min=12, budget_for_test=7)
#   multi_source.py      (k_min=8,  budget_for_test=5)
#   compound_task.py     (k_min=8,  budget_for_test=5)
#
# Each task uses caliper_chatbot.solver.limit_strategy_agent + the 9
# strategies from strategies/ + the chatbot UX judge from scorers/.
# See docs/chatbot-maxturns.md §4.1 for full task specs.
"""
