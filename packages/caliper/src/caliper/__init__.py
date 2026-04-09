"""Caliper — evidence-based iteration framework for agent stacks.

Built on top of Inspect AI. This is the **core** package; tool- and
scenario-specific code lives in sibling adapter packages
(``caliper-browser-pilot``, ``caliper-computer-pilot``, ``caliper-chatbot``).

See ``docs/architecture.md`` for the workspace contract and
``docs/methodology.md`` for the 5 principles caliper enforces.

## Two integration modes

**Full mode** (Inspect AI eval loop):
    Use ``caliper.scorers`` + ``caliper.solvers`` inside an Inspect AI
    ``Task``. Caliper owns the entire eval lifecycle. Best for
    caliper-native projects (browser-pilot, computer-pilot, etc.).

**Measurement-only mode** (standalone API):
    Use ``CaliperRecord`` + ``caliper.scoring`` functions. Your project
    runs the agent itself and feeds results to caliper for scoring,
    aggregation, and comparison. No Inspect AI eval loop needed.

Both modes share the same scoring logic — the Inspect AI scorers are
thin wrappers around the pure functions in ``caliper.scoring``.
"""

__version__ = "0.0.1"

from caliper.evaluator import CaliperEvaluator
from caliper.record import CaliperRecord, JudgeResult, VerifyResult

__all__ = [
    "CaliperEvaluator",
    "CaliperRecord",
    "JudgeResult",
    "VerifyResult",
]
