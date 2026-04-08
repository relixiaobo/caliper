"""Tests for the .env loader."""

from __future__ import annotations

import os
from pathlib import Path

from caliper.runtime.env import load_dotenv


def test_loads_simple_kv(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nBAZ=qux\n")
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAZ", raising=False)

    set_keys = load_dotenv(env_file)
    assert set_keys == {"FOO": "bar", "BAZ": "qux"}
    assert os.environ["FOO"] == "bar"
    assert os.environ["BAZ"] == "qux"


def test_does_not_overwrite_existing(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ALREADY_SET=new_value\n")
    monkeypatch.setenv("ALREADY_SET", "original")

    set_keys = load_dotenv(env_file)
    assert set_keys == {}
    assert os.environ["ALREADY_SET"] == "original"


def test_skips_comments_and_blank_lines(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n"
        "# this is a comment\n"
        "REAL_KEY=real_value\n"
        "\n"
        "# another comment\n"
    )
    monkeypatch.delenv("REAL_KEY", raising=False)

    set_keys = load_dotenv(env_file)
    assert set_keys == {"REAL_KEY": "real_value"}


def test_missing_file_returns_empty(tmp_path: Path):
    set_keys = load_dotenv(tmp_path / "nope.env")
    assert set_keys == {}
