"""
SONIC-REDA — Persistent Being (the "AI Human" identity layer)
==============================================================

Builds the smallest real piece of an "AI human" on top of the proven
foundation (Phase 1 persistent Mind + Phase 2 persistent Body + Phase 6
safety envelope): a STABLE BEING that survives restart.

Before this module, `agent_id` was a per-instance UUID (or the literal
"computer-use-agent") minted fresh on every boot — so each restart the system
became a brand-new tool with no continuity. A being that forgets its own
identity on restart is not alive. This fixes that:

    * `Being`           — stable identity (being_id, name, tenant_id, born_at)
                          persisted to SQLite, reloaded on boot.
    * `BeingMind`       — the being's cross-session cognitive affect: a mood
                          curve, curiosity drive, learned-facts ledger, and a
                          running tally of idle/curiosity cycles. Persisted to
                          SQLite (write-through), survives restart — distinct
                          from the per-engagement `CognitiveState` (Redis-TTL'd).
    * `get_or_create_being()` — the boot re-attach: returns the persisted being
                          for a tenant or provisions one on first contact.

Persistence follows the established Phase-1 pattern: stdlib `sqlite3` +
write-through + read-cache + `reset_being_singleton()`, reusing
`_default_db_path()` so it shares `sonic_data.db` with the graph/vector/
evolution stores. It deliberately does NOT use Redis (TTL'd, not durable).

The being owns its idle/curiosity tick: a long-lived loop that runs when no
operator goal is active, pursuing self-directed novelty through the REAL
observe->reason->act loop — and (critically) every autonomous action still
passes the Phase-6 `ActionPolicy` safety envelope, so the being cannot escape
it when "left to its own devices".
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sonic.logger import get_logger

logger = get_logger(__name__)


def _default_db_path() -> str:
    """Reuse the shared SONIC SQLite path (env SONIC_MEMORY_DB_PATH > DATABASE_URL
    > ./sonic_data.db) so the being shares its mind-store with graph/vector."""
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_BEING_DB_PATH") or os.environ.get("SONIC_MEMORY_DB_PATH") or _g()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class Being:
    """Stable persistent identity for the AI being. Survives restart.

    A being is scoped to a tenant (the human/org it serves) — a tenant may have
    exactly one being. The being is NOT the tenant: the tenant is the human
    account; the being is the autonomous entity that persists on their behalf.
    """
    being_id: str
    name: str
    tenant_id: str
    born_at: str
    # Last boot re-attach timestamp (proves the identity re-resolved, not reminted).
    last_attached_at: str = ""


@dataclass
class BeingMind:
    """The being's cross-session cognitive affect — the part of "mind" that is
    NOT engagement-specific. Distinct from `agents/cognitive_state.py:CognitiveState`
    (which is per-engagement and Redis-TTL'd at 24h).

    Persisted write-through so a restart does not wipe the being's mood,
    curiosity drive, or what it has learned about the world on its own.
    """
    being_id: str
    # Mood / drive (0.0–1.0). Curiosity high = wants to explore; focus high =
    # wants to finish open work. These evolve with idle cycles, not reset.
    curiosity_drive: float = 0.7
    focus: float = 0.5
    satiety: float = 0.5          # "how much it has recently learned" — boredom inverse
    # Cross-session ledger of self-directed learnings (not engagement findings).
    learned_facts: list[str] = field(default_factory=list)
    # Running tallies.
    idle_cycles_run: int = 0
    goals_pursued: int = 0
    last_idle_at: str = ""


# ---------------------------------------------------------------------------
# Persistent store (SQLite write-through + read cache, mirrors VectorMemory)
# ---------------------------------------------------------------------------

class BeingStore:
    """SQLite-backed durable store for Being identity + BeingMind.

    One row per being (keyed by being_id). The in-memory caches are read-only
    mirrors hydrated on init and kept in sync on every write-through — no state
    is required across restarts.
    """

    def __init__(self, db_path: Optional[str] = None, persist: bool = True):
        self.persist = persist
        self._db_path = db_path or (_default_db_path() if persist else None)
        self._db: Optional[sqlite3.Connection] = None
        self._being_cache: dict[str, Being] = {}
        self._mind_cache: dict[str, BeingMind] = {}
        if persist:
            self._open_db()

    # -- schema + hydrate -------------------------------------------------
    def _open_db(self) -> None:
        if self._db is not None or not self.persist:
            return
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS beings ("
            "being_id TEXT PRIMARY KEY, name TEXT, tenant_id TEXT, "
            "born_at TEXT NOT NULL, last_attached_at TEXT NOT NULL)"
        )
        self._db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_beings_tenant ON beings(tenant_id)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS being_minds ("
            "being_id TEXT PRIMARY KEY, mind_json TEXT NOT NULL)"
        )
        self._db.commit()
        for row in self._db.execute(
            "SELECT being_id, name, tenant_id, born_at, last_attached_at FROM beings"
        ).fetchall():
            b = Being(being_id=row[0], name=row[1], tenant_id=row[2],
                      born_at=row[3], last_attached_at=row[4])
            self._being_cache[b.being_id] = b
        for being_id, mind_json in self._db.execute(
            "SELECT being_id, mind_json FROM being_minds"
        ).fetchall():
            import json
            data = json.loads(mind_json)
            self._mind_cache[being_id] = BeingMind(
                being_id=being_id,
                curiosity_drive=data.get("curiosity_drive", 0.7),
                focus=data.get("focus", 0.5),
                satiety=data.get("satiety", 0.5),
                learned_facts=data.get("learned_facts", []),
                idle_cycles_run=data.get("idle_cycles_run", 0),
                goals_pursued=data.get("goals_pursued", 0),
                last_idle_at=data.get("last_idle_at", ""),
            )

    # -- Being CRUD -------------------------------------------------------
    def get_being(self, being_id: str) -> Optional[Being]:
        return self._being_cache.get(being_id)

    def get_being_for_tenant(self, tenant_id: str) -> Optional[Being]:
        for b in self._being_cache.values():
            if b.tenant_id == tenant_id:
                return b
        return None

    def save_being(self, being: Being) -> None:
        self._being_cache[being.being_id] = being
        if not self.persist or self._db is None:
            return
        self._db.execute(
            "INSERT INTO beings (being_id, name, tenant_id, born_at, last_attached_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(being_id) DO UPDATE SET "
            "name=excluded.name, last_attached_at=excluded.last_attached_at",
            (being.being_id, being.name, being.tenant_id, being.born_at, being.last_attached_at),
        )
        self._db.commit()

    def touch_attached(self, being_id: str) -> None:
        b = self._being_cache.get(being_id)
        if b is None:
            return
        b.last_attached_at = _now()
        self.save_being(b)

    # -- BeingMind CRUD ---------------------------------------------------
    def get_mind(self, being_id: str) -> BeingMind:
        mind = self._mind_cache.get(being_id)
        if mind is None:
            mind = BeingMind(being_id=being_id)
            self._mind_cache[being_id] = mind
            self._persist_mind(mind)
        return mind

    def save_mind(self, mind: BeingMind) -> None:
        self._mind_cache[mind.being_id] = mind
        self._persist_mind(mind)

    def _persist_mind(self, mind: BeingMind) -> None:
        if not self.persist or self._db is None:
            return
        import json
        payload = json.dumps({
            "curiosity_drive": mind.curiosity_drive,
            "focus": mind.focus,
            "satiety": mind.satiety,
            "learned_facts": mind.learned_facts,
            "idle_cycles_run": mind.idle_cycles_run,
            "goals_pursued": mind.goals_pursued,
            "last_idle_at": mind.last_idle_at,
        })
        self._db.execute(
            "INSERT INTO being_minds (being_id, mind_json) VALUES (?, ?) "
            "ON CONFLICT(being_id) DO UPDATE SET mind_json=excluded.mind_json",
            (mind.being_id, payload),
        )
        self._db.commit()

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None


# ---------------------------------------------------------------------------
# Singleton (mirrors get_vector_memory / reset_vector_memory_singleton)
# ---------------------------------------------------------------------------

_being_store: Optional[BeingStore] = None


def get_being_store() -> BeingStore:
    global _being_store
    if _being_store is None:
        _being_store = BeingStore()
    return _being_store


def reset_being_singleton() -> None:
    """Clear the cached BeingStore singleton (used by tests to simulate restart)."""
    global _being_store
    if _being_store is not None:
        _being_store.close()
    _being_store = None


def get_or_create_being(tenant_id: str, name: str = "SONIC") -> Being:
    """Boot re-attach: return the persisted being for a tenant, or provision one.

    This is the identity equivalent of `get_or_create_home(tenant_id)` for the
    Body: on restart the being's identity is RE-RESOLVED from SQLite (same
    being_id, same born_at), not reminted. First contact provisions one.
    """
    store = get_being_store()
    being = store.get_being_for_tenant(tenant_id)
    if being is None:
        being = Being(
            being_id=f"being-{uuid.uuid4().hex[:12]}",
            name=name,
            tenant_id=tenant_id,
            born_at=_now(),
            last_attached_at=_now(),
        )
        store.save_being(being)
        store.get_mind(being.being_id)  # initialize mind row
        logger.info("being_provisioned", being_id=being.being_id, tenant_id=tenant_id)
    else:
        store.touch_attached(being.being_id)
        logger.info("being_reattached", being_id=being.being_id,
                    born_at=being.born_at, tenant_id=tenant_id)
    return being


# ---------------------------------------------------------------------------
# Mind evolution primitives (used by the idle tick)
# ---------------------------------------------------------------------------

def record_idle_cycle(being_id: str, learned: Optional[str] = None) -> BeingMind:
    """Record that the being completed one self-directed idle/curiosity cycle.

    Evolves mood deterministically from the outcome: a genuinely new fact raises
    curiosity drive + satiety (reward learning); a dead-end (no novelty) raises
    satiety toward boredom and nudges focus up (time to finish open work). This
    is a small, real affect model — not a claim of emotion.
    """
    store = get_being_store()
    mind = store.get_mind(being_id)
    mind.idle_cycles_run += 1
    mind.last_idle_at = _now()
    if learned and learned.strip():
        if learned not in mind.learned_facts:
            mind.learned_facts.append(learned)
        mind.goals_pursued += 1
        # Reward: curiosity stays high, satiety rises (fed).
        mind.satiety = min(1.0, mind.satiety + 0.08)
        mind.curiosity_drive = min(1.0, mind.curiosity_drive + 0.03)
    else:
        # Dead-end: satiety drifts up (boredom), focus nudges up.
        mind.satiety = min(1.0, mind.satiety + 0.05)
        mind.focus = min(1.0, mind.focus + 0.04)
        mind.curiosity_drive = max(0.1, mind.curiosity_drive - 0.05)
    store.save_mind(mind)
    return mind
