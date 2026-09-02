"""High-level ``fetch`` orchestration: pull, classify, rank, render."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import classify as classify_mod
from . import rank as rank_mod
from . import render as render_mod
from . import select as select_mod
from .config import KBConfig
from .providers.arxiv import ArxivClient, ArxivPaper
from .providers.ollama import OllamaClient
from .providers.semantic_scholar import SemanticScholarClient
from .state import KBState, load_state, save_state

LOGGER = logging.getLogger(__name__)


def _configure_logging() -> None:
    """One-shot INFO setup so Actions logs show what fetch actually does."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            stream=sys.stdout,
        )


@dataclass
class FetchResult:
    iso_date: str
    cfg: KBConfig
    selected: select_mod.SelectionResult
    rendered_by_subtopic: dict[str, list[render_mod.RenderedPaper]]
    rendered_unclassified: list[render_mod.RenderedPaper]
    manifest_json_path: Path
    manifest_md_path: Path
    state: KBState
    new_count: int
    skipped_duplicates: int


def run_fetch(
    cfg: KBConfig,
    *,
    output_root: Path,
    iso_date: Optional[str] = None,
    dry_run: bool = False,
    ollama: OllamaClient | None = None,
    s2: SemanticScholarClient | None = None,
    s2_cache_path: Optional[Path] = None,
) -> FetchResult:
    """End-to-end: fetch -> classify -> rank -> select -> render -> state."""
    _configure_logging()
    if iso_date is None:
        iso_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    output_root = Path(output_root)
    day_root = output_root / iso_date
    day_root.mkdir(parents=True, exist_ok=True)
    LOGGER.info("[%s] starting fetch for %s", cfg.name, iso_date)

    arxiv = ArxivClient()
    papers = arxiv.query(
        categories=cfg.arxiv_categories,
        submitted_after=datetime.now(tz=timezone.utc)
        - timedelta(hours=cfg.fetch_window_hours),
        max_results=200,
    )
    LOGGER.info("[%s] fetched %d papers", cfg.name, len(papers))

    state_path = output_root / "arxiv-daily" / "state.json"
    state = load_state(state_path) if not dry_run else KBState()
    state.kb_repo = cfg.kb_repo

    # 1. classify + 2. rank (with deduplication against state)
    pairs: list[tuple[ArxivPaper, float]] = []
    classified: dict[str, str] = {}        # short_id -> subtopic
    confs: dict[str, float] = {}
    skipped = 0
    for paper in papers:
        if state.has(paper.short_id()):
            skipped += 1
            continue
        text = paper.title + "\n" + paper.abstract
        cls = classify_mod.classify_paper(text, cfg, ollama=ollama)
        classified[paper.short_id()] = cls.subtopic_id or ""
        confs[paper.short_id()] = cls.confidence
        pairs.append((paper, cls.confidence))

    LOGGER.info(
        "[%s] kept=%d skipped_dup=%d classified=%d",
        cfg.name, len(pairs), skipped, len({k for k,v in classified.items() if v}),
    )

    ranked = rank_mod.rank_papers(
        [p for p, _ in pairs],
        s2=s2 if not dry_run else None,
        ollama=ollama,
    )
    ranked_by_id = {r.arxiv_id: r for r in ranked}

    triples: list[tuple[ArxivPaper, rank_mod.RankedPaper, float]] = [
        (p, ranked_by_id[p.short_id()], confs[p.short_id()])
        for p, _ in pairs
        if p.short_id() in ranked_by_id
    ]

    selection = select_mod.select_top_n(
        triples, subtopic_of=classified, top_n=cfg.top_n_per_subtopic
    )

    # 3. render markdown into per-subtopic folders
    template_dir = cfg.kb_local_path / "idea" / "_templates"
    if not template_dir.exists():
        LOGGER.warning(
            "[%s] template dir missing at %s; will produce stubs only",
            cfg.name, template_dir,
        )

    rendered_by_subtopic: dict[str, list[render_mod.RenderedPaper]] = {}
    rendered_unclassified: list[render_mod.RenderedPaper] = []
    new_count = 0

    for st, items in selection.by_subtopic.items():
        out_dir = day_root / st
        out_dir.mkdir(parents=True, exist_ok=True)
        bucket: list[render_mod.RenderedPaper] = []
        for item in items:
            is_deep = item.rank.score >= cfg.deep_review_threshold
            if template_dir.exists():
                rp = render_mod.render_paper_markdown(
                    item,
                    subtopic_id=st,
                    template_dir=template_dir,
                    output_dir=out_dir,
                    is_deep=is_deep,
                )
            else:
                rp = render_mod.RenderedPaper(
                    paper=item.paper, subtopic=st,
                    summary_path=out_dir / "STUB.md", deep_path=None,
                    confidence=item.classification_confidence,
                    rank_score=item.rank.score, novelty=item.rank.novelty_0_100,
                )
            bucket.append(rp)
            state.mark(
                item.paper.short_id(),
                iso_date=iso_date,
                rank_score=item.rank.score,
                subtopic=st,
            )
            new_count += 1
        rendered_by_subtopic[st] = bucket

    for item in selection.unclassified:
        out_dir = day_root / "unclassified"
        out_dir.mkdir(parents=True, exist_ok=True)
        rp = render_mod.RenderedPaper(
            paper=item.paper, subtopic="unclassified",
            summary_path=out_dir / _stub_name(item.paper),
            deep_path=None,
            confidence=item.classification_confidence,
            rank_score=item.rank.score, novelty=item.rank.novelty_0_100,
        )
        rendered_unclassified.append(rp)

    json_path, md_path = render_mod.render_manifest(
        output_dir=day_root,
        iso_date=iso_date,
        kb_name=cfg.name,
        by_subtopic=rendered_by_subtopic,
        unclassified=rendered_unclassified,
    )

    if not dry_run:
        save_state(state, state_path)

    return FetchResult(
        iso_date=iso_date,
        cfg=cfg,
        selected=selection,
        rendered_by_subtopic=rendered_by_subtopic,
        rendered_unclassified=rendered_unclassified,
        manifest_json_path=json_path,
        manifest_md_path=md_path,
        state=state,
        new_count=new_count,
        skipped_duplicates=skipped,
    )


__all__ = ["FetchResult", "run_fetch"]


def _stub_name(paper: ArxivPaper) -> str:
    return f"{paper.published.year}_{paper.short_id().replace('/', '_')}.md"


__all__ = ["FetchResult", "run_fetch"]