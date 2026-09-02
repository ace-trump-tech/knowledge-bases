"""Top-N selection per subtopic + bucket assignment."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .providers.arxiv import ArxivPaper
from .rank import RankedPaper


@dataclass(frozen=True)
class Selected:
    paper: ArxivPaper
    rank: RankedPaper
    classification_confidence: float


@dataclass(frozen=True)
class SelectionResult:
    by_subtopic: dict[str, list[Selected]]
    unclassified: list[Selected]

    @property
    def all_papers(self) -> list[Selected]:
        out: list[Selected] = []
        for items in self.by_subtopic.values():
            out.extend(items)
        out.extend(self.unclassified)
        return out


def select_top_n(
    papers_with_ranks: list[tuple[ArxivPaper, RankedPaper, float]],
    *,
    subtopic_of: dict[str, str],
    top_n: int,
) -> SelectionResult:
    """Group papers by resolved subtopic and keep top N per group."""
    by_sub: dict[str, list[Selected]] = defaultdict(list)
    unclassified: list[Selected] = []

    for paper, rank, conf in papers_with_ranks:
        item = Selected(paper=paper, rank=rank, classification_confidence=conf)
        st = subtopic_of.get(paper.short_id())
        if st is None or conf < 0.30:
            unclassified.append(item)
            continue
        by_sub[st].append(item)

    for st, items in by_sub.items():
        items.sort(key=lambda x: x.rank.score, reverse=True)
        by_sub[st] = items[:top_n]

    return SelectionResult(by_subtopic=dict(by_sub), unclassified=unclassified)


__all__ = ["Selected", "SelectionResult", "select_top_n"]