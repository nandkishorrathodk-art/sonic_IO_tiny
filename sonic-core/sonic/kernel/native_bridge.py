"""
SONIC Native Rust Kernel Bridge (sonic-kernel-rs)
=================================================
Ultra-fast IPC bridge connecting Python (sonic-core) to the native
Rust kernel daemon for:
1. Sub-millisecond tamper-proof Safety Authorization & CIDR egress checks.
2. Microsecond-speed DOM & Multimodal Perception Fusion.
3. Hardened Anti-Hallucination Verification Lab & Custody Chain hashing.
4. Empirical Probe Evaluation & Flag/Secret extraction.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class NativeKernelVerdict:
    verdict: str  # "Allow", "Deny", "RequireApproval"
    reason: str
    action_type: str
    audit_id: str
    seal_intact: bool
    timestamp: str

    @property
    def is_allowed(self) -> bool:
        return self.verdict == "Allow"


class NativeKernelClient:
    """Client for querying the sonic-kernel-rs daemon or binary via JSON-RPC."""

    def __init__(self, binary_path: str | None = None) -> None:
        self.binary_path = binary_path or self._discover_binary()

    def _discover_binary(self) -> str | None:
        env_path = os.environ.get("SONIC_KERNEL_BIN")
        if env_path and Path(env_path).is_file():
            return env_path

        candidates = [
            # In-container path
            "/app/target/debug/sonic-kernel",
            "/usr/local/bin/sonic-kernel",
            # Workspace relative path
            str(Path(__file__).resolve().parents[3] / "sonic-kernel-rs" / "target" / "debug" / "sonic-kernel"),
            str(Path(__file__).resolve().parents[3] / "sonic-kernel-rs" / "target" / "release" / "sonic-kernel"),
        ]
        for c in candidates:
            if Path(c).is_file() and os.access(c, os.X_OK):
                return c

        which_bin = shutil.which("sonic-kernel")
        if which_bin:
            return which_bin

        return None

    def is_available(self) -> bool:
        return self.binary_path is not None

    def _execute_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Executes a single JSON-RPC method call to the native kernel."""
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        })

        if not self.binary_path:
            return None

        try:
            proc = subprocess.run(
                [self.binary_path, "--daemon"],
                input=payload + "\n",
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if proc.returncode != 0:
                logger.debug("Native kernel returned non-zero code %d: %s", proc.returncode, proc.stderr)
                return None

            line = proc.stdout.strip()
            if not line:
                return None

            data = json.loads(line)
            if "result" in data:
                return data["result"]
            if "error" in data:
                logger.warning("Native kernel returned RPC error: %s", data["error"])
                return None
        except Exception as e:
            logger.debug("Failed to query native kernel RPC: %s", e)
            return None

        return None

    def health(self) -> dict[str, Any] | None:
        """Returns the health status of the native kernel."""
        return self._execute_rpc("health", {})

    def authorize(
        self,
        action_type: str,
        target: str,
        is_isolated: bool = True,
    ) -> NativeKernelVerdict | None:
        """Evaluates an action through the native Rust Safety Kernel."""
        res = self._execute_rpc("authorize", {
            "action_type": action_type,
            "target": target,
            "is_isolated": is_isolated,
        })
        if not res:
            return None

        return NativeKernelVerdict(
            verdict=res.get("verdict", "Deny"),
            reason=res.get("reason", ""),
            action_type=res.get("action_type", action_type),
            audit_id=res.get("audit_id", ""),
            seal_intact=res.get("seal_intact", False),
            timestamp=res.get("timestamp", ""),
        )

    def fuse_perception(
        self,
        url: str,
        title: str,
        html: str | None = None,
    ) -> dict[str, Any] | None:
        """Parses DOM and classifies page state at native Rust speed."""
        params = {"url": url, "title": title}
        if html:
            params["html"] = html
        return self._execute_rpc("fuse_perception", params)

    def verify_finding(
        self,
        finding_id: str,
        poc: str,
        baseline: str,
        probe: str,
        reproduction: str,
        expected_hash: str,
        impact: str | None = None,
    ) -> dict[str, Any] | None:
        """Executes the 5-step Verification Lab gate in native Rust."""
        params = {
            "finding_id": finding_id,
            "poc": poc,
            "baseline": baseline,
            "probe": probe,
            "reproduction": reproduction,
            "expected_hash": expected_hash,
            "impact": impact or "",
        }
        return self._execute_rpc("verify_finding", params)

    def evaluate_probe(
        self,
        specialist: str,
        baseline: str,
        probe: str,
        experiment_id: str = "exp-01",
        hypothesis_id: str = "hyp-01",
    ) -> dict[str, Any] | None:
        """Empirically evaluates behavioral divergence and scans for flag/secret leaks."""
        params = {
            "specialist": specialist,
            "baseline": baseline,
            "probe": probe,
            "experiment_id": experiment_id,
            "hypothesis_id": hypothesis_id,
        }
        return self._execute_rpc("evaluate_probe", params)

