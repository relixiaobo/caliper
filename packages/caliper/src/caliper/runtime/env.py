"""Tiny .env loader — sets environment variables from a KEY=value file.

Inspect AI's model providers read API keys from the environment, so
benchmark scripts (especially in ``examples/``) need a way to populate
``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` etc. from a local ``.env``
file without forcing every script to inline the same parsing code.

This is deliberately minimal — no quoting rules, no variable
interpolation, no export keyword. If you need real dotenv semantics, use
the ``python-dotenv`` package directly.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path | None = None) -> dict[str, str]:
    """Load KEY=value pairs from a .env file into ``os.environ``.

    Args:
        path: Path to the .env file. If ``None``, searches for ``.env`` in
            the current working directory and walks up to the filesystem
            root, returning empty dict if not found.

    Returns:
        Dict of the keys that were actually set (i.e. not already present
        in ``os.environ``). Existing env vars are NEVER overwritten.

    Lines beginning with ``#`` and blank lines are ignored. Values are
    stripped of surrounding whitespace; quotes are NOT stripped.
    """
    env_path = _resolve_env_path(path)
    if env_path is None or not env_path.exists():
        return {}

    set_keys: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if key not in os.environ:
            os.environ[key] = value
            set_keys[key] = value
    return set_keys


def _resolve_env_path(path: str | Path | None) -> Path | None:
    if path is not None:
        return Path(path)
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return None
