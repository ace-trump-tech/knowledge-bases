"""Tests for the CLI entrypoint (smoke tests, no network)."""

from __future__ import annotations

import pytest

from arxiv_daily import __version__
from arxiv_daily.cli import main


def test_version_flag(capsys):
    # argparse --version calls parser.exit() which raises SystemExit(0).
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_status_lists_kb(tmp_path, capsys):
    cfg = tmp_path / "kb.yaml"
    cfg.write_text("""
kb_repo: ace-trump-tech/test-kb
kb_local_path: ./bases/test-kb
arxiv_categories: [cs.CV]
subtopics:
  - {id: "01_x", keywords: ["foo"], description: "topic x"}
""")
    rc = main(["status", "--config", str(cfg)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "test-kb" in captured.out
    assert "cs.CV" in captured.out