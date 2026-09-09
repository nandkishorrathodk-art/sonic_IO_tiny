"""
Tests for SONIC's Attack Graph and Domain Specialists:
  1. BusinessLogicSpecialist multi-step state machine analysis.
  2. CloudSpecialist metadata (IMDS) and storage asset investigation.
  3. Dynamic decomposition reactive rules for Business Logic & Cloud.
  4. AttackGraph DAG representation, multi-hop pathfinding, and Mermaid export.
"""

from __future__ import annotations

import pytest

from sonic.research.attack_graph import (
    AttackEdge,
    AttackGraph,
    AttackNode,
    AttackNodeType,
    AttackPath,
)
from sonic.research.event_bus import (
    AnomalyDetectedEvent,
    EndpointDiscoveredEvent,
    HypothesisProposedEvent,
    ResearchEventBus,
    TargetDiscoveredEvent,
    VulnerabilityVerifiedEvent,
)
from sonic.research.orchestrator import (
    AsyncResearchOrchestrator,
    ResearchBlackboard,
    default_decomposition_rules,
)
from sonic.research.specialist import (
    BusinessLogicSpecialist,
    CloudSpecialist,
    SpecialistState,
)


@pytest.mark.asyncio
async def test_business_logic_specialist_workflow():
    bus = ResearchEventBus()
    anomalies: list[AnomalyDetectedEvent] = []
    hypotheses: list[HypothesisProposedEvent] = []
    verified: list[VulnerabilityVerifiedEvent] = []

    bus.subscribe(AnomalyDetectedEvent, lambda e: anomalies.append(e))
    bus.subscribe(HypothesisProposedEvent, lambda e: hypotheses.append(e))
    bus.subscribe(VulnerabilityVerifiedEvent, lambda e: verified.append(e))

    specialist = BusinessLogicSpecialist(
        name="CartLogicTester",
        target_url="https://app.corp/cart",
    )

    context = {
        "workflows": [
            {"name": "checkout_flow", "steps": ["/cart", "/checkout", "/pay", "/confirm"]},
        ],
        # Real reproduction evidence must be explicit (caller-supplied) — a
        # specialist must never fabricate a confirmed vulnerability by itself.
        "verification_evidence": "Reproduced: direct /confirm without /pay transitioned order to confirmed",
    }

    result = await specialist.run(context, bus)
    assert specialist.state == SpecialistState.COMPLETED
    assert result["workflows_analyzed"] == 1
    assert len(anomalies) == 1
    assert "checkout_flow" in anomalies[0].observation
    assert len(hypotheses) == 1
    assert "Business workflows" in hypotheses[0].statement
    assert len(verified) == 1
    assert verified[0].vulnerability_class == "Business Logic Flaw"


@pytest.mark.asyncio
async def test_cloud_specialist_imds_and_storage():
    bus = ResearchEventBus()
    targets: list[TargetDiscoveredEvent] = []
    hypotheses: list[HypothesisProposedEvent] = []
    verified: list[VulnerabilityVerifiedEvent] = []

    bus.subscribe(TargetDiscoveredEvent, lambda e: targets.append(e))
    bus.subscribe(HypothesisProposedEvent, lambda e: hypotheses.append(e))
    bus.subscribe(VulnerabilityVerifiedEvent, lambda e: verified.append(e))

    specialist = CloudSpecialist(
        name="AWSCloudAuditor",
        target_host="customer-app",
    )

    context = {
        "cloud_assets": [
            {"type": "cloud_storage", "name": "customer-app-data", "provider": "s3"},
            {"type": "imds_target", "name": "169.254.169.254", "flavor": "aws_imds_v1"},
        ],
        # Real reproduction evidence must be explicit (caller-supplied) — a
        # specialist must never fabricate an S3/IMDS finding by itself.

        "verification_evidence": "Reproduced: anonymous list of S3 bucket returned 200 (AllUsers:READ)",
    }

    result = await specialist.run(context, bus)
    assert specialist.state == SpecialistState.COMPLETED
    assert result["cloud_assets_evaluated"] == 2
    assert len(targets) == 2
    assert any(t.target == "customer-app-data" for t in targets)
    assert len(hypotheses) == 1
    assert "Cloud resources" in hypotheses[0].statement
    assert len(verified) == 1
    assert verified[0].vulnerability_class == "Cloud Misconfiguration"


