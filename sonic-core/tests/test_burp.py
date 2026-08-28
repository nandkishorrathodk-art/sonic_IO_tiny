"""
Unit tests for Burp Suite REST integration client.
"""

import pytest
from sonic.integrations.burp import BurpClient, BurpHttpItem, BurpIssue


def test_burp_models():
    item = BurpHttpItem(
        id="item-01",
        host="target.com",
        port=443,
        protocol="https",
        url="https://target.com/api/v1/user",
        method="POST",
        status_code=200,
        request_raw="POST /api/v1/user HTTP/1.1\nHost: target.com\n\n",
        response_raw="HTTP/1.1 200 OK\n\n{\"status\":\"ok\"}",
    )
    assert item.host == "target.com"
    assert item.status_code == 200

    issue = BurpIssue(
        issue_id="issue-01",
        name="SQL Injection (Time-based)",
        severity="High",
        confidence="Certain",
        host="target.com",
        path="/api/v1/user",
        description="Database response delay observed",
        remediation="Use parameterized queries",
        http_items=[item],
    )
    assert issue.severity == "High"
    assert len(issue.http_items) == 1
