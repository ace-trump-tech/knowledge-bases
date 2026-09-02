"""Tests for the markdown renderer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from arxiv_daily.providers.arxiv import ArxivPaper
from arxiv_daily.providers.ollama import OllamaResponse
from arxiv_daily.render import _safe_filename, render_manifest, render_paper_markdown
from arxiv_daily.select import Selected
from arxiv_daily.rank import RankedPaper
from arxiv_daily.providers.semantic_scholar import SemanticScholarMeta


SAMPLE_TEMPLATE = """# <Paper Title> (2026/arXiv)

## 基本信息
- **作者 / 机构**：
- **会议/期刊**：
- **arXiv**：
- **项目页 / 代码**：

## 问题
要解决的痛点，1–2 句话。

## 方法
核心方法，3–5 句话含技术关键。

## 创新点
- 贡献 1
- 贡献 2
- 贡献 3

## 实验结果
- **数据集**：
- **指标**：

## 局限性
- 局限 1
- 局限 2

## 相关工作链接
- **前序**：[...]

## 一句话总结
"""


def _paper():
    return ArxivPaper(
        arxiv_id="2406.01234",
        title="Driving with Latent World Models",
        authors=["Alice", "Bob"],
        abstract="We propose a unified latent world model for end-to-end driving.",
        categories=["cs.CV"],
        primary_category="cs.CV",
        published=datetime(2026, 8, 31, tzinfo=timezone.utc),
        updated=datetime(2026, 8, 31, tzinfo=timezone.utc),
        pdf_url="https://arxiv.org/pdf/2406.01234",
        abs_url="https://arxiv.org/abs/2406.01234",
        comment="12 pages",
    )


def _selected():
    paper = _paper()
    return Selected(
        paper=paper,
        rank=RankedPaper(
            arxiv_id=paper.short_id(),
            score=85.5,
            parts={"citation": 0.5, "influential": 0.4, "recency": 0.9, "novelty": 0.6},
            s2=SemanticScholarMeta.empty(paper.short_id()),
            novelty_0_100=70.0,
        ),
        classification_confidence=0.8,
    )


def test_safe_filename_uses_year_and_title():
    paper = _paper()
    name = _safe_filename(paper)
    assert name.startswith("2026_")
    assert name.endswith(".md")
    assert "_deep" not in name


def test_render_summary_fills_template(tmp_path):
    template_dir = tmp_path / "_templates"
    template_dir.mkdir()
    (template_dir / "paper_summary_template.md").write_text(SAMPLE_TEMPLATE)

    out = render_paper_markdown(
        _selected(),
        subtopic_id="01_test",
        template_dir=template_dir,
        output_dir=tmp_path / "out",
        is_deep=False,
    )
    assert out.summary_path is not None
    assert out.deep_path is None
    body = out.summary_path.read_text(encoding="utf-8")
    assert "Driving with Latent World Models" in body
    assert "2406.01234" in body
    assert "arXiv preprint" in body or "CVPR" in body
    assert "Alice, Bob" in body


def test_render_deep_fills_template(tmp_path):
    template_dir = tmp_path / "_templates"
    template_dir.mkdir()
    (template_dir / "paper_deep_review_template.md").write_text(SAMPLE_TEMPLATE)

    out = render_paper_markdown(
        _selected(),
        subtopic_id="01_test",
        template_dir=template_dir,
        output_dir=tmp_path / "out",
        is_deep=True,
    )
    assert out.deep_path is not None
    assert "Driving with Latent World Models" in out.deep_path.read_text(encoding="utf-8")


def test_render_manifest_produces_both_files(tmp_path):
    template_dir = tmp_path / "_templates"
    template_dir.mkdir()
    (template_dir / "paper_summary_template.md").write_text(SAMPLE_TEMPLATE)

    rendered = render_paper_markdown(
        _selected(),
        subtopic_id="01_test",
        template_dir=template_dir,
        output_dir=tmp_path / "out" / "01_test",
        is_deep=False,
    )
    json_path, md_path = render_manifest(
        output_dir=tmp_path / "out",
        iso_date="2026-09-02",
        kb_name="driver-kb",
        by_subtopic={"01_test": [rendered]},
        unclassified=[],
    )
    assert json_path.exists() and md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["kb"] == "driver-kb"
    assert "01_test" in payload["subtopics"]
    assert payload["subtopics"]["01_test"][0]["arxiv_id"] == "2406.01234"
    assert "Driving with Latent World Models" in md_path.read_text(encoding="utf-8")