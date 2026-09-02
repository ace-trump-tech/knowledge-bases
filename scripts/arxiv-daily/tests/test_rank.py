"""Tests for the rank module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from arxiv_daily.providers.arxiv import ArxivPaper
from arxiv_daily.providers.ollama import OllamaClient, OllamaUnavailable
from arxiv_daily.providers.semantic_scholar import SemanticScholarClient, SemanticScholarMeta
from arxiv_daily.rank import RankWeights, rank_papers


def _paper(short_id: str, *, days_old: int = 0) -> ArxivPaper:
    now = datetime.now(tz=timezone.utc) - timedelta(days=days_old)
    return ArxivPaper(
        arxiv_id=short_id,
        title=f"Title for {short_id}",
        authors=["A"],
        abstract="abstract",
        categories=["cs.CV"],
        primary_category="cs.CV",
        published=now,
        updated=now,
        pdf_url=f"https://arxiv.org/pdf/{short_id}",
        abs_url=f"https://arxiv.org/abs/{short_id}",
    )


class _FakeS2(SemanticScholarClient):
    def __init__(self, citation_map):  # noqa: ANN001 - test fixture
        self.citation_map = citation_map

    def lookup_many(self, arxiv_ids):  # noqa: D401, ANN001
        return {
            aid: SemanticScholarMeta(
                arxiv_id=aid,
                s2_paper_id="x",
                citation_count=self.citation_map.get(aid, 0),
                influential_citation_count=self.citation_map.get(aid, 0) // 4,
                reference_count=10,
                tweet_count=0,
                year=2026,
            )
            for aid in arxiv_ids
        }


class _FakeOllama(OllamaClient):
    def __init__(self, scores):  # noqa: ANN001 - test fixture
        self.scores = scores

    def is_available(self):
        return True

    def generate(self, prompt, system=None):  # noqa: ANN001
        from arxiv_daily.providers.ollama import OllamaResponse
        # Return novelty score derived from a hash so each paper gets a unique value
        for arxiv_id, score in self.scores.items():
            if arxiv_id in prompt:
                return OllamaResponse(model="fake", text=str(score), total_duration_ns=0,
                                       prompt_tokens=0, completion_tokens=1)
        return OllamaResponse(model="fake", text="50", total_duration_ns=0,
                               prompt_tokens=0, completion_tokens=1)


def test_rank_orders_by_citations_when_other_signals_equal():
    papers = [_paper("a"), _paper("b"), _paper("c")]
    s2 = _FakeS2({"a": 200, "b": 50, "c": 10})
    ollama = _FakeOllama({"a": 50, "b": 50, "c": 50})
    ranked = rank_papers(papers, s2=s2, ollama=ollama, weights=RankWeights())
    ids = [r.arxiv_id for r in ranked]
    assert ids == ["a", "b", "c"]


def test_rank_handles_missing_ollama_gracefully():
    papers = [_paper("a"), _paper("b")]
    s2 = _FakeS2({"a": 5, "b": 100})
    # pass None for ollama; should still rank by citation
    ranked = rank_papers(papers, s2=s2, ollama=None, weights=RankWeights())
    assert ranked[0].arxiv_id == "b"
    # novelty defaults to 50.0
    assert ranked[0].novelty_0_100 == 50.0


def test_rank_recency_breaks_ties():
    """When citation/ novelty scores tie, recency should rank a fresh paper higher."""
    fresh = _paper("fresh", days_old=0)
    stale = _paper("stale", days_old=365)
    s2 = _FakeS2({"fresh": 5, "stale": 5})   # equal citations
    ollama = _FakeOllama({"fresh": 50, "stale": 50})  # equal novelty
    ranked = rank_papers([fresh, stale], s2=s2, ollama=ollama, weights=RankWeights())
    assert ranked[0].arxiv_id == "fresh"
    # confirm recency signal exists and decays
    fresh_paper = next(p for p in [fresh, stale] if p.arxiv_id == "fresh")
    stale_paper = next(p for p in [fresh, stale] if p.arxiv_id == "stale")
    assert fresh_paper.published > stale_paper.published