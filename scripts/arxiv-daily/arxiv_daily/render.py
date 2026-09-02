"""Render markdown for a paper into a KB's template.

Each KB carries ``idea/_templates/paper_summary_template.md`` and
``paper_deep_review_template.md``. We read the template, substitute a fixed
set of placeholders, and write a new ``<year>_<slug>.md``. Both templates
contain ``<Paper Title>`` etc. as placeholders.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .providers.arxiv import ArxivPaper
from .rank import RankedPaper
from .select import Selected

LOGGER = logging.getLogger(__name__)

_TEMPLATE_SUMMARY = "paper_summary_template.md"
_TEMPLATE_DEEP = "paper_deep_review_template.md"

# Placeholders we substitute. Keys are regex patterns matched in the
# template; values are callables that produce the substitution.
_PLACEHOLDERS_SUMMARY: dict[str, str] = {
    r"<Paper Title>": "_title",
    r"## 基本信息[\s\S]*?(?=##|\Z)": "_basic_info_block",
}

_PLACEHOLDERS_DEEP: dict[str, str] = {
    r"<Paper Title>": "_title",
}


@dataclass
class RenderedPaper:
    paper: ArxivPaper
    subtopic: str
    summary_path: Path | None
    deep_path: Path | None
    confidence: float
    rank_score: float
    novelty: float


def render_paper_markdown(
    selected: Selected,
    *,
    subtopic_id: str,
    template_dir: Path,
    output_dir: Path,
    is_deep: bool,
) -> RenderedPaper:
    """Write one paper's markdown into ``output_dir``. Returns a RenderedPaper."""
    template_name = _TEMPLATE_DEEP if is_deep else _TEMPLATE_SUMMARY
    template_path = template_dir / template_name
    if not template_path.exists():
        raise RuntimeError(f"template missing: {template_path}")
    template_text = template_path.read_text(encoding="utf-8")

    body = _fill_template(template_text, selected.paper, is_deep=is_deep)
    filename = _safe_filename(selected.paper, suffix=("_deep" if is_deep else ""))
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename
    out_path.write_text(body, encoding="utf-8")

    return RenderedPaper(
        paper=selected.paper,
        subtopic=subtopic_id,
        summary_path=None if is_deep else out_path,
        deep_path=out_path if is_deep else None,
        confidence=selected.classification_confidence,
        rank_score=selected.rank.score,
        novelty=selected.rank.novelty_0_100,
    )


def render_manifest(
    *,
    output_dir: Path,
    iso_date: str,
    kb_name: str,
    by_subtopic: dict[str, list[RenderedPaper]],
    unclassified: list[RenderedPaper],
) -> tuple[Path, Path]:
    """Write manifest.json and manifest.md under ``<output_dir>/<date>``."""
    day_dir = output_dir / iso_date
    day_dir.mkdir(parents=True, exist_ok=True)

    import json

    payload = {
        "schema_version": 1,
        "kb": kb_name,
        "date": iso_date,
        "subtopics": {
            st: [
                {
                    "arxiv_id": rp.paper.short_id(),
                    "title": rp.paper.title,
                    "summary_path": str(rp.summary_path.relative_to(output_dir)) if rp.summary_path else None,
                    "deep_path": str(rp.deep_path.relative_to(output_dir)) if rp.deep_path else None,
                    "rank_score": round(rp.rank_score, 2),
                    "novelty": rp.novelty,
                    "confidence": round(rp.confidence, 2),
                }
                for rp in items
            ]
            for st, items in by_subtopic.items()
        },
        "unclassified": [
            {
                "arxiv_id": rp.paper.short_id(),
                "title": rp.paper.title,
                "rank_score": round(rp.rank_score, 2),
            }
            for rp in unclassified
        ],
    }
    json_path = day_dir / "manifest.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    md_path = day_dir / "manifest.md"
    md_path.write_text(_render_manifest_md(payload), encoding="utf-8")
    return json_path, md_path


# -- internals --------------------------------------------------------------


