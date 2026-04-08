"""WebVoyager-format JSONL loader.

Reads WebVoyager-shaped task records from a JSONL file (one record per
line) and produces an Inspect AI ``Dataset``. Used for both the v8
curated 12-task subset (in ``caliper-browser-pilot/data/v8_curated.jsonl``)
and the full 643-task WebVoyager benchmark when caliper grows into
Layer 3 broad-coverage runs (Phase 2).

## Schema

Each line is a JSON object with these fields:

    {
      "id":        "Task--N",
      "input":     "natural-language goal",
      "target":    "reference answer string",
      "metadata":  {
        "bucket":            "lookup" | "search" | "compare" | "navigate" | ...,
        "source":            "WebVoyager" | "AssistantBench" | ...,
        "license":           "academic" | "Apache 2.0" | ...,
        "is_time_sensitive": true | false,
        "last_validated":    "YYYY-MM-DD",
        "reference_type":    "golden" | "possible",
        "start_url":         "https://...",
        ...
      }
    }

The ``bucket`` and ``source`` keys are required (they're enforced by
``caliper.protocols.validate_task_metadata``); the rest are optional.
The schema mirrors ``docs/reference/curated-tasks.md`` "Loading these
in caliper".

## Validation policy

- Missing required keys → ``ValueError`` (fail loud, methodology
  principle 1: measurement layer must not silently accept malformed
  data).
- Unknown metadata keys → soft warning via ``warnings.warn``,
  loaded anyway. Loaders that pass through source-specific fields
  shouldn't be blocked.
- A line that fails ``json.loads`` → ``ValueError`` with the line
  number.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

from inspect_ai.dataset import Dataset, MemoryDataset, Sample

from caliper.protocols import REQUIRED_METADATA_KEYS, validate_task_metadata


def load_webvoyager_jsonl(
    path: str | Path,
    *,
    name: str | None = None,
) -> Dataset:
    """Load a WebVoyager-format JSONL file into an Inspect AI Dataset.

    Args:
        path: Filesystem path to the JSONL file. Each line is one task.
        name: Optional dataset name surfaced in Inspect AI's UI. If
            omitted, the file's stem is used (e.g. ``v8_curated``).

    Returns:
        A ``MemoryDataset`` of ``Sample`` objects.

    Raises:
        FileNotFoundError: if ``path`` doesn't exist.
        ValueError: if any line is invalid JSON, missing the required
            ``id`` / ``input`` / ``target`` fields, or has metadata
            missing the ``bucket`` / ``source`` required keys.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"WebVoyager JSONL not found: {p}")

    samples: list[Sample] = []
    for line_no, raw in enumerate(p.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{p}:{line_no}: invalid JSON: {exc}"
            ) from exc

        for required in ("id", "input", "target"):
            if required not in record:
                raise ValueError(
                    f"{p}:{line_no}: missing required field {required!r}"
                )

        metadata = record.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError(
                f"{p}:{line_no}: metadata must be an object, "
                f"got {type(metadata).__name__}"
            )

        # Required keys are enforced; unknown keys are warned but loaded.
        errors = validate_task_metadata(metadata)
        for err in errors:
            if err.startswith("missing required"):
                raise ValueError(f"{p}:{line_no}: {err}")
            else:
                warnings.warn(
                    f"{p}:{line_no}: {err}",
                    stacklevel=2,
                )

        samples.append(
            Sample(
                id=record["id"],
                input=record["input"],
                target=record["target"],
                metadata=metadata,
            )
        )

    return MemoryDataset(
        samples=samples,
        name=name or p.stem,
        location=str(p),
    )


def filter_by_bucket(dataset: Dataset, bucket: str) -> Dataset:
    """Return a new ``Dataset`` containing only samples with the given
    ``metadata["bucket"]`` value.

    The new dataset's name is ``f"{original.name}.{bucket}"`` so it
    surfaces clearly in Inspect AI's UI.
    """
    filtered = [
        s
        for s in dataset
        if s.metadata is not None and s.metadata.get("bucket") == bucket
    ]
    return MemoryDataset(
        samples=filtered,
        name=f"{dataset.name or 'dataset'}.{bucket}",
        location=dataset.location,
    )


__all__ = ["load_webvoyager_jsonl", "filter_by_bucket"]


# Sanity: REQUIRED_METADATA_KEYS is the contract this loader enforces.
assert "bucket" in REQUIRED_METADATA_KEYS
assert "source" in REQUIRED_METADATA_KEYS
