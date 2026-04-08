"""Runtime helpers used by solvers: subprocess execution + .env loading.

Pure utility code with no agent-loop or LLM dependencies. Adapter packages
may also use these.
"""

from caliper.runtime.env import load_dotenv
from caliper.runtime.subprocess import run_cli

__all__ = ["load_dotenv", "run_cli"]
