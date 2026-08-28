"""
Unit tests for Graph Memory Schemas.
"""

import pytest
from sonic.memory.schemas import (
    AssetNode,
    AssetType,
    EngagementNode,
    FindingNode,
    FindingSeverity,
    FindingStatus,
    HypothesisNode,
    RelationshipType,
)


def test_asset_node_schema():
    asset = AssetNode(
        asset_type=AssetType.SUBDOMAIN,
        value="api.staging.example.com",
        name="Staging API Gateway",
        discovered_by="recon-agent-01",
        engagement_id="eng-1234",
    )
    assert asset.neo4j_label == "Asset"
    assert asset.asset_type == AssetType.SUBDOMAIN
    assert asset.uid is not None


def test_finding_node_schema():
    finding = FindingNode(
        title="IDOR in user profile endpoint",
        description="Changing user_id parameter returns other users private data",
        vulnerability_class="IDOR",
        severity=FindingSeverity.HIGH,
        status=FindingStatus.NEEDS_VERIFICATION,
        poc="GET /api/user?user_id=1002 HTTP/1.1",
        impact="Full account takeover and unauthorized PII access",
        found_by="dynamic-agent-01",
        engagement_id="eng-1234",
    )
    assert finding.neo4j_label == "Finding"
    assert finding.severity == FindingSeverity.HIGH
    assert finding.status == FindingStatus.NEEDS_VERIFICATION


def test_relationships_types():
    assert RelationshipType.DISCOVERED_ON == "DISCOVERED_ON"
    assert RelationshipType.HAS_EVIDENCE == "HAS_EVIDENCE"
    assert RelationshipType.VALIDATED_BY == "VALIDATED_BY"
