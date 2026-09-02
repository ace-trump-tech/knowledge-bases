"""Composite ranking: citation count + influential + novelty (LLM)."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable

from .providers.ollama import OllamaClient, OllamaUnavailable
from .providers.semantic_scholar import SemanticScholarClient, SemanticScholarMeta

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankWeights:
    citation: float = 0.40
    influential: float = 0.25
    recency: float = 0.20
    novelty: float = 0.15

    def total(self) -> float:
        return self.citation + self.influential + self.recency + self.novelty


def _normalize_log(values: list[float]) -> list[float]:
    """Log1p + min-max to 0..1, safe against uniform inputs."""
    if not values:
        return []
    logs = [math.log1p(max(0.0, v)) for v in values]
    lo, hi = min(logs), max(logs)
    if hi - lo < 1e-9:
        return [0.5 for _ in logs]
    return [(v - lo) / (hi - lo) for v in logs]


def _recency_score(days_old: float, *, half_life: float = 30.0) -> float:
    """Exponential decay with 30-day half-life: 1.0 today, 0.5 in 30d."""
    return 0.5 ** (max(0.0, days_old) / half_life)


@dataclass(frozen=True)
class RankedPaper:
    arxiv_id: str
    score: float
    parts: dict[str, float]
    s2: SemanticScholarMeta | None
    novelty_0_100: float


def rank_papers(
    papers: list,
    *,
    s2: SemanticScholarClient | None,
    ollama: OllamaClient | None,
    weights: RankWeights | None = None,
) -> list[RankedPaper]:
    """Compute composite scores; papers keep order from the caller if scores tie."""
    weights = weights or RankWeights()
    if not papers:
        return []

    s2_lookup: dict[str, SemanticScholarMeta] = {}
    if s2 is not None:
        try:
            s2_lookup = s2.lookup_many([p.short_id() for p in papers])
        except Exception as exc:  # noqa: BLE001  - never block ranking
            LOGGER.warning("S2 lookup_many failed: %s", exc)
            s2_lookup = {}

    # 1. collect raw signals
    citations: list[float] = []
    influential: list[float] = []
    for p in papers:
        meta = s2_lookup.get(p.short_id()) or SemanticScholarMeta.empty(p.short_id())
        citations.append(float(meta.citation_count))
        influential.append(float(meta.influential_citation_count))

    # 3. novelty: ask ollama (optional). Fall back to 50.0 (neutral).
    novelty: list[float] = []
    if ollama is not None and ollama.is_available():
        for p in papers:
            novelty.append(_novelty(p, ollama))
    else:
        novelty = [50.0 for _ in papers]

    # 4. normalise + combine
    norm_cit = _normalize_log(citations)
    norm_inf = _normalize_log(influential)
    norm_nov = [n / 100.0 for n in novelty]

    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc)
    norm_rec = [
        _recency_score((now - p.published).total_seconds() / 86400.0)
        for p in papers
    ]

    out: list[RankedPaper] = []
    for idx, p in enumerate(papers):
        parts = {
            "citation": norm_cit[idx],
            "influential": norm_inf[idx],
            "recency": norm_rec[idx],
            "novelty": norm_nov[idx],
        }
        score = (
            weights.citation * parts["citation"]
            + weights.influential * parts["influential"]
            + weights.recency * parts["recency"]
            + weights.novelty * parts["novelty"]
        ) * 100.0
        out.append(
            RankedPaper(
                arxiv_id=p.short_id(),
                score=score,
                parts=parts,
                s2=s2_lookup.get(p.short_id()),
                novelty_0_100=novelty[idx],
            )
        )
    out.sort(key=lambda r: r.score, reverse=True)
    return out


def _novelty(paper, ollama: OllamaClient) -> float:
    """Ask ollama for a 0..100 novelty score for the paper."""
    prompt = (
        "Score the technical novelty of this arXiv paper on a 0..100 scale. "
        "Consider: does it introduce a new method, dataset, benchmark, or "
        "theoretical result? Is it a re-run of existing ideas? Reply with "
        "ONLY an integer between 0 and 100.\n\n"
        f"Title: {paper.title}\n"
        f"Abstract: {paper.abstract[:1500]}"
    )
    try:
        resp = ollama.generate(prompt)
    except OllamaUnavailable:
        return 50.0
    import re

    m = re.search(r"\d{1,3}", resp.text)
    if not m:
        return 50.0
    val = max(0, min(100, int(m.group(0))))
    return float(val)


__all__ = ["RankWeights", "RankedPaper", "rank_papers"]