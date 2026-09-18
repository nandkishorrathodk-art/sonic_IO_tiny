"""
SONIC v2 — Decision Engine, Dead-End Pivot System & L2 Multi-Mind Parliament
============================================================================
Prevents infinite repetition and aimless looping. Treats 'DEAD END' as a
first-class epistemic state and mandates pivots.

NEXUS L2 — Multi-Mind Parliament
================================
Enables disagreement-preserving cognitive committees: instead of one scalar
opinion, every decision is contested by a parliament of branches structured to
DISAGREE (Strategist / Skeptic / Historian / RiskGovernor / MethodInventor).
Weighted consensus produces a credibility score; dissenting opinions are
preserved verbatim as an epistemic contradiction record instead of being
averaged away.

HONESTY INVARIANT (mirrors the evidence engine): a branch may only vote
support/oppose with a grounded rationale; empty-rationale opposition ballots
are rejected. This module holds zero tool handles and executes nothing.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)

# Cython hot-path acceleration: mirrors the existing fast_graph.py seam.
# @cython.cfunc decorated helpers compile to C speed when the module is run
# through Cython; the fallback mock keeps them pure-Python otherwise.
try:
    import cython
    CYTHON_AVAILABLE = True
except ImportError:
    CYTHON_AVAILABLE = False

    class _CythonMock:
        compiled = False

        @staticmethod
        def cfunc(f):
            return f

        @staticmethod
        def inline(f):
            return f

        @staticmethod
        def locals(**kwargs):
            return lambda f: f

        int = int
        float = float
        Py_ssize_t = int

    cython = _CythonMock()


def _parliament_db_path() -> str:
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_PARLIAMENT_DB_PATH") or os.environ.get("SONIC_MEMORY_DB_PATH") or _g()


@cython.cfunc
def _weighted_consensus_score(votes: list[Any]) -> tuple[float, float, float]:
    """Cython-hot-path weighted consensus for a parliament session.

    Returns (credibility, support_weight, oppose_weight). Pure arithmetic over
    the vote tuples — the fastest inner loop of the parliament; cpdef/fallback
    keeps correctness identical when Cython is unavailable.
    """
    total: cython.float = 0.0
    support: cython.float = 0.0
    oppose: cython.float = 0.0
    weights: dict[Any, cython.float] = {
        BranchRole.STRATEGIST: 1.0,
        BranchRole.SKEPTIC: 1.0,
        BranchRole.HISTORIAN: 0.6,
        BranchRole.RISK_GOVERNOR: 1.2,
        BranchRole.METHOD_INVENTOR: 0.4,
    }
    for branch, vote, confidence in votes:
        w = weights.get(branch, 1.0) * confidence
        total += w
        if vote == Vote.SUPPORT:
            support += w
        elif vote == Vote.OPPOSE:
            oppose += w
    credibility = support / total if total > 0.0 else 0.0
    if credibility > 1.0:
        credibility = 1.0
    return credibility, support, oppose


class DecisionAction(StrEnum):
    PROCEED = "proceed"
    PIVOT = "pivot"
    PAUSE_REVIEW = "pause_review"
    TERMINATE = "terminate"


@dataclass
class DecisionTrace:
    action: DecisionAction
    target_asset: str
    rationale: str
    strategy: str
    alternative_strategies: list[str] = field(default_factory=list)
    consecutive_failures: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DecisionEngine:
    """Monitors mission trajectory, identifies dead-ends, and orchestrates pivots."""

    def __init__(self, failure_threshold_for_pivot: int = 3):
        self.failure_threshold = failure_threshold_for_pivot
        # Tracks failures per (asset, strategy)
        self._failure_tallies: dict[str, int] = {}
        self._dead_ends: set[str] = set()
        self._traces: list[DecisionTrace] = []

    def _key(self, asset: str, strategy: str) -> str:
        return f"{asset}::{strategy}"

    def record_success(self, asset: str, strategy: str) -> None:
        key = self._key(asset, strategy)
        self._failure_tallies[key] = 0

    def record_failure(self, asset: str, strategy: str, reason: str = "") -> DecisionTrace:
        """Records an experiment failure and assesses whether to pivot."""
        key = self._key(asset, strategy)
        current_count = self._failure_tallies.get(key, 0) + 1
        self._failure_tallies[key] = current_count

        if current_count >= self.failure_threshold:
            self._dead_ends.add(key)
            logger.warning(
                "decision_engine_dead_end_reached",
                asset=asset,
                strategy=strategy,
                failures=current_count,
            )
            trace = DecisionTrace(
                action=DecisionAction.PIVOT,
                target_asset=asset,
                rationale=f"Strategy '{strategy}' failed {current_count} consecutive times on asset '{asset}'. Declaring DEAD END and pivoting.",
                strategy=strategy,
                consecutive_failures=current_count,
                alternative_strategies=["recon_deep", "alternate_endpoint", "privilege_pivot"],
            )
        else:
            trace = DecisionTrace(
                action=DecisionAction.PROCEED,
                target_asset=asset,
                rationale=f"Failure count ({current_count}/{self.failure_threshold}) within tolerance; continuing investigation.",
                strategy=strategy,
                consecutive_failures=current_count,
            )

        self._traces.append(trace)
        return trace

    def is_dead_end(self, asset: str, strategy: str) -> bool:
        return self._key(asset, strategy) in self._dead_ends

    def get_traces(self) -> list[DecisionTrace]:
        return list(self._traces)


# ---------------------------------------------------------------------------
# NEXUS L2 -- Multi-Mind Parliament
# ---------------------------------------------------------------------------

class BranchRole(StrEnum):
    STRATEGIST = "strategist"
    SKEPTIC = "skeptic"
    HISTORIAN = "historian"
    RISK_GOVERNOR = "risk_governor"
    METHOD_INVENTOR = "method_inventor"


class Vote(StrEnum):
    SUPPORT = "support"
    OPPOSE = "oppose"
    ABSTAIN = "abstain"
    VETO = "veto"


@dataclass
class BranchVote:
    """A single branch's opinion on a proposal."""
    branch: BranchRole
    vote: Vote
    confidence: float = 0.5
    rationale: str = ""
    dissent: str = ""
    knowledge_tags: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def is_rejected_empty(self) -> bool:
        """Honesty: an OPPOSE/VETO vote with an empty rationale is invalid."""
        return self.vote in (Vote.OPPOSE, Vote.VETO) and not self.rationale.strip()


