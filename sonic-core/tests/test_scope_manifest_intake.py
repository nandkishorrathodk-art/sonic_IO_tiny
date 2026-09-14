from sonic.computer_use.scope_manifest import parse_scope_document
from sonic.api.routes.workstation import _extract_target_url_or_domain


def test_scope_document_separates_assets_from_reference_links():
    text = """
    Bug Bounty Program. Safe harbor. Targets 4 out of 4.
    opensea.io In scope https://opensea.io/
    OpenSea MCP In scope https://mcp.opensea.io
    Seaport Deployment In scope.
    Current deployments: https://github.com/ProjectOpenSea/seaport#deployments
    Contract reference: https://etherscan.io/address/0x123
    Exclusions: phishing and similar attacks. Third-party services are excluded.
    """ * 4

    manifest = parse_scope_document(text)

    assert manifest.program_detected is True
    assert "opensea.io" in manifest.in_scope_assets
    assert "mcp.opensea.io" in manifest.in_scope_assets
    assert "https://github.com/ProjectOpenSea/seaport#deployments" in manifest.reference_links
    assert "https://etherscan.io/address/0x123" in manifest.reference_links
    assert "phishing/social engineering" in manifest.exclusions
    assert manifest.requires_asset_selection is True


def test_normal_conversation_is_not_treated_as_scope_document():
    manifest = parse_scope_document("Please inspect https://opensea.io for the issue.")

    assert manifest.program_detected is False
    assert manifest.in_scope_assets == ()


def test_single_scope_asset_wins_over_reference_url():
    text = """
    Bug Bounty Program. Safe harbor. Targets.
    Primary target: https://target.example in scope.
    Deployment documentation: https://github.com/example/project
    Exclusions: phishing and similar attacks.
    """ * 4

    state = {}
    assert _extract_target_url_or_domain(text, state) == "target.example"
    assert state["active_target"] == "target.example"
