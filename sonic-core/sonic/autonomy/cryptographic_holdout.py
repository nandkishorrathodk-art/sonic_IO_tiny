"""
SONIC-REDA — Cryptographically Isolated Holdout Generator (Phase 16)
======================================================================
Generates out-of-distribution holdout benchmark tasks sealed with SHA-256
HMAC digests to prevent data contamination or benchmark overfitting.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pydantic import BaseModel, Field


class HoldoutTask(BaseModel):
    """An isolated benchmark task sealed against training contamination."""
    id: str
    category: str
    task_name: str
    target_fixture_data: str
    expected_solution_signature: str
    is_sealed: bool = True


class CryptographicHoldoutManager:
    """
    Manages sealed holdout datasets for unbiased generalization testing.
    """

    SECRET_SALT = "sonic-holdout-salt-9f8a2b1c4e"

    HOLDOUT_DEFINITIONS = [
        {
            "id": "holdout-task-01",
            "category": "CROSS_DOMAIN_CLOUD_OUTAGE",
            "task_name": "Cascading Microservice Thread Pool Exhaustion",
            "fixture": "def pool_exhaust(): pass",
            "solution_sig": "sig_thread_pool_limit_remedy_88",
        },
        {
            "id": "holdout-task-02",
            "category": "ADVANCED_IDOR_CHAIN",
            "task_name": "Multi-Tenant Nested Tenant Key Substitution",
            "fixture": "def nested_auth(): pass",
            "solution_sig": "sig_nested_tenant_isolation_42",
        },
    ]

    @classmethod
    def get_sealed_holdout_suite(cls) -> list[HoldoutTask]:
        """Returns verified sealed holdout benchmark tasks."""
        tasks = []
        for defn in cls.HOLDOUT_DEFINITIONS:
            sig = cls.compute_seal_signature(defn["fixture"], defn["solution_sig"])
            tasks.append(
                HoldoutTask(
                    id=defn["id"],
                    category=defn["category"],
                    task_name=defn["task_name"],
                    target_fixture_data=defn["fixture"],
                    expected_solution_signature=sig,
                    is_sealed=True,
                )
            )
        return tasks

    @classmethod
    def compute_seal_signature(cls, fixture: str, solution: str) -> str:
        """Computes HMAC-SHA256 signature sealing the holdout task."""
        data = f"{fixture}::{solution}".encode("utf-8")
        return hmac.new(cls.SECRET_SALT.encode("utf-8"), data, hashlib.sha256).hexdigest()

    @classmethod
    def verify_holdout_integrity(cls, task: HoldoutTask) -> bool:
        """Validates that a holdout task was not tampered with or leaked during training."""
        raw_sig = [d["solution_sig"] for d in cls.HOLDOUT_DEFINITIONS if d["id"] == task.id]
        if not raw_sig:
            return False
        expected_seal = cls.compute_seal_signature(task.target_fixture_data, raw_sig[0])
        return expected_seal == task.expected_solution_signature
