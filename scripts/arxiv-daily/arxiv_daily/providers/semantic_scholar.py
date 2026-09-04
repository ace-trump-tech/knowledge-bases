"""Semantic Scholar Graph API client.

Free tier: 100 req / 5 minutes per IP. We cache results to disk to make repeated
runs cheap. When the rate limit blocks us, callers should fall back to OpenAlex.

``lookup_many`` prefers the ``/paper/batch`` endpoint (one POST, up to 500 ids)
because per-id sequential GETs blow past the free-tier rate limit the moment
we hand it a day's worth of arxiv listings (which is ~200 ids).
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from ..exceptions import ProviderError

LOGGER = logging.getLogger(__name__)

S2_ENDPOINT = "https://api.semanticscholar.org/graph/v1"
DEFAULT_TIMEOUT = 20.0
BATCH_PATH = "/paper/batch"
BATCH_FIELDS = "paperId,citationCount,influentialCitationCount,referenceCount,year"
BATCH_MAX_IDS = 500   # /paper/batch hard cap; we chunk larger requests
BATCH_SIZE = 100     # per-call batch size; smaller = friendlier to free tier
BATCH_CHUNK_PARALLELISM = 4   # concurrent chunks when input exceeds BATCH_SIZE


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
        """Return a map of arxiv_id -> S2 metadata; never raises.

        Splits input into chunks of ``BATCH_SIZE`` and POSTs each chunk to
        ``/paper/batch`` in parallel. Falls back to per-id GET for ids that
        the batch endpoint does not return (e.g. 404 from S2).
        """
        results: dict[str, SemanticScholarMeta] = {}
        unique_ids = [a for a in dict.fromkeys(arxiv_ids) if a]
        if not unique_ids:
            return results

        # 1. Serve from cache first; defer uncached ones to batch lookup.
        uncached: list[str] = []
        for aid in unique_ids:
            if aid in self._cache:
                cached = self._cache[aid]
                results[aid] = SemanticScholarMeta(
                    arxiv_id=aid,
                    s2_paper_id=cached.get("paperId"),
                    citation_count=cached.get("citationCount") or 0,
                    influential_citation_count=cached.get("influentialCitationCount") or 0,
                    reference_count=cached.get("referenceCount") or 0,
                    tweet_count=0,
                    year=cached.get("year"),
                )
            else:
                uncached.append(aid)

        # 2. Batch the rest. /paper/batch caps at 500 ids/call and our
        #    daily window is far below that, but chunk defensively so the
        #    tool works on larger backfills too.
        for aid in uncached:
            results.setdefault(aid, SemanticScholarMeta.empty(aid))

        chunks = [
            uncached[i : i + BATCH_SIZE]
            for i in range(0, len(uncached), BATCH_SIZE)
        ]
        if not chunks:
            self._maybe_persist_cache()
            return results

        def _fetch_chunk(chunk: list[str]) -> dict[str, dict]:
            try:
                return self._lookup_batch(chunk)
            except ProviderError as exc:
                LOGGER.warning("S2 batch failed (%d ids): %s", len(chunk), exc)
                return {}

        with ThreadPoolExecutor(
            max_workers=min(BATCH_CHUNK_PARALLELISM, len(chunks))
        ) as pool:
            futures = [pool.submit(_fetch_chunk, c) for c in chunks]
            for fut in as_completed(futures):
                batch_payload = fut.result()
                for aid, payload in batch_payload.items():
                    if not payload:
                        results[aid] = SemanticScholarMeta.empty(aid)
                        continue
                    self._cache[aid] = payload
                    results[aid] = SemanticScholarMeta(
                        arxiv_id=aid,
                        s2_paper_id=payload.get("paperId"),
                        citation_count=payload.get("citationCount") or 0,
                        influential_citation_count=payload.get("influentialCitationCount") or 0,
                        reference_count=payload.get("referenceCount") or 0,
                        tweet_count=0,
                        year=payload.get("year"),
                    )

        self._maybe_persist_cache()
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

    def _lookup_batch(self, arxiv_ids: list[str]) -> dict[str, dict]:
        """POST ``/paper/batch``; return ``{arxiv_id: payload_dict}``.

        Missing ids (or ``null`` entries in the response) are omitted from the
        returned map. The caller treats absence as "use empty meta".
        """
        if not arxiv_ids:
            return {}

        url = f"{self.endpoint.rstrip('/')}{BATCH_PATH}"
        body = {"ids": [f"ARXIV:{a}" for a in arxiv_ids]}

        attempt = 0
        while True:
            try:
                resp = self._session.post(
                    url,
                    params={"fields": BATCH_FIELDS},
                    json=body,
                    timeout=self.timeout,
                )
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
                    "S2 batch %s, retry %d (sleeping)", resp.status_code, attempt
                )
                time.sleep(self.backoff * (2 ** (attempt - 1)))
                continue

            if resp.status_code != 200:
                raise ProviderError(
                    "semanticscholar",
                    f"unexpected status {resp.status_code}: {resp.text[:200]}",
                    status=resp.status_code,
                )

            try:
                data = resp.json()
            except ValueError as exc:
                raise ProviderError("semanticscholar", f"bad json: {exc}") from exc

            # /paper/batch returns a list whose positions correspond to input
            # order, with ``null`` for missing ids.
            out: dict[str, dict] = {}
            for aid, payload in zip(arxiv_ids, data or []):
                if isinstance(payload, dict):
                    out[aid] = payload
            return out

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