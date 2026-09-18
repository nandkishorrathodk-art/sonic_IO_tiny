"""
SONIC-REDA — Full Graph Memory Implementation
=================================================
Agent-to-Agent Graph Memory using Neo4j.
Shared brain that all agents read/write to.

Features:
    - Schema initialization (constraints + indexes)
    - Type-safe CRUD for all node types
    - Relationship management
    - Query helpers (by engagement, by type, search)
    - Natural language query preparation
"""

from __future__ import annotations

from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)

from sonic.config import get_settings
from sonic.memory.schemas import (
    SCHEMA_INIT_QUERIES,
    AgentNode,
    AssetNode,
    EngagementNode,
    EvidenceNode,
    FindingNode,
    HypothesisNode,
    RelationshipType,
    TechniqueNode,
)


class GraphMemory:
    """
    Neo4j-backed graph memory for inter-agent knowledge sharing.
    Every agent reads/writes to this shared graph.
    """

    def __init__(self):
        self._driver = None
        self._connected = False

    # ============================================
    # Connection
    # ============================================

    async def connect(self) -> bool:
        """Establish connection to Neo4j."""
        settings = get_settings()
        try:
            import asyncio

            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
                connection_timeout=1.5,
                max_connection_lifetime=300,
            )
            async with self._driver.session() as session:
                result = await asyncio.wait_for(session.run("RETURN 1 AS ping"), timeout=1.5)
                await asyncio.wait_for(result.single(), timeout=1.5)

            self._connected = True
            logger.info("graph_memory_connected", uri=settings.neo4j_uri)
            return True
        except Exception as e:
            logger.warning("graph_memory_connection_failed", error=str(e))
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close Neo4j connection."""
        if self._driver:
            await self._driver.close()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def health_check(self) -> bool:
        if not self._driver:
            return False
        try:
            async with self._driver.session() as session:
                result = await session.run("RETURN 1")
                await result.single()
            return True
        except Exception:
            return False

    # ============================================
    # Schema Initialization
    # ============================================

    async def init_schema(self) -> bool:
        """Create constraints, indexes, and full-text indexes in Neo4j."""
        if not self._driver:
            return False

        try:
            async with self._driver.session() as session:
                for query in SCHEMA_INIT_QUERIES:
                    try:
                        await session.run(query)
                    except Exception as e:
                        # Some indexes may already exist
                        logger.debug("schema_query_note", query=query[:60], note=str(e))

            logger.info("graph_schema_initialized", queries=len(SCHEMA_INIT_QUERIES))
            return True
        except Exception as e:
            logger.error("graph_schema_init_failed", error=str(e))
            return False

    # ============================================
    # Generic CRUD
    # ============================================

    async def _create_node(self, label: str, props: dict[str, Any]) -> str | None:
        """Create a node and return its uid."""
        if not self._driver:
            return None

        async with self._driver.session() as session:
            query = f"CREATE (n:{label} $props) RETURN n.uid AS uid"
            result = await session.run(query, props=props)
            record = await result.single()
            return record["uid"] if record else None

    async def add_node(self, label: str, data: dict[str, Any]) -> str | None:
        """Create a generic labelled node (used by BaseAgent.remember)."""
        return await self._create_node(label, data)

    async def _get_node(self, label: str, uid: str, tenant_id: str | None = None) -> dict | None:
        """Get a node by uid, optionally filtered by tenant_id."""
        if not self._driver:
            return None

        async with self._driver.session() as session:
            if tenant_id:
                query = (
                    f"MATCH (n:{label} {{uid: $uid}}) "
                    "WHERE n.tenant_id = $tenant_id "
                    "RETURN properties(n) AS props"
                )
                result = await session.run(query, uid=uid, tenant_id=tenant_id)
            else:
                query = f"MATCH (n:{label} {{uid: $uid}}) RETURN properties(n) AS props"
                result = await session.run(query, uid=uid)
            record = await result.single()
            return record["props"] if record else None

    async def _update_node(self, label: str, uid: str, updates: dict[str, Any], tenant_id: str | None = None) -> bool:
        """Update a node's properties, optionally scoped by tenant_id."""
        if not self._driver:
            return False

        async with self._driver.session() as session:
            set_clauses = ", ".join(f"n.{k} = ${k}" for k in updates)
            params: dict[str, Any] = {"uid": uid, **updates}
            if tenant_id:
                query = (
                    f"MATCH (n:{label} {{uid: $uid}}) "
                    "WHERE n.tenant_id = $tenant_id "
                    f"SET {set_clauses} RETURN n"
                )
                params["tenant_id"] = tenant_id
            else:
                query = f"MATCH (n:{label} {{uid: $uid}}) SET {set_clauses} RETURN n"
            result = await session.run(query, params)
            return await result.single() is not None

    async def _delete_node(self, label: str, uid: str, tenant_id: str | None = None) -> bool:
        """Delete a node and its relationships, optionally scoped by tenant_id."""
        if not self._driver:
            return False

        async with self._driver.session() as session:
            if tenant_id:
                query = (
                    f"MATCH (n:{label} {{uid: $uid}}) "
                    "WHERE n.tenant_id = $tenant_id "
                    "DETACH DELETE n"
                )
                await session.run(query, uid=uid, tenant_id=tenant_id)
            else:
                query = f"MATCH (n:{label} {{uid: $uid}}) DETACH DELETE n"
                await session.run(query, uid=uid)
            return True

    async def create_relationship(
        self,
        from_label: str,
        from_uid: str,
        to_label: str,
        to_uid: str,
        rel_type: str,
        props: dict[str, Any] | None = None,
    ) -> bool:
        """Create a relationship between two nodes."""
        if not self._driver:
            return False

        async with self._driver.session() as session:
            query = (
                f"MATCH (a:{from_label} {{uid: $from_uid}}) "
                f"MATCH (b:{to_label} {{uid: $to_uid}}) "
                f"MERGE (a)-[r:{rel_type}]->(b) "
            )
            if props:
                query += "SET r += $props "
            query += "RETURN r"

            params: dict[str, Any] = {"from_uid": from_uid, "to_uid": to_uid}
            if props:
                params["props"] = props

            result = await session.run(query, params)
            return await result.single() is not None

    # ============================================
    # Typed CRUD — Engagements
    # ============================================

    async def create_engagement(self, engagement: EngagementNode) -> str | None:
        return await self._create_node("Engagement", engagement.model_dump())

    async def get_engagement(self, uid: str, tenant_id: str | None = None) -> dict | None:
        return await self._get_node("Engagement", uid, tenant_id=tenant_id)

    async def update_engagement(self, uid: str, tenant_id: str | None = None, **updates: Any) -> bool:
        return await self._update_node("Engagement", uid, updates, tenant_id=tenant_id)

    async def list_engagements(self, status: str | None = None, tenant_id: str | None = None) -> list[dict]:
        if not self._driver:
            return []
        async with self._driver.session() as session:
            conditions = []
            params: dict[str, Any] = {}
            if status:
                conditions.append("n.status = $status")
                params["status"] = status
            if tenant_id:
                conditions.append("n.tenant_id = $tenant_id")
                params["tenant_id"] = tenant_id
            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"MATCH (n:Engagement){where} RETURN properties(n) AS props ORDER BY n.created_at DESC"
            result = await session.run(query, params)
            return [record["props"] async for record in result]

    # ============================================
    # Typed CRUD — Assets
    # ============================================

    async def create_asset(self, asset: AssetNode) -> str | None:
        uid = await self._create_node("Asset", asset.model_dump())
        # Auto-link to engagement
        if uid and asset.engagement_id:
            await self.create_relationship(
                "Asset", uid, "Engagement", asset.engagement_id,
                RelationshipType.PART_OF,
            )
        return uid

    async def get_asset(self, uid: str, tenant_id: str | None = None) -> dict | None:
        return await self._get_node("Asset", uid, tenant_id=tenant_id)

    async def find_assets(
        self, engagement_id: str, asset_type: str | None = None, tenant_id: str | None = None
    ) -> list[dict]:
        if not self._driver:
            return []
        async with self._driver.session() as session:
            conditions = ["a.engagement_id = $eid"]
            params: dict[str, Any] = {"eid": engagement_id}
            if asset_type:
                conditions.append("a.asset_type = $atype")
                params["atype"] = asset_type
            if tenant_id:
                conditions.append("a.tenant_id = $tenant_id")
                params["tenant_id"] = tenant_id
            where = " AND ".join(conditions)
            query = f"MATCH (a:Asset) WHERE {where} RETURN properties(a) AS props"
            result = await session.run(query, params)
            return [record["props"] async for record in result]

    async def upsert_asset(self, asset: AssetNode) -> str:
        """Create or update asset (merge by value + type + engagement)."""
        if not self._driver:
            return ""
        async with self._driver.session() as session:
            query = (
                "MERGE (a:Asset {value: $value, asset_type: $atype, engagement_id: $eid}) "
                "ON CREATE SET a += $props "
                "ON MATCH SET a.metadata = $metadata "
                "RETURN a.uid AS uid"
            )
            result = await session.run(query,
                value=asset.value,
                atype=asset.asset_type,
                eid=asset.engagement_id,
                props=asset.model_dump(),
                metadata=asset.metadata,
            )
            record = await result.single()
            return record["uid"] if record else ""

    # ============================================
    # Typed CRUD — Findings
    # ============================================

    async def create_finding(self, finding: FindingNode) -> str | None:
        uid = await self._create_node("Finding", finding.model_dump())
        if uid:
            # Link to engagement
            if finding.engagement_id:
                await self.create_relationship(
                    "Finding", uid, "Engagement", finding.engagement_id,
                    RelationshipType.PART_OF,
                )
            # Link to target asset
            if finding.target_asset:
                await self.create_relationship(
                    "Finding", uid, "Asset", finding.target_asset,
                    RelationshipType.DISCOVERED_ON,
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
        if not self._driver:
            return []
        async with self._driver.session() as session:
            conditions = ["f.engagement_id = $eid"]
            params: dict[str, Any] = {"eid": engagement_id}

            if severity:
                conditions.append("f.severity = $severity")
                params["severity"] = severity
            if status:
                conditions.append("f.status = $status")
                params["status"] = status
            if min_confidence > 0:
                conditions.append("f.confidence_score >= $min_conf")
                params["min_conf"] = min_confidence
            if tenant_id:
                conditions.append("f.tenant_id = $tenant_id")
                params["tenant_id"] = tenant_id

            where = " AND ".join(conditions)
            query = (
                f"MATCH (f:Finding) WHERE {where} "
                "RETURN properties(f) AS props ORDER BY f.severity, f.confidence_score DESC"
            )
            result = await session.run(query, params)
            return [record["props"] async for record in result]

    # ============================================
    # Typed CRUD — Hypotheses
    # ============================================

    async def create_hypothesis(self, hypothesis: HypothesisNode) -> str | None:
        return await self._create_node("Hypothesis", hypothesis.model_dump())

    async def update_hypothesis(self, uid: str, tenant_id: str | None = None, **updates: Any) -> bool:
        return await self._update_node("Hypothesis", uid, updates, tenant_id=tenant_id)

    async def find_hypotheses(self, engagement_id: str, status: str | None = None, tenant_id: str | None = None) -> list[dict]:
        if not self._driver:
            return []
        async with self._driver.session() as session:
            conditions = ["h.engagement_id = $eid"]
            params: dict[str, Any] = {"eid": engagement_id}
            if status:
                conditions.append("h.status = $status")
                params["status"] = status
            if tenant_id:
                conditions.append("h.tenant_id = $tenant_id")
                params["tenant_id"] = tenant_id
            where = " AND ".join(conditions)
            query = f"MATCH (h:Hypothesis) WHERE {where} RETURN properties(h) AS props ORDER BY h.priority DESC"
            result = await session.run(query, params)
            return [record["props"] async for record in result]

    # ============================================
    # Typed CRUD — Evidence, Technique, Agent
    # ============================================

    async def create_evidence(self, evidence: EvidenceNode) -> str | None:
        uid = await self._create_node("Evidence", evidence.model_dump())
        if uid and evidence.finding_id:
            await self.create_relationship(
                "Finding", evidence.finding_id, "Evidence", uid,
                RelationshipType.HAS_EVIDENCE,
            )
        return uid

    async def find_evidence(self, finding_id: str, tenant_id: str | None = None) -> list[dict]:
        """List all evidence attached to a finding (tenant-isolated)."""
        if not self._driver:
            return []
        async with self._driver.session() as session:
            tenant_filter = " AND e.tenant_id = $tenant_id" if tenant_id else ""
            params: dict[str, Any] = {"fid": finding_id}
            if tenant_id:
                params["tenant_id"] = tenant_id
            query = (
                f"MATCH (:Finding {{uid: $fid}})-[:HAS_EVIDENCE]->(e:Evidence)"
                f"{tenant_filter} RETURN properties(e) AS props ORDER BY e.created_at"
            )
            result = await session.run(query, params)
            return [record["props"] async for record in result]

    async def create_technique(self, technique: TechniqueNode) -> str | None:
        return await self._create_node("Technique", technique.model_dump())

    async def register_agent(self, agent: AgentNode) -> str | None:
        return await self._create_node("Agent", agent.model_dump())

    # ============================================
    # Query Helpers
    # ============================================

    async def query(self, cypher: str, params: dict[str, Any] | None = None, tenant_id: str | None = None) -> list[dict]:
        """Run a raw Cypher query. If tenant_id is provided, it is NOT auto-injected —
        the caller is responsible for including tenant_id filtering in their Cypher."""
        if not self._driver:
            return []
        async with self._driver.session() as session:
            result = await session.run(cypher, params or {})
            return await result.data()

    async def search_findings(self, search_text: str, limit: int = 20, tenant_id: str | None = None) -> list[dict]:
        """Full-text search across findings, optionally scoped by tenant_id."""
        if not self._driver:
            return []
        async with self._driver.session() as session:
            if tenant_id:
                query = (
                    "CALL db.index.fulltext.queryNodes('findingSearch', $search) "
                    "YIELD node, score "
                    "WHERE node.tenant_id = $tenant_id "
                    "RETURN properties(node) AS props, score "
                    "ORDER BY score DESC LIMIT $limit"
                )
                result = await session.run(query, search=search_text, limit=limit, tenant_id=tenant_id)
            else:
                query = (
                    "CALL db.index.fulltext.queryNodes('findingSearch', $search) "
                    "YIELD node, score "
                    "RETURN properties(node) AS props, score "
                    "ORDER BY score DESC LIMIT $limit"
                )
                result = await session.run(query, search=search_text, limit=limit)
            return [{"finding": r["props"], "score": r["score"]} async for r in result]

    async def get_engagement_summary(self, engagement_id: str, tenant_id: str | None = None) -> dict:
        """Get a summary of an engagement's graph, scoped by tenant_id."""
        if not self._driver:
            return {}
        async with self._driver.session() as session:
            tenant_filter = " AND e.tenant_id = $tenant_id" if tenant_id else ""
            params: dict[str, Any] = {"eid": engagement_id}
            if tenant_id:
                params["tenant_id"] = tenant_id
            query = f"""
            MATCH (e:Engagement {{uid: $eid}}){tenant_filter}
            OPTIONAL MATCH (a:Asset {{engagement_id: $eid}})
            OPTIONAL MATCH (f:Finding {{engagement_id: $eid}})
            OPTIONAL MATCH (h:Hypothesis {{engagement_id: $eid}})
            RETURN
                properties(e) AS engagement,
                count(DISTINCT a) AS asset_count,
                count(DISTINCT f) AS finding_count,
                count(DISTINCT h) AS hypothesis_count
            """
            result = await session.run(query, params)
            record = await result.single()
            if not record:
                return {}
            return {
                "engagement": record["engagement"],
                "asset_count": record["asset_count"],
                "finding_count": record["finding_count"],
                "hypothesis_count": record["hypothesis_count"],
            }

    async def get_finding_graph(self, finding_uid: str, tenant_id: str | None = None) -> dict:
        """Get a finding with all its relationships (evidence, asset, agent), scoped by tenant_id."""
        if not self._driver:
            return {}
        async with self._driver.session() as session:
            tenant_filter = " AND f.tenant_id = $tenant_id" if tenant_id else ""
            params: dict[str, Any] = {"uid": finding_uid}
            if tenant_id:
                params["tenant_id"] = tenant_id
            query = f"""
            MATCH (f:Finding {{uid: $uid}}){tenant_filter}
            OPTIONAL MATCH (f)-[:DISCOVERED_ON]->(a:Asset)
            OPTIONAL MATCH (f)-[:HAS_EVIDENCE]->(e:Evidence)
            OPTIONAL MATCH (f)-[:FOUND_BY]->(ag:Agent)
            OPTIONAL MATCH (f)-[:TESTED_WITH]->(t:Technique)
            RETURN
                properties(f) AS finding,
                collect(DISTINCT properties(a)) AS assets,
                collect(DISTINCT properties(e)) AS evidence,
                collect(DISTINCT properties(ag)) AS agents,
                collect(DISTINCT properties(t)) AS techniques
            """
            result = await session.run(query, params)
            record = await result.single()
            if not record:
                return {}
            return {
                "finding": record["finding"],
                "assets": record["assets"],
                "evidence": record["evidence"],
                "agents": record["agents"],
                "techniques": record["techniques"],
            }

    async def get_stats(self, tenant_id: str | None = None) -> dict:
        """Get graph-wide statistics, optionally scoped by tenant_id."""
        if not self._driver:
            return {"connected": False}
        async with self._driver.session() as session:
            if tenant_id:
                query = """
                OPTIONAL MATCH (e:Engagement {tenant_id: $tenant_id}) WITH count(e) AS engagements
                OPTIONAL MATCH (a:Asset {tenant_id: $tenant_id}) WITH engagements, count(a) AS assets
                OPTIONAL MATCH (f:Finding {tenant_id: $tenant_id}) WITH engagements, assets, count(f) AS findings
                OPTIONAL MATCH (h:Hypothesis {tenant_id: $tenant_id}) WITH engagements, assets, findings, count(h) AS hypotheses
                RETURN engagements, assets, findings, hypotheses
                """
                result = await session.run(query, tenant_id=tenant_id)
            else:
                query = """
                OPTIONAL MATCH (e:Engagement) WITH count(e) AS engagements
                OPTIONAL MATCH (a:Asset) WITH engagements, count(a) AS assets
                OPTIONAL MATCH (f:Finding) WITH engagements, assets, count(f) AS findings
                OPTIONAL MATCH (h:Hypothesis) WITH engagements, assets, findings, count(h) AS hypotheses
                RETURN engagements, assets, findings, hypotheses
                """
                result = await session.run(query)
            record = await result.single()
            if not record:
                return {"connected": True, "empty": True}
            return {
                "connected": True,
                "engagements": record["engagements"],
                "assets": record["assets"],
                "findings": record["findings"],
                "hypotheses": record["hypotheses"],
            }


# Global singleton
_graph_memory: GraphMemory | None = None


def get_graph_memory() -> GraphMemory:
    """Get the global GraphMemory singleton."""
    global _graph_memory
    if _graph_memory is None:
        _graph_memory = GraphMemory()
    return _graph_memory
