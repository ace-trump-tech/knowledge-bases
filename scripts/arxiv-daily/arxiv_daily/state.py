"""Persistent state: which arxiv_ids have already been processed per KB.

A SHA-256 over the arxiv_id keeps the JSON compact and human-readable. Each
KB repo keeps a single ``arxiv-daily/state.json`` file committed alongside
the draft content.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .exceptions import StateCorrupt

LOGGER = logging.getLogger(__name__)

STATE_FILENAME = "arxiv-daily/state.json"


@dataclass
class StateEntry:
    arxiv_id: str
    first_seen: str                       # ISO date 'YYYY-MM-DD'
    short_sha256: str
    last_seen: str = ""
    rank_score: float = 0.0
    subtopic: str = ""
    note: str = ""

    def touch(self, iso_date: str, rank_score: float, subtopic: str) -> None:
        self.last_seen = iso_date
        self.rank_score = rank_score
        self.subtopic = subtopic


@dataclass
class KBState:
    schema_version: int = 1
    kb_repo: str = ""
    entries: dict[str, StateEntry] = field(default_factory=dict)

    # -- queries ------------------------------------------------------------

    def has(self, arxiv_id: str) -> bool:
        return arxiv_id in self.entries

    def ids(self) -> Iterable[str]:
        return self.entries.keys()

    # -- mutations ---------------------------------------------------------

    def mark(
        self,
        arxiv_id: str,
        *,
        iso_date: str,
        rank_score: float,
        subtopic: str,
        note: str = "",
    ) -> bool:
        """Return True if the entry is new (caller should process it)."""
        sha = hashlib.sha256(arxiv_id.encode("utf-8")).hexdigest()[:12]
        if arxiv_id in self.entries:
            self.entries[arxiv_id].touch(iso_date, rank_score, subtopic)
            return False
        self.entries[arxiv_id] = StateEntry(
            arxiv_id=arxiv_id,
            first_seen=iso_date,
            short_sha256=sha,
            last_seen=iso_date,
            rank_score=rank_score,
            subtopic=subtopic,
            note=note,
        )
        return True

    # -- persistence -------------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "kb_repo": self.kb_repo,
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
                "entries": {k: asdict(v) for k, v in self.entries.items()},
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "KBState":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StateCorrupt(f"state.json is not valid JSON: {exc}") from exc
        if raw.get("schema_version") != 1:
            raise StateCorrupt(
                f"unsupported schema_version {raw.get('schema_version')!r}"
            )
        entries_raw = raw.get("entries") or {}
        entries = {
            k: StateEntry(
                arxiv_id=v.get("arxiv_id", k),
                first_seen=v.get("first_seen", ""),
                short_sha256=v.get("short_sha256", ""),
                last_seen=v.get("last_seen", ""),
                rank_score=float(v.get("rank_score", 0.0)),
                subtopic=v.get("subtopic", ""),
                note=v.get("note", ""),
            )
            for k, v in entries_raw.items()
        }
        return cls(
            schema_version=1,
            kb_repo=raw.get("kb_repo", ""),
            entries=entries,
        )


def load_state(path: Path) -> KBState:
    if not path.exists():
        return KBState()
    return KBState.from_json(path.read_text(encoding="utf-8"))


def save_state(state: KBState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.to_json(), encoding="utf-8")


__all__ = ["KBState", "StateEntry", "STATE_FILENAME", "load_state", "save_state"]