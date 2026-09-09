"""
SONIC-REDA — Being Craft (durable toolkit / authored artifacts)
===============================================================

The "craft" part of the AI human: durable artifacts the being authors on its
own initiative (notes, observations, reusable scripts) that persist on the HOST
filesystem, keyed by being_id — so the being builds up a personal toolkit that
survives restart, distinct from disposable in-sandbox research outputs.

Before this, evolution/dev outputs were written only into disposable sandboxes
(/home/sonic/workspace) and became durable only via git commits. There was no
host-side "notes" or "scripts" home for the being itself. A being with no
durable craft is an amnesiac worker.

Persistence: host filesystem under ``sonic_data/craft/<being_id>/`` (env
``SONIC_DATA_DIR``, mirroring the workstation state file convention). Each note
is one file; an index is kept in memory + written as ``index.json``. This is
deliberately simple and inspectable — a human can read the being's notes
directly off disk.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sonic.logger import get_logger

logger = get_logger(__name__)


def _craft_root() -> str:
    base = os.environ.get("SONIC_DATA_DIR", "sonic_data")
    return os.path.join(base, "craft")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class CraftNote:
    """A single durable artifact authored by the being."""
    note_id: str
    being_id: str
    title: str
    body: str
    kind: str = "note"            # note | script | observation | reflection
    created_at: str = ""
    updated_at: str = ""


class BeingCraft:
    """Host-side durable craft store for a being.

    Files live under ``sonic_data/craft/<being_id>/``; an ``index.json`` lists
    metadata so the being can recall what it has authored without re-scanning.
    """

    def __init__(self, being_id: str, root: str | None = None):
        self.being_id = being_id
        self._root = root or os.path.join(_craft_root(), being_id)
        self._index: dict[str, CraftNote] = {}
        os.makedirs(self._root, exist_ok=True)
        self._load_index()

    # ------------------------------------------------------------------
    def _index_path(self) -> str:
        return os.path.join(self._root, "index.json")

    def _note_path(self, note_id: str) -> str:
        return os.path.join(self._root, f"{note_id}.md")

    def _load_index(self) -> None:
        path = self._index_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("notes", []):
                n = CraftNote(**entry)
                self._index[n.note_id] = n
        except Exception as e:
            logger.warning("craft_index_load_failed", being_id=self.being_id, error=str(e))

    def _save_index(self) -> None:
        with open(self._index_path(), "w", encoding="utf-8") as f:
            json.dump({"notes": [n.__dict__ for n in self._index.values()]}, f, indent=2)

    # ------------------------------------------------------------------
    def author(self, title: str, body: str, kind: str = "note") -> CraftNote:
        """Author a new durable note. Write-through to disk immediately."""
        note_id = f"note-{int(time.time() * 1000)}"
        ts = _now()
        note = CraftNote(
            note_id=note_id, being_id=self.being_id, title=title, body=body,
            kind=kind, created_at=ts, updated_at=ts,
        )
        # Write the note body (markdown, human-readable on disk).
        with open(self._note_path(note_id), "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n_kind: {kind}_\n_created: {ts}_\n\n{body}\n")
        self._index[note_id] = note
        self._save_index()
        logger.info("craft_authored", being_id=self.being_id,
                    note_id=note_id, kind=kind, title=title[:60])
        return note

    def list_notes(self) -> list[CraftNote]:
        return list(self._index.values())

    def get_note(self, note_id: str) -> CraftNote | None:
        n = self._index.get(note_id)
        if n is None:
            return None
        # Re-read body from disk (authoritative).
        try:
            with open(self._note_path(note_id), encoding="utf-8") as f:
                n.body = f.read()
        except FileNotFoundError:
            pass
        return n

    def update_note(self, note_id: str, body: str | None = None,
                    title: str | None = None) -> CraftNote | None:
        n = self._index.get(note_id)
        if n is None:
            return None
        if body is not None:
            n.body = body
        if title is not None:
            n.title = title
        n.updated_at = _now()
        with open(self._note_path(note_id), "w", encoding="utf-8") as f:
            f.write(f"# {n.title}\n\n_kind: {n.kind}_\n_created: {n.created_at}_\n_updated: {n.updated_at}_\n\n{n.body}\n")
        self._save_index()
        return n
