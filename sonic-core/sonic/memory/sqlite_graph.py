"""
SONIC-REDA — SQLite-Backed Persistent Graph Store
===================================================
A persistent, multi-tenant graph memory that mirrors the :class:`InMemoryGraph`
interface but writes every node and relationship through to a local SQLite file,
so SONIC's mind survives a backend restart.

Design (per PLAN Phase 1):
    - Two tables: ``memory_nodes`` (uid, label, tenant_id, props_json, created_at)
      and ``memory_relationships`` (from_uid, to_uid, type, props_json, tenant_id).
    - Every write flushes to SQLite immediately (write-through). Reads load from
      SQLite. No in-memory state is required across restarts.
    - Tenant isolation is enforced on every read/write exactly like InMemoryGraph.
    - Dependency-light: a single ``aiosqlite`` connection (no ORM).

The default DB path resolves from ``DATABASE_URL`` (sqlite+aiosqlite) or falls
back to ``./sonic_data.db``; it can be overridden via ``SONIC_MEMORY_DB_PATH``
for tests.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from sonic.logger import get_logger
from sonic.memory.schemas import (
    AgentNode,
    AssetNode,
    EngagementNode,
    EvidenceNode,
    FindingNode,
    HypothesisNode,
    RelationshipType,
    TechniqueNode,
)

logger = get_logger(__name__)


def _default_db_path() -> str:
    """Resolve the SQLite file path for persistent memory."""
    explicit = os.environ.get("SONIC_MEMORY_DB_PATH")
    if explicit:
        return explicit
    db_url = os.environ.get("DATABASE_URL", "")
    # sqlite+aiosqlite:///./sonic_data.db  -> ./sonic_data.db
    if db_url.startswith("sqlite"):
        return db_url.split(":///", 1)[-1] if ":///" in db_url else "sonic_data.db"
    # Non-sqlite DATABASE_URL (e.g. postgres) means persistent graph falls back
    # to a local file rather than silently losing memory.
    return "sonic_data.db"


class SqliteGraph:
    """
    Persistent multi-tenant graph store backed by SQLite.

    Implements the same method surface as :class:`InMemoryGraph` /
    :class:`GraphMemory` so it is a drop-in for the smart-memory router.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _default_db_path()
        self._db: aiosqlite.Connection | None = None
        self._connected = False

    # ============================================
    # Lifecycle
    # ============================================

    async def connect(self) -> bool:
        if self._db is not None:
            self._connected = True
            return True
        # autocommit off; we commit explicitly after every write (write-through).
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self.init_schema()
        self._connected = True
        logger.info("sqlite_graph_ready", db_path=self.db_path)
        return True

    async def disconnect(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def health_check(self) -> bool:
        if not self._connected or self._db is None:
            return False
        try:
            async with self._db.execute("SELECT 1") as cur:
                await cur.fetchone()
            return True
        except Exception:
            return False

    async def init_schema(self) -> bool:
        assert self._db is not None
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_nodes (
                uid        TEXT PRIMARY KEY,
                label      TEXT NOT NULL,
                tenant_id  TEXT NOT NULL DEFAULT 'default',
                props_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_label   ON memory_nodes(label);
            CREATE INDEX IF NOT EXISTS idx_nodes_tenant  ON memory_nodes(tenant_id);

            CREATE TABLE IF NOT EXISTS memory_relationships (
                from_uid    TEXT NOT NULL,
                to_uid      TEXT NOT NULL,
                type        TEXT NOT NULL,
                from_label  TEXT NOT NULL,
                to_label    TEXT NOT NULL,
                props_json  TEXT NOT NULL DEFAULT '{}',
                tenant_id   TEXT NOT NULL DEFAULT 'default'
            );
            CREATE INDEX IF NOT EXISTS idx_rels_from   ON memory_relationships(from_uid);
            CREATE INDEX IF NOT EXISTS idx_rels_to     ON memory_relationships(to_uid);
            CREATE INDEX IF NOT EXISTS idx_rels_tenant ON memory_relationships(tenant_id);
            """
        )
        await self._db.commit()
        return True

    # ============================================
    # Internal helpers (write-through)
    # ============================================

    async def create_node(self, node: Any) -> str | None:
        """Generic node creator for any pydantic node or dict."""
        if hasattr(node, "model_dump"):
            data = node.model_dump()
            label = type(node).__name__.replace("Node", "")
        elif isinstance(node, dict):
            data = dict(node)
            label = data.pop("_label", "Node")
        else:
            data = dict(node.__dict__)
            label = type(node).__name__.replace("Node", "")
        return await self._create_node(label, data)

    async def _create_node(self, label: str, props: dict[str, Any]) -> str | None:
        assert self._db is not None
        uid = props.get("uid") or f"{label.lower()}-{uuid.uuid4().hex[:8]}"
        props["uid"] = uid
        props["_label"] = label
        if not props.get("tenant_id"):
            props["tenant_id"] = "default"
        if "created_at" not in props:
            props["created_at"] = datetime.now(UTC).isoformat()
        created_at = props["created_at"]
        tenant_id = props["tenant_id"]
        # Store props WITHOUT the internal _label key in props_json (label has
        # its own column) but keep it on read so callers see the same shape as
        # InMemoryGraph.
        storable = {k: v for k, v in props.items() if k != "_label"}
        await self._db.execute(
            "INSERT OR REPLACE INTO memory_nodes "
            "(uid, label, tenant_id, props_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, label, tenant_id, json.dumps(storable, default=str), created_at),
        )
        await self._db.commit()
        return uid

    async def _get_node(self, label: str, uid: str, tenant_id: str | None = None) -> dict | None:
        assert self._db is not None
        if tenant_id:
            sql = (
                "SELECT label, props_json FROM memory_nodes "
                "WHERE uid = ? AND label = ? AND tenant_id = ?"
            )
            params: tuple = (uid, label, tenant_id)
        else:
            sql = "SELECT label, props_json FROM memory_nodes WHERE uid = ? AND label = ?"
            params = (uid, label)
        async with self._db.execute(sql, params) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        node = json.loads(row[1])
        node["_label"] = row[0]
        return {k: v for k, v in node.items() if k != "_label"}

    async def _update_node(self, label: str, uid: str, updates: dict[str, Any], tenant_id: str | None = None) -> bool:
        assert self._db is not None
        existing = await self._get_node(label, uid, tenant_id=tenant_id)
        if existing is None:
            return False
        merged = {**existing, **updates}
        storable = {k: v for k, v in merged.items() if k != "_label"}
        await self._db.execute(
            "UPDATE memory_nodes SET props_json = ? WHERE uid = ?",
            (json.dumps(storable, default=str), uid),
        )
        await self._db.commit()
        return True

    async def _delete_node(self, label: str, uid: str, tenant_id: str | None = None) -> bool:
        assert self._db is not None
        existing = await self._get_node(label, uid, tenant_id=tenant_id)
        if existing is None:
            return False
        await self._db.execute("DELETE FROM memory_nodes WHERE uid = ?", (uid,))
        await self._db.execute(
            "DELETE FROM memory_relationships WHERE from_uid = ? OR to_uid = ?", (uid, uid)
        )
        await self._db.commit()
        return True

    async def create_relationship(
        self, from_label: str, from_uid: str,
        to_label: str, to_uid: str,
        rel_type: str, props: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> bool:
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO memory_relationships "
            "(from_uid, to_uid, type, from_label, to_label, props_json, tenant_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                from_uid, to_uid, rel_type, from_label, to_label,
                json.dumps(props or {}, default=str),
                tenant_id or "default",
            ),
        )
        await self._db.commit()
        return True

    # ============================================
    # Typed Multi-Tenant CRUD (mirrors InMemoryGraph)
    # ============================================

    async def create_engagement(self, engagement: EngagementNode) -> str | None:
        return await self._create_node("Engagement", engagement.model_dump())

    async def get_engagement(self, uid: str, tenant_id: str | None = None) -> dict | None:
        return await self._get_node("Engagement", uid, tenant_id=tenant_id)

    async def update_engagement(self, uid: str, tenant_id: str | None = None, **updates: Any) -> bool:
        return await self._update_node("Engagement", uid, updates, tenant_id=tenant_id)

    async def list_engagements(self, status: str | None = None, tenant_id: str | None = None) -> list[dict]:
        return await self._list_nodes("Engagement", filters={"status": status}, tenant_id=tenant_id)

    async def create_asset(self, asset: AssetNode) -> str | None:
        uid = await self._create_node("Asset", asset.model_dump())
        if uid and asset.engagement_id:
            await self.create_relationship(
                "Asset", uid, "Engagement", asset.engagement_id,
                RelationshipType.PART_OF, tenant_id=asset.tenant_id,
            )
        return uid

    async def get_asset(self, uid: str, tenant_id: str | None = None) -> dict | None:
        return await self._get_node("Asset", uid, tenant_id=tenant_id)

    async def find_assets(self, engagement_id: str, asset_type: str | None = None, tenant_id: str | None = None) -> list[dict]:
        filters: dict[str, Any] = {"engagement_id": engagement_id}
        if asset_type:
            filters["asset_type"] = asset_type
        return await self._list_nodes("Asset", filters=filters, tenant_id=tenant_id)

    async def upsert_asset(self, asset: AssetNode) -> str:
        for n in await self._list_nodes("Asset", tenant_id=asset.tenant_id):
            if (n.get("value") == asset.value
                    and n.get("asset_type") == asset.asset_type
                    and n.get("engagement_id") == asset.engagement_id):
                await self._update_node("Asset", n["uid"], {"metadata": asset.metadata}, tenant_id=asset.tenant_id)
                return n["uid"]
        return await self._create_node("Asset", asset.model_dump()) or ""

    async def create_finding(self, finding: FindingNode) -> str | None:
        uid = await self._create_node("Finding", finding.model_dump())
        if uid and finding.engagement_id:
            await self.create_relationship(
                "Finding", uid, "Engagement", finding.engagement_id,
                RelationshipType.PART_OF, tenant_id=finding.tenant_id,
            )
        return uid

    async def get_finding(self, uid: str, tenant_id: str | None = None) -> dict | None:
        return await self._get_node("Finding", uid, tenant_id=tenant_id)

    async def update_finding(self, uid: str, tenant_id: str | None = None, **updates: Any) -> bool:
        return await self._update_node("Finding", uid, updates, tenant_id=tenant_id)

    async def find_findings(
        self,
        engagement_id: str,
        severity: str | None = None,
        status: str | None = None,
        min_confidence: int = 0,
        tenant_id: str | None = None,
    ) -> list[dict]:
        filters: dict[str, Any] = {"engagement_id": engagement_id}
        if severity:
            filters["severity"] = severity
        if status:
            filters["status"] = status
        out = []
        for n in await self._list_nodes("Finding", filters=filters, tenant_id=tenant_id):
            if n.get("confidence_score", 0) < min_confidence:
                continue
            out.append(n)
        return out

    async def create_hypothesis(self, hypothesis: HypothesisNode) -> str | None:
        return await self._create_node("Hypothesis", hypothesis.model_dump())

    async def update_hypothesis(self, uid: str, tenant_id: str | None = None, **updates: Any) -> bool:
        return await self._update_node("Hypothesis", uid, updates, tenant_id=tenant_id)

    async def find_hypotheses(self, engagement_id: str, status: str | None = None, tenant_id: str | None = None) -> list[dict]:
        filters: dict[str, Any] = {"engagement_id": engagement_id}
        if status:
            filters["status"] = status
        return await self._list_nodes("Hypothesis", filters=filters, tenant_id=tenant_id)

    async def create_evidence(self, evidence: EvidenceNode) -> str | None:
        uid = await self._create_node("Evidence", evidence.model_dump())
        if uid and evidence.finding_id:
            await self.create_relationship(
                "Finding", evidence.finding_id, "Evidence", uid,
                RelationshipType.HAS_EVIDENCE, tenant_id=evidence.tenant_id,
            )
        return uid

    async def find_evidence(self, finding_id: str, tenant_id: str | None = None) -> list[dict]:
        """List all evidence attached to a finding (tenant-isolated)."""
        assert self._db is not None
        sql = (
            "SELECT n.label, n.props_json FROM memory_nodes n "
            "JOIN memory_relationships r ON r.to_uid = n.uid "
            "WHERE r.type = ? AND r.from_uid = ? AND n.label = 'Evidence'"
        )
        params: list[Any] = [RelationshipType.HAS_EVIDENCE, finding_id]
        if tenant_id:
            sql += " AND r.tenant_id = ?"
            params.append(tenant_id)
        out: list[dict] = []
        async with self._db.execute(sql, params) as cur:
            for label_val, props_json in await cur.fetchall():
                node = json.loads(props_json)
                node["_label"] = label_val
                out.append({k: v for k, v in node.items() if k != "_label"})
        return out

    async def create_technique(self, technique: TechniqueNode) -> str | None:
        return await self._create_node("Technique", technique.model_dump())

    async def register_agent(self, agent: AgentNode) -> str | None:
        return await self._create_node("Agent", agent.model_dump())

    # ============================================
    # Generic query / search
    # ============================================

    async def add_node(self, label: str, data: dict[str, Any]) -> str | None:
        return await self._create_node(label, data)

    async def _list_nodes(
        self,
        label: str,
        filters: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> list[dict]:
        assert self._db is not None
        sql = "SELECT label, props_json FROM memory_nodes WHERE label = ?"
        params: list[Any] = [label]
        if tenant_id:
            sql += " AND tenant_id = ?"
            params.append(tenant_id)
        rows: list[dict] = []
        async with self._db.execute(sql, params) as cur:
            for label_val, props_json in await cur.fetchall():
                node = json.loads(props_json)
                node["_label"] = label_val
                node = {k: v for k, v in node.items() if k != "_label"}
                if filters:
                    if any(node.get(k) != v for k, v in filters.items() if v is not None):
                        continue
                rows.append(node)
        return rows

    async def query(self, query_str: str, params: dict[str, Any] | None = None, tenant_id: str | None = None) -> list[dict]:
        # query_str is retained for interface parity; we return tenant-scoped nodes.
        assert self._db is not None
        sql = "SELECT label, props_json FROM memory_nodes"
        p: list[Any] = []
        if tenant_id:
            sql += " WHERE tenant_id = ?"
            p.append(tenant_id)
        out = []
        async with self._db.execute(sql, p) as cur:
            for label_val, props_json in await cur.fetchall():
                node = json.loads(props_json)
                node["_label"] = label_val
                out.append({k: v for k, v in node.items() if k != "_label"})
        return out[:20]

    async def search_findings(self, search_text: str, limit: int = 20, tenant_id: str | None = None) -> list[dict]:
        search_lower = search_text.lower()
        out = []
        for n in await self._list_nodes("Finding", tenant_id=tenant_id):
            text = f"{n.get('title', '')} {n.get('description', '')} {n.get('vulnerability_class', '')}".lower()
            if search_lower in text:
                out.append({"finding": n, "score": 1.0})
        return out[:limit]

    async def get_engagement_summary(self, engagement_id: str, tenant_id: str | None = None) -> dict:
        eng = await self.get_engagement(engagement_id, tenant_id=tenant_id)
        assets = await self.find_assets(engagement_id, tenant_id=tenant_id)
        findings = await self.find_findings(engagement_id, tenant_id=tenant_id)
        hypotheses = await self.find_hypotheses(engagement_id, tenant_id=tenant_id)
        return {
            "engagement": eng or {},
            "asset_count": len(assets),
            "finding_count": len(findings),
            "hypothesis_count": len(hypotheses),
        }

    async def get_stats(self, tenant_id: str | None = None) -> dict:
        assert self._db is not None
        node_sql = "SELECT label, tenant_id FROM memory_nodes"
        rel_sql = "SELECT COUNT(*) FROM memory_relationships"
        rel_params: list[Any] = []
        if tenant_id:
            node_sql = "SELECT label FROM memory_nodes WHERE tenant_id = ?"
            rel_sql = "SELECT COUNT(*) FROM memory_relationships WHERE tenant_id = ?"
            rel_params = [tenant_id]
        labels: dict[str, int] = {}
        total_nodes = 0
        async with self._db.execute(node_sql, [tenant_id] if tenant_id else []) as cur:
            for row in await cur.fetchall():
                lbl = row[0]
                labels[lbl] = labels.get(lbl, 0) + 1
                total_nodes += 1
        async with self._db.execute(rel_sql, rel_params) as cur:
            total_rels = (await cur.fetchone())[0]
        return {
            "connected": True,
            "persistent": True,
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            **{k.lower() + "s": v for k, v in labels.items()},
        }

    async def get_all_graph_data(self, tenant_id: str | None = None) -> tuple[list[dict], list[dict]]:
        """Retrieve all nodes and relationships for graph visualization."""
        assert self._db is not None
        node_sql = "SELECT uid, label, props_json FROM memory_nodes"
        node_params: list[Any] = []
        if tenant_id:
            node_sql += " WHERE tenant_id = ?"
            node_params.append(tenant_id)

        nodes: list[dict] = []
        async with self._db.execute(node_sql, node_params) as cur:
            for uid, label, props_json in await cur.fetchall():
                try:
                    props = json.loads(props_json)
                except Exception:
                    props = {}
                nodes.append({
                    "id": uid,
                    "label": props.get("title") or props.get("value") or props.get("name") or uid,
                    "type": label,
                    "properties": props,
                })

        node_ids = {n["id"] for n in nodes}
        rel_sql = "SELECT from_uid, to_uid, type FROM memory_relationships"
        rel_params: list[Any] = []
        if tenant_id:
            rel_sql += " WHERE tenant_id = ?"
            rel_params.append(tenant_id)

        edges: list[dict] = []
        async with self._db.execute(rel_sql, rel_params) as cur:
            for from_uid, to_uid, rel_type in await cur.fetchall():
                if from_uid in node_ids and to_uid in node_ids:
                    edges.append({
                        "source": from_uid,
                        "target": to_uid,
                        "type": rel_type,
                    })

        return nodes, edges

