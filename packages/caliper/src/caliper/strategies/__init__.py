"""Strategy protocol — the placeholder layer for the chatbot scenario.

This module intentionally contains only the ``Strategy`` Protocol class
(re-exported from ``caliper.protocols``). Concrete strategies live in
scenario packages — e.g. the 9 chatbot termination strategies are in
``caliper-chatbot/src/caliper_chatbot/strategies/``.

caliper core never ships specific strategies. The protocol exists so
multiple scenarios can interoperate (a Report module that knows how to
display a Strategy axis works for any scenario, not just chatbot).

See ``docs/chatbot-maxturns.md`` for the canonical first user.
"""

from caliper.protocols import Strategy

__all__ = ["Strategy"]
