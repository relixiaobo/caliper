"""Caliper solvers — generic agent loops.

These are tool-agnostic. They take a CLI prefix or a Strategy hook and
the rest is delegated. Tool-specific defaults live in adapter packages
(``caliper-browser-pilot``, ``caliper-computer-pilot``).
"""

from caliper.solvers.text_protocol import text_protocol_agent

__all__ = ["text_protocol_agent"]
