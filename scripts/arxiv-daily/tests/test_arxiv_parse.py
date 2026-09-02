"""Tests for arxiv Atom parsing (no network)."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

import feedparser
import pytest

from arxiv_daily.providers.arxiv import _parse_entry, _strip_versioned_id

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_atom_sample.xml"


def _feed():
    return feedparser.parse(FIXTURE.read_text(encoding="utf-8"))


def test_strip_id_variants():
    assert _strip_versioned_id("http://arxiv.org/abs/2406.01234v2") == "2406.01234v2"
    assert _strip_versioned_id("2406.01234v2") == "2406.01234v2"
    assert _strip_versioned_id("http://arxiv.org/pdf/2406.01234.pdf") == "2406.01234"
    assert _strip_versioned_id("cs.CV/0405001v1") == "cs.CV/0405001v1"


def test_parse_entry_modern_id():
    paper = _parse_entry(_feed().entries[0])
    assert paper.arxiv_id == "2406.01234v2"
    assert paper.short_id() == "2406.01234"
    assert paper.primary_category == "cs.CV"
    assert "Latent World Models" in paper.title
    assert "BEV" in paper.abstract
    assert len(paper.authors) == 2
    assert paper.published.tzinfo is not None and paper.published.tzinfo == timezone.utc
    assert paper.comment == "12 pages, 6 figures"
    assert paper.pdf_url.endswith("2406.01234v2")
    assert paper.abs_url.startswith("https://arxiv.org/abs/")


def test_parse_entry_old_style_id():
    paper = _parse_entry(_feed().entries[1])
    assert paper.arxiv_id == "cs.CV/0405001v1"
    assert paper.short_id() == "cs.CV/0405001"
    assert paper.primary_category == "cs.RO"
    assert "Diffusion" in paper.title