@pytest.mark.asyncio
async def test_dynamic_decomposition_spawns_business_and_cloud():
    """Verify that discovering /checkout and cloud IP triggers reactive specialist spawning."""
    orchestrator = AsyncResearchOrchestrator(max_concurrent_specialists=10)
    bus = orchestrator.event_bus

    # Trigger 1: Endpoint with /checkout triggers BusinessLogicSpecialist
    ep_event = EndpointDiscoveredEvent(url="https://shop.corp/checkout/pay")
    # Trigger 2: Target with cloud storage triggers CloudSpecialist
    tgt_event = TargetDiscoveredEvent(target="corp-backups.s3.amazonaws.com", target_type="cloud_resource")

    # Evaluate rules
    rules = default_decomposition_rules()
    bl_rules = [r for r in rules if r.name == "WebToBusinessLogic"]
    cloud_rules = [r for r in rules if r.name == "TargetToCloud"]

    assert len(bl_rules) == 1
    assert len(cloud_rules) == 1

    bl_specialists = bl_rules[0].spawn_factory(ep_event, orchestrator.blackboard)
    assert len(bl_specialists) == 1
    assert isinstance(bl_specialists[0], BusinessLogicSpecialist)
    assert "BusinessLogicSpecialist" in bl_specialists[0].name

    cloud_specialists = cloud_rules[0].spawn_factory(tgt_event, orchestrator.blackboard)
    assert len(cloud_specialists) == 1
    assert isinstance(cloud_specialists[0], CloudSpecialist)
    assert "CloudSpecialist" in cloud_specialists[0].name


def test_attack_graph_pathfinding_and_mermaid():
    """Verify AttackGraph nodes, edges, multi-hop pathfinding, and Mermaid rendering."""
    graph = AttackGraph()

    # 1. Add nodes representing attack chain:
    # Internet Entry -> Web SSRF -> Cloud IMDS Token -> S3 Backup Bucket -> RCE / Objective
    n_entry = graph.add_node("entry-1", "Public Web App (:443)", AttackNodeType.ENTRY_POINT)
    n_ssrf = graph.add_node("vuln-ssrf", "SSRF on /api/proxy", AttackNodeType.VULNERABILITY, severity="critical")
    n_cred = graph.add_node("cred-imds", "AWS IAM Role Token", AttackNodeType.CREDENTIAL, severity="high")
    n_bucket = graph.add_node("asset-s3", "S3 Storage Bucket", AttackNodeType.ASSET)
    n_obj = graph.add_node("obj-rce", "Remote Code Execution", AttackNodeType.OBJECTIVE, severity="critical")

    assert len(graph.nodes) == 5

    # 2. Add edges
    graph.add_edge("entry-1", "vuln-ssrf", "Probe input reflection", confidence=0.95)
    graph.add_edge("vuln-ssrf", "cred-imds", "Extract metadata from 169.254.169.254", confidence=0.9)
    graph.add_edge("cred-imds", "asset-s3", "Authenticate with leaked IAM keys", confidence=1.0)
    graph.add_edge("asset-s3", "obj-rce", "Overwrite deployment script in bucket", confidence=0.85)

    # Also add an alternative dead-end branch
    n_sqli = graph.add_node("vuln-sqli", "Blind SQLi on /search", AttackNodeType.VULNERABILITY)
    graph.add_edge("entry-1", "vuln-sqli", "Inject timing payload", confidence=0.7)

    # 3. Pathfinding
    paths = graph.find_all_paths("entry-1", "obj-rce")
    assert len(paths) == 1
    path = paths[0]
    assert path.total_hops == 4
    assert [n.id for n in path.nodes] == ["entry-1", "vuln-ssrf", "cred-imds", "asset-s3", "obj-rce"]
    assert 0.7 < path.compound_confidence < 0.75

    # Shortest path
    shortest = graph.shortest_path("entry-1", "obj-rce")
    assert shortest is not None
    assert shortest.total_hops == 4

    # No path to unconnected node
    n_orphan = graph.add_node("asset-db", "Internal DB", AttackNodeType.ASSET)
    assert graph.shortest_path("entry-1", "asset-db") is None

    # 4. Mermaid visualization
    mermaid = graph.to_mermaid()
    assert "graph TD" in mermaid
    assert 'entry-1(["Public Web App (:443)"])' in mermaid
    assert 'obj-rce>"Remote Code Execution"]' in mermaid
    assert 'entry-1 -->|"Probe input reflection"| vuln-ssrf' in mermaid

