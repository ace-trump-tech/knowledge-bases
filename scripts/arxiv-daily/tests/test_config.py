"""Tests for config loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from arxiv_daily.config import load_config
from arxiv_daily.exceptions import ConfigError


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "kb.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_minimal_valid_config(tmp_path):
    p = _write(tmp_path, """
kb_repo: ace-trump-tech/driver-kb
kb_local_path: ./bases/driver-kb
arxiv_categories: [cs.CV]
subtopics:
  - id: "01_x"
    keywords: ["foo", "bar"]
    description: "topic x"
""")
    cfg = load_config(p)
    assert cfg.name == "kb"
    assert cfg.owner == "ace-trump-tech"
    assert cfg.repo == "driver-kb"
    assert cfg.top_n_per_subtopic == 3
    assert cfg.fetch_window_hours == 26


def test_missing_kb_repo(tmp_path):
    p = _write(tmp_path, """
kb_local_path: ./bases/x
arxiv_categories: [cs.CV]
subtopics: [{id: "01_x", keywords: ["foo"]}]
""")
    with pytest.raises(ConfigError):
        load_config(p)


def test_empty_subtopics(tmp_path):
    p = _write(tmp_path, """
kb_repo: ace-trump-tech/x
kb_local_path: ./bases/x
arxiv_categories: [cs.CV]
subtopics: []
""")
    with pytest.raises(ConfigError):
        load_config(p)