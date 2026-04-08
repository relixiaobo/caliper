"""Mock tools for the 5 budget-exhausting tasks — Phase 3b placeholder.

# TODO M3b.2: implement deterministic mock tools whose K-step path is
# known so the budget-test always hits the limit. See
# docs/chatbot-maxturns.md §4.1 for the 5 task designs and the mock tools
# each one needs:
#
#   research_grants/    — search_grants_db, get_grant_details, check_eligibility, filter_by_status
#   debug_auth/         — read_file, search_logs, check_config
#   shopping_compare/   — search_products, get_specs, get_reviews
#   multi_source/       — read_email, extract_action_items, draft_response
#   compound_task/      — lookup_order, check_inventory, get_customer, draft_notification
#
# The mock framework infrastructure (registration, recording, replaying)
# lives in caliper.mocks core; specific mocks live here.
"""
