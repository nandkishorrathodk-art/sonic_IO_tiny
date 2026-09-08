"""
SONIC-REDA — Sealed (Tamper-Evident) Safety Policy
====================================================

Closes the PLAN.md audit item:

    "Safety immutability: guards are real but NOT protected from a
     self-evolving agent modifying them (no read-only/signed layer)."

The existing ``ActionPolicy`` is a plain mutable Python object: its attributes
are reassignable, ``security_tool_targets`` is a mutable set, and the egress
filter consults a module-level *mutable* ``BLOCKED_NETWORKS`` list. A
self-evolving being running in-process could widen the envelope at runtime
(``policy.security_tool_targets.add(...)``, ``policy.self_host = False``, or
``egress.BLOCKED_NETWORKS.clear()``) and then act — the guards would no longer
protect it.

``SealedActionPolicy`` makes the safety-relevant config tamper-evident:

    * At ``seal()`` time it freezes a snapshot of every field that controls the
      verdict (allowed_types, security_tool_targets, rate cap, approval flag,
      workspace root, and a *copy* of the egress blocked-networks list) and
      records a SHA-256 seal hash over the canonical serialization.
    * After sealing, mutation of any safety-relevant field is refused (the
      object is effectively immutable); ``security_tool_targets`` is stored as a
      frozenset, and the blocked-networks snapshot as a tuple.
    * On every ``evaluate()`` the seal hash is recomputed and compared; any
      mismatch (i.e. the config was somehow altered) makes the verdict
      fail-closed DENY and logs ``safety_policy_tampered`` — the being may NOT
      act under a policy whose integrity cannot be proven.
    * The egress check uses the frozen blocked-networks snapshot, so a runtime
      mutation of ``egress.BLOCKED_NETWORKS`` cannot widen what this policy
      permits.

This is additive and opt-in: plain ``ActionPolicy`` still works unchanged (so
existing tests/contracts hold). The AI-Human being life loop constructs a
``SealedActionPolicy`` and seals it, so the long-lived self-directing being
always acts under a proven-intact envelope.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sonic.logger import get_logger
from sonic.safety.action_policy import ActionPolicy, PolicyVerdict
from sonic.safety.scope import ScopeChecker
from sonic.sandbox import egress

logger = get_logger(__name__)

# Fields whose values determine a verdict. After sealing these MUST NOT change.
_SEALED_FIELDS = (
    "allowed_types",
    "security_tool_targets",
    "max_actions_per_minute",
    "require_approval_for_intrusive",
    "workspace_root",
    "scope_checker",
    "scope_config",
    "_sealed",
    "_seal_hash",
    "_blocked_networks_snapshot",
)


class SealedActionPolicy(ActionPolicy):
    """A tamper-evident ActionPolicy: config is frozen + hash-sealed at seal().

    Until ``seal()`` is called the object behaves like a normal ActionPolicy
    (construct, then seal). After sealing, safety-relevant fields become
    immutable and every ``evaluate()`` re-verifies the seal.
    """

    def __init__(
        self,
        workspace_root: str = "/home/sonic/workspace",
        allowed_action_types: set[str] | None = None,
        allow_security_tool_targets: set[str] | None = None,
        max_actions_per_minute: int = 60,
        require_approval_for_intrusive: bool = True,
        scope_checker: ScopeChecker | None = None,
        scope_config: dict | None = None,
    ):
        super().__init__(
            workspace_root=workspace_root,
            allowed_action_types=allowed_action_types,
            allow_security_tool_targets=allow_security_tool_targets,
            max_actions_per_minute=max_actions_per_minute,
            require_approval_for_intrusive=require_approval_for_intrusive,
            scope_checker=scope_checker,
            scope_config=scope_config,
        )
        # Freeze the mutable target set into a frozenset immediately.
        self.security_tool_targets = frozenset(self.security_tool_targets)
        # Snapshot the egress blocked-networks so a runtime mutation of the
        # module-level list cannot widen what this policy permits.
        self._blocked_networks_snapshot: tuple = tuple(egress.BLOCKED_NETWORKS)
        self._seal_hash: str = ""
        self._sealed: bool = False

    # ------------------------------------------------------------------
    # Sealing
    # ------------------------------------------------------------------
    def seal(self) -> SealedActionPolicy:
        """Freeze the safety config and record its seal hash. Call once."""
        if self._sealed:
            return self
        # Re-freeze in case the caller mutated targets before sealing.
        self.security_tool_targets = frozenset(self.security_tool_targets)
        self._blocked_networks_snapshot = tuple(egress.BLOCKED_NETWORKS)
        self._seal_hash = self._compute_seal_hash()
        self._sealed = True
        logger.info("safety_policy_sealed", seal_hash=self._seal_hash[:12])
        return self

    @property
    def sealed(self) -> bool:
        return self._sealed

    @property
    def seal_hash(self) -> str:
        return self._seal_hash

    def _compute_seal_hash(self) -> str:
        """SHA-256 over the canonical serialization of the safety-relevant config."""
        payload = {
            "allowed_types": sorted(self.allowed_types),
            "security_tool_targets": sorted(self.security_tool_targets),
            "max_actions_per_minute": self.max_actions_per_minute,
            "require_approval_for_intrusive": self.require_approval_for_intrusive,
            "workspace_root": str(self.workspace_root),
            "blocked_networks": [str(n) for n in self._blocked_networks_snapshot],
        }
        if getattr(self, "scope_config", None):
            payload["scope_config"] = self.scope_config
        if hasattr(self, "scope_checker") and self.scope_checker is not None:
            patterns = getattr(self.scope_checker, "_destructive_patterns", getattr(self.scope_checker, "_DESTRUCTIVE_PATTERNS", []))
            forbidden = getattr(self.scope_checker, "_forbidden_patterns", [])
            payload["scope_patterns_repr"] = sorted([getattr(p, "pattern", str(p)) for p in patterns]) + sorted([getattr(p, "pattern", str(p)) for p in forbidden])
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------
    def __setattr__(self, name: str, value: Any) -> None:
        # Allow the rate window + internal bookkeeping to keep mutating.
        if name in ("_rate",):
            object.__setattr__(self, name, value)
            return
        # After sealing, refuse mutation of safety-relevant fields or seal state.
        if getattr(self, "_sealed", False) and (
            name in _SEALED_FIELDS or name in ("_sealed", "_seal_hash", "_blocked_networks_snapshot")
        ):
            logger.warning("safety_policy_mutation_blocked", field=name)
            raise AttributeError("sealed policy is immutable after seal()")
        # Always keep the target set frozen.
        if name == "security_tool_targets" and not isinstance(value, frozenset):
            value = frozenset(value)
        object.__setattr__(self, name, value)

    # ------------------------------------------------------------------
    # Tamper-evident evaluation
    # ------------------------------------------------------------------
    def evaluate(self, action_type_name: str, target: str, payload: dict[str, Any]) -> PolicyVerdict:
        """Fail-closed if the seal no longer matches the current config."""
        if self._sealed and self._compute_seal_hash() != self._seal_hash:
            logger.error(
                "safety_policy_tampered",
                expected=self._seal_hash[:12],
                actual=self._compute_seal_hash()[:12],
            )
            return PolicyVerdict(
                False, "safety policy seal mismatch — refusing to act (tamper-evident)"
            )
        return super().evaluate(action_type_name, target, payload)

    # ------------------------------------------------------------------
    # Egress uses the FROZEN blocked-networks snapshot, not the live module list.
    # ------------------------------------------------------------------
    def _check_egress(self, target: str, label: str) -> PolicyVerdict:
        verdict = self._check_target_and_scope(target, label)
        if verdict is not None:
            return verdict
        try:
            ok, reason = egress.is_target_allowed(
                target,
                blocked_networks=self._blocked_networks_snapshot,
            )
        except Exception as e:
            return PolicyVerdict(False, f"egress check failed: {e}")
        if not ok:
            return PolicyVerdict(False, f"{label} egress denied: {reason}")
        return PolicyVerdict(True, "egress allowed")


def seal_default(workspace_root: str = "/home/sonic/workspace") -> SealedActionPolicy:
    """Build + seal the standard production policy for the being life loop."""
    return SealedActionPolicy(workspace_root=workspace_root).seal()
