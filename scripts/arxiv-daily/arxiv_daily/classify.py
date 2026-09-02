"""Subtopic classification: keyword TF-IDF (always on) + ollama vote (optional).

The ollama leg is best-effort: when the local model is unreachable we fall back
to keyword scoring alone, but mark confidence as low so callers can route the
paper into the ``unclassified`` bucket.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .config import KBConfig, SubtopicConfig
from .providers.ollama import OllamaClient, OllamaUnavailable
from .providers.ollama import OllamaResponse

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Classification:
    subtopic_id: str | None    # None means 'unclassified'
    confidence: float          # 0..1
    method: str                # 'keyword+ollama', 'keyword-only', 'unclassified'

    @property
    def is_confident(self) -> bool:
        return self.subtopic_id is not None and self.confidence >= 0.6


_TOKEN_RE = re.compile(r"[a-z0-9一-鿿]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _keyword_score(paper_text: str, subtopic: SubtopicConfig) -> float:
    """Crude weighted Jaccard over the subtopic keyword list."""
    text_tokens = set(_tokenize(paper_text))
    kw_tokens: set[str] = set()
    for kw in subtopic.keywords:
        kw_tokens.update(_tokenize(kw))
    if not kw_tokens:
        return 0.0
    overlap = text_tokens & kw_tokens
    return len(overlap) / math.sqrt(len(kw_tokens) * max(1, len(text_tokens)))


def keyword_classify(
    paper_text: str,
    subtopics: Iterable[SubtopicConfig],
) -> tuple[str | None, float]:
    """Return (best_subtopic_id, score) or (None, 0) if all zero."""
    scored = [
        (st.id, _keyword_score(paper_text, st)) for st in subtopics
    ]
    if not scored:
        return None, 0.0
    scored.sort(key=lambda x: x[1], reverse=True)
    best_id, best_score = scored[0]
    if best_score <= 0:
        return None, 0.0
    return best_id, min(1.0, best_score * 4)   # rescale to ~0..1


def ollama_classify(
    paper_text: str,
    cfg: KBConfig,
    *,
    client: OllamaClient,
) -> tuple[str | None, float]:
    """Ask ollama which subtopic fits, return (subtopic_id, 0..1 confidence)."""
    desc_lines = "\n".join(
        f"- {st.id}: {st.description or ' '.join(st.keywords[:5])}"
        for st in cfg.subtopics
    )
    prompt = (
        "You classify new arXiv papers into one of the following subtopics of "
        f"the `{cfg.name}` knowledge base.\n\n"
        f"{desc_lines}\n\n"
        "Paper:\n"
        f"---\n{paper_text[:1800]}\n---\n\n"
        "Reply with STRICT JSON only (no markdown fence): "
        '{"subtopic": "<id>", "confidence": <0..1>}\n'
        "Pick `null` if nothing matches."
    )
    try:
        resp: OllamaResponse = client.generate(
            prompt,
            system="You are a precise classifier. Output strict JSON.",
        )
    except OllamaUnavailable as exc:
        LOGGER.warning("ollama unavailable for %s: %s", cfg.name, exc)
        return None, 0.0

    return _parse_json_response(resp.text, valid_ids={st.id for st in cfg.subtopics})


_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_json_response(text: str, *, valid_ids: set[str]) -> tuple[str | None, float]:
    match = _JSON_RE.search(text)
    if not match:
        return None, 0.0
    import json

    try:
        js = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, 0.0
    sub = js.get("subtopic")
    conf = js.get("confidence", 0.0)
    if sub in (None, "null", ""):
        return None, 0.0
    if sub not in valid_ids:
        return None, 0.0
    try:
        conf_f = max(0.0, min(1.0, float(conf)))
    except (TypeError, ValueError):
        conf_f = 0.0
    return str(sub), conf_f


def classify_paper(
    paper_text: str,
    cfg: KBConfig,
    *,
    ollama: OllamaClient | None,
) -> Classification:
    """Combine keyword + LLM legs; require both to agree for confidence."""
    kw_id, kw_conf = keyword_classify(paper_text, cfg.subtopics)
    if ollama is None:
        method = "keyword-only"
        llm_id, llm_conf = None, 0.0
    else:
        llm_id, llm_conf = ollama_classify(paper_text, cfg, client=ollama)

    if kw_id and llm_id and kw_id == llm_id:
        conf = (kw_conf + llm_conf) / 2
        return Classification(subtopic_id=kw_id, confidence=conf, method="keyword+ollama")

    if kw_id and not llm_id:
        # ollama unavailable; trust keyword with a confidence cap
        return Classification(subtopic_id=kw_id, confidence=min(kw_conf, 0.5), method="keyword-only")

    if kw_id and llm_id and kw_id != llm_id:
        # disagreement -> keyword wins but confidence is low
        return Classification(subtopic_id=kw_id, confidence=min(kw_conf, 0.4), method="keyword+ollama-disagree")

    if not kw_id and llm_id:
        return Classification(subtopic_id=llm_id, confidence=min(llm_conf, 0.5), method="ollama-only")

    return Classification(subtopic_id=None, confidence=0.0, method="unclassified")


__all__ = [
    "Classification",
    "classify_paper",
    "keyword_classify",
    "ollama_classify",
]