def _fill_template(text: str, paper: ArxivPaper, *, is_deep: bool) -> str:
    """Apply our substitutions against ``text``.

    For the summary template we replace the whole ``## 基本信息`` block with a
    richer multi-line section. For the deep template we just replace
    ``<Paper Title>`` and the basic-info block.
    """
    text = re.sub(r"<Paper Title>", paper.title, text)

    basic_block_re = re.compile(r"## 基本信息[\s\S]*?(?=\n## |\Z)", re.MULTILINE)
    block = _basic_info_block(paper, deep=is_deep)
    text = basic_block_re.sub(block.rstrip("\n"), text, count=1)
    return text


def _basic_info_block(paper: ArxivPaper, *, deep: bool) -> str:
    venue = _guess_venue(paper)
    authors = ", ".join(paper.authors[:6])
    if len(paper.authors) > 6:
        authors += " et al."
    lines = [
        "## 基本信息",
        f"- **作者 / 机构**：{authors}",
        f"- **会议 / 期刊**：{venue}",
        f"- **arXiv**：{paper.short_id()}",
        f"- **项目页 / 代码**：_未抓取，请人工补_",
        f"- **PDF**：{paper.pdf_url}",
        f"- **abs**：{paper.abs_url}",
    ]
    if paper.comment:
        lines.append(f"- **作者注释**：{paper.comment}")
    if deep:
        lines.append("- **社区评价**：_待人工填写（引用数 / 是否高引 / 是否 Best）_")
        lines.append("- **奖项 / 收录**：_待人工填写_")
    lines.append("")
    return "\n".join(lines)


_VENUE_HINTS = [
    ("cvpr", "CVPR"),
    ("iccv", "ICCV"),
    ("eccv", "ECCV"),
    ("neurips", "NeurIPS"),
    ("icml", "ICML"),
    ("iclr", "ICLR"),
    ("icra", "ICRA"),
    ("iros", "IROS"),
    ("corl", "CoRL"),
    ("rss", "RSS"),
    ("arxiv", "arXiv preprint"),
]


def _guess_venue(paper: ArxivPaper) -> str:
    haystack = (paper.title + " " + paper.comment + " " + paper.abstract[:300]).lower()
    for needle, label in _VENUE_HINTS:
        if needle in haystack:
            return label
    return "arXiv preprint"


_SLUG_RE = re.compile(r"[^a-z0-9]+", re.IGNORECASE)


def _safe_filename(paper: ArxivPaper, *, suffix: str = "") -> str:
    title_slug = _SLUG_RE.sub("_", paper.title.lower()).strip("_")[:60]
    year = paper.published.year
    base = f"{year}_{title_slug}{suffix}.md"
    return base


def _render_manifest_md(payload: dict) -> str:
    lines = [
        f"# arxiv-daily · `{payload['kb']}` · {payload['date']}",
        "",
        "> Draft generated by `arxiv-daily`. Author must review and merge manually.",
        "",
    ]
    for st, items in payload["subtopics"].items():
        lines.append(f"## {st} ({len(items)} papers)")
        if not items:
            lines.extend(["", "_No papers matched this subtopic today._", ""])
            continue
        lines.extend(
            [
                "",
                "| arXiv | Title | Score | Novelty | Confidence |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for it in items:
            lines.append(
                f"| [{it['arxiv_id']}](https://arxiv.org/abs/{it['arxiv_id']}) "
                f"| {_md_inline(it['title'])} "
                f"| {it['rank_score']:.1f} | {it['novelty']:.0f} | {it['confidence']:.2f} |"
            )
        lines.append("")

    if payload["unclassified"]:
        lines.append(f"## unclassified ({len(payload['unclassified'])})")
        lines.extend(
            [
                "",
                "_These papers were not assigned a subtopic with sufficient confidence; "
                "the author should move them to `idea/<subtopic>/` by hand._",
                "",
                "| arXiv | Title | Score |",
                "| --- | --- | ---: |",
            ]
        )
        for it in payload["unclassified"]:
            lines.append(
                f"| [{it['arxiv_id']}](https://arxiv.org/abs/{it['arxiv_id']}) "
                f"| {_md_inline(it['title'])} | {it['rank_score']:.1f} |"
            )
        lines.append("")
    return "\n".join(lines)


def _md_inline(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


__all__ = [
    "RenderedPaper",
    "render_paper_markdown",
    "render_manifest",
    "_safe_filename",
]