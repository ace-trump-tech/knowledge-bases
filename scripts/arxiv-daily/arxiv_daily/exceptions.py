from __future__ import annotations
"""Exceptions raised by the arxiv-daily pipeline."""


class ArxivDailyError(Exception):
    """Base exception for the arxiv-daily package."""


class ConfigError(ArxivDailyError):
    """A YAML configuration file is malformed or missing required fields."""


class ProviderError(ArxivDailyError):
    """An upstream provider (arXiv, Semantic Scholar, ollama) returned an error."""

    def __init__(self, provider: str, message: str, *, status: int | None = None) -> None:
        super().__init__(f"[{provider}] {message}" + (f" (HTTP {status})" if status else ""))
        self.provider = provider
        self.status = status


class ClassificationError(ArxivDailyError):
    """Both classification legs (keyword + LLM) failed to converge on a subtopic."""


class StateCorrupt(ArxivDailyError):
    """The state.json file is malformed."""


class GitHubAuthError(ArxivDailyError):
    """Missing or invalid GitHub credentials for the publisher."""