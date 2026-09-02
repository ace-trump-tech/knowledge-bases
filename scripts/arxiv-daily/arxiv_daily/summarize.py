"""Markdown body generation via local ollama.

We never auto-merge. This module produces ``body_md`` strings; the caller
writes them to disk only after the author explicitly invokes the command.
"""

from __future__ import annotations

import logging
import re

from .providers.ollama import OllamaClient, OllamaUnavailable
from .providers.arxiv import ArxivPaper

LOGGER = logging.getLogger(__name__)


def is_ollama_ready(client: OllamaClient | None) -> bool:
    return client is not None and client.is_available()


def generate_summary(
    paper: ArxivPaper,
    *,
    ollama: OllamaClient,
    language: str = "zh",
) -> str:
    """Return the body text that fills sections below `## 基本信息`.

    Sections produced: 问题 / 方法 / 创新点 / 实验结果 / 局限性 / 一句话总结.
    """
    prompt = _summary_prompt(paper, language=language)
    try:
        resp = ollama.generate(
            prompt,
            system=(
                "You are a precise research-paper digesting assistant. "
                "You only describe what is grounded in the provided abstract. "
                "Do not invent numbers. Output strict markdown, no preamble."
            ),
        )
    except OllamaUnavailable as exc:
        LOGGER.warning("ollama unavailable: %s", exc)
        return _stub_body(paper)
    return _normalise_summary(resp.text, paper)


def generate_deep_review(
    paper: ArxivPaper,
    *,
    ollama: OllamaClient,
    language: str = "zh",
) -> str:
    """Produce the 10-section deep review body (without the basic-info block)."""
    prompt = _deep_prompt(paper, language=language)
    try:
        resp = ollama.generate(
            prompt,
            system=(
                "You write deep reviews of research papers for an expert audience. "
                "Only use evidence from the abstract. Mark uncertain items as "
                "`_待人工补_`. Strict markdown, no preamble."
            ),
        )
    except OllamaUnavailable as exc:
        LOGGER.warning("ollama unavailable for deep review: %s", exc)
        return _stub_deep_body(paper)
    return _normalise_deep(resp.text, paper)


# -- prompts ----------------------------------------------------------------


def _summary_prompt(paper: ArxivPaper, *, language: str) -> str:
    lang_note = "Write in Simplified Chinese." if language == "zh" else "Write in English."
    return (
        f"{lang_note}\n\n"
        "Given the paper title and abstract below, fill in these sections:\n\n"
        "## 问题\n(1–2 sentences: the pain point.)\n\n"
        "## 方法\n(3–5 sentences covering the core method.)\n\n"
        "## 创新点\n(3 bullets, each a single sentence.)\n\n"
        "## 实验结果\n(Bullets: dataset + headline metric; if not in abstract, write `_待人工补_`.)\n\n"
        "## 局限性\n(2–3 bullets, hedging when uncertain.)\n\n"
        "## 一句话总结\n(≤30 chars or 15 words.)\n\n"
        "Title: " + paper.title + "\n\n"
        "Abstract: " + paper.abstract[:2200] + "\n"
    )


