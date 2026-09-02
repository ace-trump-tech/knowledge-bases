"""arXiv API client (Atom XML).

Uses the public endpoint http://export.arxiv.org/api/query. We deliberately
keep this thin: parse the Atom feed, expose a typed dataclass, retry on 429.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Iterator, Sequence

import feedparser

from ..exceptions import ProviderError

LOGGER = logging.getLogger(__name__)

ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
DEFAULT_TIMEOUT = 60.0
USER_AGENT = "arxiv-daily/0.1 (+https://github.com/ace-trump-tech/knowledge-bases)"


@dataclass(frozen=True)
class ArxivPaper:
    """A single arXiv listing."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    primary_category: str
    published: datetime
    updated: datetime
    pdf_url: str
    abs_url: str
    comment: str = ""

    def short_id(self) -> str:
        """Return arxiv_id without the version suffix (e.g. '2403.12345')."""
        base = self.arxiv_id.split("v")[0]
        # old-style 'cs.CV/0405001' already has no 'v'
        return base

    def to_dict(self) -> dict:
        return {
            "arxiv_id": self.arxiv_id,
            "short_id": self.short_id(),
            "title": self.title,
            "authors": list(self.authors),
            "abstract": self.abstract,
            "categories": list(self.categories),
            "primary_category": self.primary_category,
            "published": self.published.isoformat(),
            "updated": self.updated.isoformat(),
            "pdf_url": self.pdf_url,
            "abs_url": self.abs_url,
            "comment": self.comment,
        }


def _strip_versioned_id(raw: str) -> str:
    """Normalise the various arXiv id forms to 'YYMM.NNNNN' (or 'cat/YYMMNNN')."""
    raw = raw.strip()
    # 'http://arxiv.org/abs/2403.12345v2' or '.../abs/2403.12345'
    if "/abs/" in raw:
        raw = raw.rsplit("/abs/", 1)[-1]
    elif "/pdf/" in raw:
        raw = raw.rsplit("/pdf/", 1)[-1]
    # strip trailing '.pdf'
    if raw.endswith(".pdf"):
        raw = raw[:-4]
    return raw


def _parse_entry(entry: feedparser.FeedParserDict) -> ArxivPaper:
    arxiv_id = _strip_versioned_id(entry.get("id", ""))
    title = " ".join(entry.get("title", "").split())
    abstract = " ".join(entry.get("summary", "").split())
    authors = [a.get("name", "").strip() for a in entry.get("authors", []) if a.get("name")]
    categories = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
    primary = entry.get("arxiv_primary_category", {}).get("term") or (categories[0] if categories else "")

    published = _ensure_utc(entry.get("published_parsed"))
    updated = _ensure_utc(entry.get("updated_parsed"))

    pdf_url = ""
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break
    if not pdf_url:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    abs_url = entry.get("link", "") or f"https://arxiv.org/abs/{arxiv_id}"
    abs_url = abs_url.replace("http://arxiv.org/", "https://arxiv.org/")

    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=abstract,
        categories=categories,
        primary_category=primary,
        published=published,
        updated=updated,
        pdf_url=pdf_url,
        abs_url=abs_url,
        comment=entry.get("arxiv_comment", ""),
    )


def _ensure_utc(struct_time) -> datetime:
    if struct_time is None:
        return datetime.now(tz=timezone.utc)
    return datetime(*struct_time[:6], tzinfo=timezone.utc)


class ArxivClient:
    """Thin HTTP client for the arXiv API. Stateless apart from a requests session."""

    def __init__(
        self,
        *,
        endpoint: str = ARXIV_ENDPOINT,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = USER_AGENT,
        max_retries: int = 4,
        backoff_seconds: float = 5.0,
    ) -> None:
        import requests

        self.endpoint = endpoint
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.backoff = backoff_seconds
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent})

    def query(
        self,
        *,
        categories: Sequence[str],
        submitted_after: datetime,
        submitted_before: datetime | None = None,
        max_results: int = 200,
        extra_terms: Iterable[str] = (),
    ) -> list[ArxivPaper]:
        """Fetch all papers in ``categories`` submitted in [after, before]."""
        submitted_before = submitted_before or datetime.now(tz=timezone.utc)

        cat_clause = "+OR+".join(f"cat:{c}" for c in categories)
        date_range = (
            f"submittedDate:"
            f"[{submitted_after.strftime('%Y%m%d%H%M')}+TO+"
            f"{submitted_before.strftime('%Y%m%d%H%M')}]"
        )
        search_query = f"({cat_clause})+AND+{date_range}"
        for term in extra_terms:
            search_query += f"+AND+all:{term}"

        papers: list[ArxivPaper] = []
        start = 0
        page_size = min(100, max_results)
        while start < max_results:
            params = {
                "search_query": search_query,
                "start": start,
                "max_results": page_size,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            payload = self._get_with_retry(params)
            feed = feedparser.parse(payload)
            if feed.bozo and not feed.entries:
                raise ProviderError(
                    "arxiv", f"feed parse error: {feed.bozo_exception}", status=None
                )
            page = [_parse_entry(e) for e in feed.entries]
            if not page:
                break
            papers.extend(page)
            if len(page) < page_size:
                break
            start += page_size
        return papers[:max_results]

    def _get_with_retry(self, params: dict) -> bytes:
        import requests

        attempt = 0
        while True:
            try:
                resp = self._session.get(
                    self.endpoint, params=params, timeout=self.timeout
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise ProviderError("arxiv", f"network: {exc}") from exc
                attempt += 1
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= self.max_retries:
                    raise ProviderError(
                        "arxiv",
                        "rate-limited or server-error after exhausting retries",
                        status=resp.status_code,
                    )
                attempt += 1
                LOGGER.warning("arxiv %s, retry %d", resp.status_code, attempt)
                self._sleep_backoff(attempt)
                continue

            if resp.status_code != 200:
                raise ProviderError(
                    "arxiv",
                    f"unexpected status {resp.status_code}: {resp.text[:200]}",
                    status=resp.status_code,
                )
            return resp.content

    def _sleep_backoff(self, attempt: int) -> None:
        time.sleep(self.backoff * (2 ** (attempt - 1)))

    def iter_in_batches(self, **kwargs) -> Iterator[ArxivPaper]:
        yield from self.query(**kwargs)


__all__ = ["ArxivClient", "ArxivPaper", "ARXIV_ENDPOINT"]