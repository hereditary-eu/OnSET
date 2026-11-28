"""Edit histories saved with a session (ontology builder sessions, query sessions).

The history entries are made by the frontend (utils/builder/history.ts, utils/sparql/history.ts):
each has a snapshot of the edited state, who made the change (provenance) and the change itself.
The server keeps them as opaque JSON, keyed by the entry's own ``timestamp`` (the client's epoch
ms, unique within a history), and adds when it first stored and last updated an entry
(``created_at``/``updated_at``, the server's epoch ms). Clients send changes as a
``HistoryUpdate``: entries to add or replace (a coalesced edit replaces the entry with the same
timestamp) and timestamps to remove.
"""

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# session ids are file names in the save dirs: no dots or slashes (path traversal, suffixes)
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
# entries kept per history (the oldest are dropped first)
MAX_HISTORY_ENTRIES = 1000


def check_session_id(session_id: str) -> str:
    """``session_id`` if it is a valid session id (ValueError otherwise)."""
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError(f"Invalid session id '{session_id}' (letters, digits, '-' and '_' only, at most 64)")
    return session_id


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def write_atomic(path: Path, text: str):
    """Write ``text`` to ``path`` through a temporary file, so a crash leaves the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


class HistoryEntryIn(BaseModel):
    # the entry's own timestamp (client epoch ms), its key in the history
    timestamp: int
    # the client's entry (opaque to the server)
    entry: Any


class HistoryRecord(HistoryEntryIn):
    # server epoch ms of the first and the last time the entry was stored
    created_at: int
    updated_at: int


class HistoryUpdate(BaseModel):
    # applied in this order: clear, remove, upsert
    clear: bool = False
    remove: list[int] = Field(default_factory=list)
    upsert: list[HistoryEntryIn] = Field(default_factory=list)


class HistoryInfo(BaseModel):
    entries: int
    # bumped on every change, so another client of the session knows to refetch
    version: int
    updated_at: int | None = None


class EditHistory:
    """The history entries of one session, ordered by their timestamp (thread-safe)."""

    def __init__(self, records: list[dict] | None = None, max_entries: int = MAX_HISTORY_ENTRIES):
        self.max_entries = max_entries
        self.version = 0
        self._records: dict[int, HistoryRecord] = {}
        self._lock = threading.Lock()
        for raw in records or []:
            record = HistoryRecord(**raw)
            self._records[record.timestamp] = record
        self._trim()

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> list[HistoryRecord]:
        with self._lock:
            return [self._records[t].model_copy() for t in sorted(self._records)]

    def info(self) -> HistoryInfo:
        with self._lock:
            updated = max((r.updated_at for r in self._records.values()), default=None)
            return HistoryInfo(entries=len(self._records), version=self.version, updated_at=updated)

    def apply(self, update: HistoryUpdate, now: int | None = None) -> bool:
        """Apply ``update``; whether it changed the history."""
        now = now if now is not None else now_ms()
        with self._lock:
            changed = False
            if update.clear and self._records:
                self._records.clear()
                changed = True
            for timestamp in update.remove:
                changed |= self._records.pop(timestamp, None) is not None
            for item in update.upsert:
                old = self._records.get(item.timestamp)
                if old is not None and old.entry == item.entry:
                    continue
                self._records[item.timestamp] = HistoryRecord(
                    timestamp=item.timestamp, entry=item.entry,
                    created_at=old.created_at if old is not None else now, updated_at=now,
                )
                changed = True
            changed |= self._trim()
            if changed:
                self.version += 1
            return changed

    def _trim(self) -> bool:
        excess = len(self._records) - self.max_entries
        for timestamp in sorted(self._records)[:max(excess, 0)]:
            del self._records[timestamp]
        return excess > 0

    def dump(self) -> list[dict]:
        return [r.model_dump(mode="json") for r in self.records()]

    def dumps(self) -> str:
        return json.dumps(self.dump())
