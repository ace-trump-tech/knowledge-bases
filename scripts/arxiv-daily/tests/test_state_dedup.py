"""Tests for state persistence and dedup."""

from __future__ import annotations

import pytest

from arxiv_daily.exceptions import StateCorrupt
from arxiv_daily.state import KBState, load_state, save_state


def test_mark_distinguishes_new_vs_seen():
    state = KBState()
    assert state.mark("2406.01234", iso_date="2026-09-02", rank_score=80.5, subtopic="01_vla") is True
    assert state.mark("2406.01234", iso_date="2026-09-03", rank_score=82.0, subtopic="01_vla") is False
    assert len(state.entries) == 1
    entry = state.entries["2406.01234"]
    assert entry.first_seen == "2026-09-02"
    assert entry.last_seen == "2026-09-03"
    assert entry.rank_score == 82.0


def test_round_trip(tmp_path):
    state = KBState(kb_repo="ace-trump-tech/driver-kb")
    state.mark("2406.01234", iso_date="2026-09-02", rank_score=80.5, subtopic="02_world_model")
    state.mark("cs.CV/0405001", iso_date="2026-09-02", rank_score=72.0, subtopic="04_rl")

    p = tmp_path / "state.json"
    save_state(state, p)
    assert p.exists()

    reloaded = load_state(p)
    assert reloaded.kb_repo == "ace-trump-tech/driver-kb"
    assert set(reloaded.ids()) == {"2406.01234", "cs.CV/0405001"}


def test_corrupt_state_rejected(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    with pytest.raises(StateCorrupt):
        load_state(p)


def test_wrong_schema_rejected(tmp_path):
    p = tmp_path / "wrong.json"
    p.write_text('{"schema_version": 99, "entries": {}}')
    with pytest.raises(StateCorrupt):
        load_state(p)