@dataclass
class ParliamentDecision:
    """The outcome of a parliamentary session over a single proposal."""
    proposal_id: str
    proposal: str
    motion: str
    context: str
    votes: list[BranchVote] = field(default_factory=list)
    consensus_credibility: float = 0.0
    dissent_count: int = 0
    dissent_record: list[dict[str, str]] = field(default_factory=list)
    outcome: str = "undecided"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposal": self.proposal,
            "motion": self.motion,
            "context": self.context,
            "votes": [v.__dict__ for v in self.votes],
            "consensus_credibility": self.consensus_credibility,
            "dissent_count": self.dissent_count,
            "dissent_record": self.dissent_record,
            "outcome": self.outcome,
            "timestamp": self.timestamp,
        }


class MultiMindParliament:
    """A disagreement-preserving committee over any decision surface.

    The parliament is pure reasoning orchestration -- it holds no tool handles.
    Scoring uses a fixed weighted formula (strategist/skeptic weigh heaviest;
    risk_governor owns a hard veto lane), and every session is persisted to
    SQLite as an epistemic contradiction record.
    """

    _VETO_ROLES = {BranchRole.RISK_GOVERNOR, BranchRole.SKEPTIC}
    _WEIGHTS = {
        BranchRole.STRATEGIST: 1.0,
        BranchRole.SKEPTIC: 1.0,
        BranchRole.HISTORIAN: 0.6,
        BranchRole.RISK_GOVERNOR: 1.2,
        BranchRole.METHOD_INVENTOR: 0.4,
    }

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _parliament_db_path()
        self._motion_counter = 0
        self._init_db()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS parliament_decisions (
                    proposal_id TEXT PRIMARY KEY,
                    proposal TEXT,
                    motion TEXT,
                    context TEXT,
                    outcome TEXT,
                    consensus_credibility REAL,
                    dissent_count INTEGER,
                    record_json TEXT,
                    created_at TEXT
                )
                """
            )

    def _persist(self, decision: ParliamentDecision) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO parliament_decisions VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        decision.proposal_id,
                        decision.proposal,
                        decision.motion,
                        decision.context,
                        decision.outcome,
                        decision.consensus_credibility,
                        decision.dissent_count,
                        json.dumps(decision.to_dict()),
                        decision.timestamp,
                    ),
                )
        except sqlite3.Error as e:
            logger.warning("parliament_persist_failed", error=str(e))

    def list_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT record_json FROM parliament_decisions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [json.loads(r[0]) for r in rows]
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.warning("parliament_list_failed", error=str(e))
            return []

    def _default_votes(self, motion: str, context: str) -> list[BranchVote]:
        """Deterministic shell ballots; the LLM supplants this in production."""
        return [
            BranchVote(
                branch=BranchRole.STRATEGIST,
                vote=Vote.SUPPORT,
                confidence=0.7,
                rationale=f"'{motion}' advances the current objective with the "
                          f"highest expected information gain given '{context}'.",
            ),
            BranchVote(
                branch=BranchRole.SKEPTIC,
                vote=Vote.SUPPORT,
                confidence=0.5,
                rationale="No falsifying evidence present in the stated context.",
            ),
            BranchVote(
                branch=BranchRole.HISTORIAN,
                vote=Vote.SUPPORT,
                confidence=0.6,
                rationale="Consistent with historical patterns in this domain.",
            ),
            BranchVote(
                branch=BranchRole.RISK_GOVERNOR,
                vote=Vote.ABSTAIN,
                confidence=1.0,
                rationale="No safety-critical parameters known for this static motion.",
            ),
            BranchVote(
                branch=BranchRole.METHOD_INVENTOR,
                vote=Vote.ABSTAIN,
                confidence=0.3,
                rationale="No novelty surplus claimed for a static motion.",
            ),
        ]

    @staticmethod
    def _native_or_python_consensus(final_votes: list[BranchVote]) -> tuple[float, float, float]:
        """Prefer the native Rust NEXUS parliament scorer; fall back to the
        Cython-hot-path scorer when the kernel binary is unavailable."""
        branch_idx = {
            BranchRole.STRATEGIST: 0,
            BranchRole.SKEPTIC: 1,
            BranchRole.HISTORIAN: 2,
            BranchRole.RISK_GOVERNOR: 3,
            BranchRole.METHOD_INVENTOR: 4,
        }
        try:
            from sonic.kernel.native_bridge import NativeKernelClient
            client = NativeKernelClient()
            if client.is_available():
                rust_votes = [
                    (
                        branch_idx[v.branch],
                        v.vote.value,
                        float(v.confidence),
                    )
                    for v in final_votes
                ]
                res = client.nexus_parliament_consensus(rust_votes)
                if res and "credibility" in res:
                    return (
                        float(res["credibility"]),
                        float(res.get("support_weight", 0.0)),
                        float(res.get("oppose_weight", 0.0)),
                    )
        except Exception:
            logger.debug("native_parliament_consensus_unavailable", exc_info=True)

        return _weighted_consensus_score(
            [(v.branch, v.vote, v.confidence) for v in final_votes]
        )

    def convene(
        self,
        proposal: str,
        motion: str,
        context: str = "",
        votes: list[BranchVote] | None = None,
    ) -> ParliamentDecision:
        """Run a full parliamentary session over a motion."""
        self._motion_counter += 1
        proposal_id = f"par-{self._motion_counter:06d}"

        final_votes = votes if votes is not None else self._default_votes(motion, context)
        final_votes = [v for v in final_votes if not v.is_rejected_empty]

        for v in final_votes:
            if v.vote == Vote.VETO and v.branch in self._VETO_ROLES:
                decision = ParliamentDecision(
                    proposal_id=proposal_id,
                    proposal=proposal,
                    motion=motion,
                    context=context,
                    votes=final_votes,
                    consensus_credibility=0.0,
                    dissent_count=sum(1 for x in final_votes if x.vote in (Vote.OPPOSE, Vote.VETO)),
                    dissent_record=[
                        {"branch": x.branch.value, "rationale": x.rationale}
                        for x in final_votes if x.vote in (Vote.OPPOSE, Vote.VETO)
                    ],
                    outcome="vetoed",
                )
                self._persist(decision)
                return decision

        # Fast native-Rust weighted consensus (NEXUS स्वरूप-0), falling back to
        # the Cython-hot-path scorer (pure-Python fallback identical) whenever the
        # kernel binary is unavailable. Veto has already been handled above.
        credibility, support_w, oppose_w = self._native_or_python_consensus(final_votes)

        dissent = [v for v in final_votes if v.vote in (Vote.OPPOSE, Vote.VETO)]
        if credibility >= 0.6 and not oppose_w >= support_w:
            outcome = "approve"
        elif oppose_w > support_w:
            outcome = "oppose"
        else:
            outcome = "undecided"

        decision = ParliamentDecision(
            proposal_id=proposal_id,
            proposal=proposal,
            motion=motion,
            context=context,
            votes=final_votes,
            consensus_credibility=credibility,
            dissent_count=len(dissent),
            dissent_record=[
                {"branch": v.branch.value, "rationale": v.rationale} for v in dissent
            ],
            outcome=outcome,
        )
        self._persist(decision)
        return decision

    def approve_hard_gate(
        self,
        proposal: str,
        motion: str,
        context: str = "",
        explicit_votes: list[BranchVote] | None = None,
    ) -> bool:
        """Convenience: does the full parliament approve this motion?"""
        decision = self.convene(proposal, motion, context, votes=explicit_votes)
        return decision.outcome == "approve"
