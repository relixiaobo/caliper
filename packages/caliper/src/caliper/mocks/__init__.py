"""Mock-tool framework — placeholder for Phase 3.

Generic infrastructure for defining mock tools that return deterministic
responses, registering them with a solver, and recording/replaying
traces. This is what makes synthetic Layer 4 tests (per
``docs/test-sets.md``) possible: tasks designed to force specific failure
modes need mock tools whose K+1-step path is known.

caliper core ships only the framework. Specific mocks live in scenario
packages — e.g. the chatbot maxTurns scenario's 5 budget-exhausting
tasks have their mocks in ``caliper-chatbot/src/caliper_chatbot/mocks/``.

**Status: skeleton only.** Implementation lands when the chatbot
scenario starts in Phase 3.
"""
