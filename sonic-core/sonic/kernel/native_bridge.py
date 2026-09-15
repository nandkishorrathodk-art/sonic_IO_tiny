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
    """Client for querying the sonic-kernel-rs daemon or binary via fast JSON-RPC."""

    def __init__(self, binary_path: str | None = None) -> None:
        self.binary_path = binary_path or self._discover_binary()
        self._daemon_proc: subprocess.Popen | None = None
        self._native_disabled = False

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
            # The checked-in Rust target is a Linux ELF binary. Do not select
            # it on Windows, where spawning it only produces WinError 193 on
            # every first safety check; an explicit SONIC_KERNEL_BIN remains
            # available for a compatible Windows build.
            if os.name == "nt" and not c.lower().endswith(".exe"):
                continue
            if Path(c).is_file() and os.access(c, os.X_OK):
                return c

        which_bin = shutil.which("sonic-kernel")
        if which_bin:
            return which_bin

        return None

    def is_available(self) -> bool:
        return self.binary_path is not None and not self._native_disabled

    def _disable_native(self, exc: BaseException) -> None:
        """Disable an incompatible binary for this client lifetime."""
        self._native_disabled = True
        logger.warning(
            "Native kernel unavailable; using Python safety fallback",
            binary=self.binary_path,
            error=str(exc),
        )

    def _get_or_spawn_daemon(self) -> subprocess.Popen | None:
        """Maintains a long-lived streaming daemon for zero-overhead pipe communication."""
        if self._native_disabled:
            return None
        if self._daemon_proc is not None:
            if self._daemon_proc.poll() is None:
                return self._daemon_proc
            self._daemon_proc = None

        if not self.binary_path or not Path(self.binary_path).is_file():
            return None

        try:
            self._daemon_proc = subprocess.Popen(
                [self.binary_path, "--daemon"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            return self._daemon_proc
        except OSError as exc:
            if getattr(exc, "winerror", None) == 193:
                self._disable_native(exc)
            else:
                logger.debug("Failed to spawn native kernel persistent daemon: %s", exc)
            self._daemon_proc = None
            return None
        except Exception as exc:
            logger.debug("Failed to spawn native kernel persistent daemon: %s", exc)
            self._daemon_proc = None
            return None

    def _execute_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Executes a JSON-RPC method call to the native kernel via persistent pipe or fallback."""
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        })

        if not self.binary_path or self._native_disabled:
            return None

        # 1. Microsecond streaming pipe over persistent daemon
        daemon = self._get_or_spawn_daemon()
        if daemon and daemon.stdin and daemon.stdout:
            try:
                daemon.stdin.write(payload + "\n")
                daemon.stdin.flush()
                line = daemon.stdout.readline()
                if line and line.strip():
                    data = json.loads(line.strip())
                    if "result" in data:
                        return data["result"]
                    if "error" in data:
                        logger.warning("Native kernel returned RPC error: %s", data["error"])
                        return None
            except Exception as pipe_err:
                logger.debug("Persistent pipe streaming failed, restarting daemon: %s", pipe_err)
                try:
                    daemon.kill()
                except Exception:
                    pass
                self._daemon_proc = None

        # 2. Fallback to one-shot subprocess invocation (preserves test patches and single-shot runs)
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
        except OSError as e:
            if getattr(e, "winerror", None) == 193:
                self._disable_native(e)
            else:
                logger.debug("Failed to query native kernel RPC: %s", e)
            return None
        except Exception as e:
            logger.debug("Failed to query native kernel RPC: %s", e)
            return None

        return None

    def close(self) -> None:
        """Cleanly terminate the persistent streaming daemon process."""
        if self._daemon_proc is not None:
            try:
                self._daemon_proc.terminate()
                self._daemon_proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._daemon_proc.kill()
                except Exception:
                    pass
            finally:
                self._daemon_proc = None

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

    def desktop_snapshot(
        self,
        *,
        width: int,
        height: int,
        active_window: str,
        windows: list[str],
        processes: list[str],
        visible_text: list[str],
        controls: list[str],
        screenshot: str = "",
    ) -> dict[str, Any] | None:
        """Publish a computer-wide state snapshot to the native perception runtime."""
        return self._execute_rpc("desktop_snapshot", {
            "width": width,
            "height": height,
            "active_window": active_window,
            "windows": windows,
            "processes": processes,
            "visible_text": visible_text,
            "controls": controls,
            "screenshot": screenshot,
        })

    def desktop_action_check(self, expected_version: int) -> dict[str, Any] | None:
        """Reject GUI actions prepared against an older desktop snapshot."""
        return self._execute_rpc("desktop_action_check", {
            "expected_version": expected_version,
        })

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

    # ------------------------------------------------------------------
    # NEXUS स्वरूप-0 native scorers (Multi-Mind Parliament + World Twin)
    # ------------------------------------------------------------------
    def nexus_parliament_consensus(
        self,
        votes: list[tuple[int, str, float]],
        weights: list[float] | None = None,
    ) -> dict[str, Any] | None:
        """Native Rust Multi-Mind Parliament consensus.

        `votes` is a list of (branch_index, vote_key, confidence) where
        vote_key is one of "support" | "oppose" | "abstain" | "veto".
        Branch indices MUST match Rust: 0=Strategist 1=Skeptic 2=Historian
        3=RiskGovernor 4=MethodInventor. Returns None when the kernel is
        unavailable so callers fall back to the Cython/Python scorer.
        """
        if weights is None:
            weights = [1.0, 1.0, 0.6, 1.2, 0.4]
        norm_votes: list[dict[str, Any]] = []
        for branch, vote_key, conf in votes:
            vote_map = {
                "support": "Support",
                "oppose": "Oppose",
                "abstain": "Abstain",
                "veto": "Veto",
            }
            norm_votes.append({
                "branch": int(branch),
                "vote": vote_map.get(str(vote_key).lower(), "Abstain"),
                "confidence": float(conf),
            })
        return self._execute_rpc("nexus_parliament_consensus", {
            "weights": weights,
            "votes": norm_votes,
        })

    def nexus_world_twin_roll_forward(
        self,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Native Rust World-Twin roll-forward accumulation.

        `steps` is a list of {"action": str, "expected_info_gain": float,
        "cost": float}. Returns {"total_gain", "total_cost", "depth",
        "actions"} when the kernel is available, else None.
        """
        norm_steps = [
            {
                "action": str(s.get("action", "")),
                "expected_info_gain": float(s.get("expected_info_gain", 0.0)),
                "cost": float(s.get("cost", 0.0)),
            }
            for s in (steps or [])
        ]
        return self._execute_rpc("nexus_world_twin_roll_forward", {"steps": norm_steps})

    def find_attack_chains(
        self,
        start_node: str,
        target_node: str,
        nodes: list[dict[str, Any]] | None = None,
        transitions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]] | None:
        """Finds multi-hop attack paths via native Rust AttackGraph traversal."""
        return self._execute_rpc(
            "find_attack_chains",
            {
                "start_node": str(start_node),
                "target_node": str(target_node),
                "nodes": nodes or [],
                "transitions": transitions or [],
            },
        )
