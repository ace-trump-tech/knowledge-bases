"""Semantic Scholar Graph API client.

Free tier: 100 req / 5 minutes per IP. We cache results to disk to make repeated
runs cheap. When the rate limit blocks us, callers should fall back to OpenAlex.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..exceptions import ProviderError

LOGGER = logging.getLogger(__name__)

S2_ENDPOINT = "https://api.semanticscholar.org/graph/v1"
DEFAULT_TIMEOUT = 20.0


@dataclass(frozen=True)
class SemanticScholarMeta:
    arxiv_id: str
    s2_paper_id: Optional[str]
    citation_count: int
    influential_citation_count: int
    reference_count: int
    tweet_count: int
    year: Optional[int]

    def to_dict(self) -> dict:
        return {
            "arxiv_id": self.arxiv_id,
            "s2_paper_id": self.s2_paper_id,
            "citation_count": self.citation_count,
            "influential_citation_count": self.influential_citation_count,
            "reference_count": self.reference_count,
            "tweet_count": self.tweet_count,
            "year": self.year,
        }

    @classmethod
    def empty(cls, arxiv_id: str) -> "SemanticScholarMeta":
        return cls(arxiv_id, None, 0, 0, 0, 0, None)


class SemanticScholarClient:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        endpoint: str = S2_ENDPOINT,
        timeout: float = DEFAULT_TIMEOUT,
        cache_path: Optional[Path] = None,
        max_retries: int = 3,
        backoff_seconds: float = 3.0,
    ) -> None:
        import requests

        self.endpoint = endpoint
        self.timeout = timeout
        self.api_key = api_key
        self.max_retries = max_retries
        self.backoff = backoff_seconds
        self._session = requests.Session()
        if api_key:
            self._session.headers.update({"x-api-key": api_key})
        self._session.headers.update({"User-Agent": "arxiv-daily/0.1"})

        self._cache_path = cache_path
        self._cache: dict[str, dict] = {}
        if cache_path:
            self._load_cache(cache_path)

    # -- public -----------------------------------------------------------

    def lookup_many(self, arxiv_ids: list[str]) -> dict[str, SemanticScholarMeta]:
        """Return a map of arxiv_id -> S2 metadata; never raises."""
        results: dict[str, SemanticScholarMeta] = {}
        for aid in arxiv_ids:
            results[aid] = self._lookup_one(aid) or SemanticScholarMeta.empty(aid)
        return results

    # -- internal ---------------------------------------------------------

    def _lookup_one(self, arxiv_id: str) -> Optional[SemanticScholarMeta]:
        if arxiv_id in self._cache:
            cached = self._cache[arxiv_id]
            return SemanticScholarMeta(
                arxiv_id=arxiv_id,
                s2_paper_id=cached.get("paperId"),
                citation_count=cached.get("citationCount") or 0,
                influential_citation_count=cached.get("influentialCitationCount") or 0,
                reference_count=cached.get("referenceCount") or 0,
                tweet_count=_safe_int((cached.get("citationStyles") or {}).get("Tweet")),
                year=cached.get("year"),
            )

        url = f"{self.endpoint}/paper/arXiv:{arxiv_id}"
        params = {
            "fields": "paperId,citationCount,influentialCitationCount,referenceCount,year"
        }
        try:
            payload = self._get_with_retry(url, params)
        except ProviderError as exc:
            LOGGER.warning("S2 lookup failed for %s: %s", arxiv_id, exc)
            return None

        if not payload:
            return None
        self._cache[arxiv_id] = payload
        self._maybe_persist_cache()

        return SemanticScholarMeta(
            arxiv_id=arxiv_id,
            s2_paper_id=payload.get("paperId"),
            citation_count=payload.get("citationCount") or 0,
            influential_citation_count=payload.get("influentialCitationCount") or 0,
            reference_count=payload.get("referenceCount") or 0,
            tweet_count=0,
            year=payload.get("year"),
        )

    def _get_with_retry(self, url: str, params: dict) -> Optional[dict]:
        import requests

        attempt = 0
        while True:
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise ProviderError("semanticscholar", f"network: {exc}") from exc
                attempt += 1
                time.sleep(self.backoff * (2 ** (attempt - 1)))
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= self.max_retries:
                    raise ProviderError(
                        "semanticscholar",
                        "rate-limited or server-error after exhausting retries",
                        status=resp.status_code,
                    )
                attempt += 1
                LOGGER.warning(
                    "S2 %s, retry %d (sleeping)", resp.status_code, attempt
                )
                time.sleep(self.backoff * (2 ** (attempt - 1)))
                continue

            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                raise ProviderError(
                    "semanticscholar",
                    f"unexpected status {resp.status_code}: {resp.text[:200]}",
                    status=resp.status_code,
                )
            return resp.json()

    # -- disk cache -------------------------------------------------------

    def _load_cache(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            self._cache = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning("S2 cache at %s is corrupt; ignoring", path)
            self._cache = {}

    def _maybe_persist_cache(self) -> None:
        if self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._cache, indent=2, sort_keys=True), encoding="utf-8"
        )


def _safe_int(value) -> int:  # noqa: ANN001
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


__all__ = ["SemanticScholarClient", "SemanticScholarMeta", "S2_ENDPOINT"]