def _deep_prompt(paper: ArxivPaper, *, language: str) -> str:
    lang_note = "Write in Simplified Chinese." if language == "zh" else "Write in English."
    return (
        f"{lang_note}\n\n"
        "You will produce a deep review. Use the abstract as the only source. "
        "Mark any unprovable claim `_待人工补_`.\n\n"
        "Sections (omit `## 基本信息` — already filled):\n"
        "## 0. 一句话定位\n(≤30 chars)\n\n"
        "## 2. 问题与动机\n- 业界痛点:\n- 现有方法的具体缺陷 (2–3):\n- 本文的缝隙:\n\n"
        "## 3. 方法深度解析\n### 3.1 整体架构\n```\n[input] -> ... -> [output]\n```\n\n"
        "### 3.2 关键模块\n- 模块 A: 原理(并标出哪些是 _待人工补_)\n\n"
        "### 3.3 损失函数\nL_total = ...  (mark `_待人工补_` if unknown)\n\n"
        "### 3.4 训练细节\n- 优化器/学习率/batch size: _待人工补_\n- 硬件/时长: _待人工补_\n\n"
        "## 4. 实验分析\n### 4.1 主结果表\n| 方法 | 数据集 | 主指标 | 对比基线 |\n| --- | --- | --- | --- |\n| 本文 | _待人工补_ | _待人工补_ | _待人工补_ |\n\n"
        "### 4.2 关键消融\n- _待人工补_\n\n"
        "## 5. 创新性评估 (10 分制)\n- 方法新颖性: _/10\n- 实验充分性: _/10\n- 工程可复现: _/10\n- 影响力与启发性: _/10\n- 总评: _._/10\n\n"
        "## 6. 与同期工作的横向对比\n| 维度 | 本文 | 同期 A | 同期 B |\n| --- | --- | --- | --- |\n| 核心范式 |  |  |  |\n| 关键模块 |  |  |  |\n| 主指标 |  |  |  |\n\n"
        "## 7. 局限性\n- 显式: _待人工补_\n- 隐式: _待人工补_\n- 复现难点: _待人工补_\n\n"
        "## 8. 创新机会\n1. 方向: ... + 可行方法 + 预期效果\n2. ...\n3. ...\n\n"
        "## 10. 实施 / 部署建议\n- 推理速度: _待人工补_\n- 显存 / 算力: _待人工补_\n- 落地关键障碍: _待人工补_\n\n"
        "Paper title: " + paper.title + "\n"
        "arXiv id: " + paper.short_id() + "\n\n"
        "Abstract:\n" + paper.abstract[:3000] + "\n"
    )


# -- normalisation ----------------------------------------------------------


def _normalise_summary(text: str, paper: ArxivPaper) -> str:
    """Strip any leading preamble; ensure every required section is present."""
    text = re.sub(r"^.*?(?=## 问题)", "", text, count=1, flags=re.DOTALL)
    required = ("## 问题", "## 方法", "## 创新点", "## 实验结果", "## 局限性", "## 一句话总结")
    for sec in required:
        if sec not in text:
            text += f"\n\n{sec}\n_待人工补_\n"
    return text.strip() + "\n"


def _normalise_deep(text: str, paper: ArxivPaper) -> str:
    text = re.sub(r"^.*?(?=## 0\. )", "", text, count=1, flags=re.DOTALL)
    return text.strip() + "\n"


def _stub_body(paper: ArxivPaper) -> str:
    return (
        "## 问题\n_ollama 不可用；请人工填入或先 `ollama serve` + `ollama pull qwen2.5:14b`_\n\n"
        "## 方法\n_待人工补_\n\n"
        "## 创新点\n- _待人工补_\n\n"
        "## 实验结果\n- _待人工补_\n\n"
        "## 局限性\n- _待人工补_\n\n"
        "## 一句话总结\n_待人工补_\n"
    )


def _stub_deep_body(paper: ArxivPaper) -> str:
    return (
        "## 0. 一句话定位\n_ollama 不可用，待人工补_\n\n"
        "## 2. 问题与动机\n- 业界痛点: _待人工补_\n- 现有方法的具体缺陷: _待人工补_\n- 本文的缝隙: _待人工补_\n\n"
        "## 3. 方法深度解析\n### 3.1 整体架构\n```\n_inferred_only_from_abstract\n```\n\n"
        "## 4. 实验分析\n### 4.1 主结果表\n_待人工补_\n\n"
        "## 5. 创新性评估\n- 总评: _._/10\n\n"
        "## 7. 局限性\n- 显式: _待人工补_\n- 隐式: _待人工补_\n\n"
        "## 8. 创新机会\n1. _待人工补_\n\n"
        "## 10. 实施 / 部署建议\n- 落地关键障碍: _待人工补_\n"
    )


__all__ = [
    "generate_summary",
    "generate_deep_review",
    "is_ollama_ready",
]