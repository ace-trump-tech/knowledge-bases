"""Configuration loader for arxiv-daily.

A YAML file declares:

  kb_repo:         <owner>/<name>            # GitHub repo to receive the draft PR
  kb_local_path:   <path>                    # local path of the submodule
  arxiv_categories: [...]                    # cs.CV etc.
  fetch_window_hours: 26                     # how far back to look each run
  top_n_per_subtopic: 3
  deep_review_threshold: 80                  # composite score threshold
  subtopics:
    - id: <folder-name>                      # matches KB's `idea/<id>/`
      keywords: [...]                        # English/Chinese synonyms
      description: <one-line>                # used in the LLM classification prompt
  ollama_model: qwen2.5:14b                  # optional override
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import yaml

from .exceptions import ConfigError


@dataclass(frozen=True)
class SubtopicConfig:
    id: str
    keywords: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class KBConfig:
    name: str                          # 'driver-kb'
    kb_repo: str                       # 'ace-trump-tech/driver-kb'
    kb_local_path: Path                # '<repo>/bases/driver-kb'
    arxiv_categories: tuple[str, ...]
    subtopics: tuple[SubtopicConfig, ...]
    fetch_window_hours: int = 26
    top_n_per_subtopic: int = 3
    deep_review_threshold: float = 80.0
    ollama_model: str = "qwen2.5:14b"

    @property
    def owner(self) -> str:
        return self.kb_repo.split("/", 1)[0]

    @property
    def repo(self) -> str:
        return self.kb_repo.split("/", 1)[1]


def load_config(path: str | Path) -> KBConfig:
    p = Path(path).resolve()
    if not p.exists():
        raise ConfigError(f"config not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping: {p}")

    name = p.stem
    kb_repo = raw.get("kb_repo")
    kb_local_path = raw.get("kb_local_path")
    if not kb_repo or "/" not in kb_repo:
        raise ConfigError(f"`kb_repo` must be set to '<owner>/<name>' in {p}")
    if not kb_local_path:
        raise ConfigError(f"`kb_local_path` must be set in {p}")

    subtopics_raw = raw.get("subtopics")
    if not isinstance(subtopics_raw, list) or not subtopics_raw:
        raise ConfigError(f"`subtopics` must be a non-empty list in {p}")
    subtopics = tuple(
        SubtopicConfig(
            id=str(item["id"]),
            keywords=tuple(str(k).lower() for k in item.get("keywords", []) if k),
            description=str(item.get("description", "")).strip(),
        )
        for item in subtopics_raw
    )

    cats = raw.get("arxiv_categories") or []
    if not isinstance(cats, list) or not cats:
        raise ConfigError(f"`arxiv_categories` must be a non-empty list in {p}")

    return KBConfig(
        name=name,
        kb_repo=kb_repo,
        # Resolve ``kb_local_path`` against the config file's grandparent so the
        # result is independent of the caller's working directory. The
        # ``publish`` step runs after ``cd bases/<kb>``, where a bare
        # ``./bases/<kb>`` would resolve to ``bases/<kb>/bases/<kb>`` and miss
        # the submodule checkout entirely.
        kb_local_path=_resolve_local_path(p, kb_local_path),
        arxiv_categories=tuple(str(c) for c in cats),
        subtopics=subtopics,
        fetch_window_hours=int(raw.get("fetch_window_hours", 26)),
        top_n_per_subtopic=int(raw.get("top_n_per_subtopic", 3)),
        deep_review_threshold=float(raw.get("deep_review_threshold", 80.0)),
        ollama_model=str(raw.get("ollama_model", "qwen2.5:14b")),
    )


def _resolve_local_path(config_path: Path, raw_path: str) -> Path:
    """Resolve ``raw_path`` (relative) against the config file's grandparent.

    The configs live at ``<repo>/scripts/arxiv-daily/config/<kb>.yaml``; their
    grandparent is the repo root. ``./bases/driver-kb`` is therefore always
    resolved to ``<repo>/bases/driver-kb`` regardless of where the caller is
    cd'd to (fetch step runs from the repo root, publish step runs from
    inside the submodule).
    """
    p = Path(raw_path)
    if p.is_absolute():
        return p.resolve()
    repo_root = config_path.parents[3]  # config/arxiv-daily/scripts/<repo>
    return (repo_root / p).resolve()


__all__ = ["KBConfig", "SubtopicConfig", "load_config"]