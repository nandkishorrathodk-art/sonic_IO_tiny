"""
SONIC-REDA — Method-Invention Loop (Phase B → AIOSR)
====================================================
The "researcher" leg of the AI-Human: the being synthesizes a NOVEL offensive
*technique* (not just a new tool) from an observation + a prior failure + the
known-technique ledger in VectorMemory. A technique is a small, concrete
attack method — e.g. a parser-confusion chain, an auth-bypass logic, a fuzzer
mutation strategy, a header-injection primitive — implemented as a short Python
probe that runs against a target and emits a reproducible finding.

This closes the one gap that kept SONIC an "Operator" rather than a "Researcher":
CuriosityLoop proposes new GOALS; the MethodLab proposes new METHODS. A method
is recorded as ``confirmed`` ONLY after it actually reproduces a finding
in-sandbox — never by decree.

HONESTY INVARIANT (mirrors the production_gate + toolsmith discipline):
    * A synthesized technique is labeled ``discovered_by: "self_invented"`` and
      ``confirmed: False`` until ``confirm()`` runs its probe in-sandbox and
      gets a non-empty finding.
    * The known-technique ledger is consulted so "novel" means genuinely outside
      what the being already knows — the LLM is explicitly biased away from the
      top known techniques (semantic search of VectorMemory).
    * A technique that duplicates a known one is rejected (not invented).
    * A technique that is blocked (exit 126) or produces no finding is recorded
      UNCONFIRMED — it is NOT added to the ledger as a working method.

SECURITY INVARIANT:
    The technique probe runs strictly inside the sandbox provider (never on the
    host). Its target must pass the existing egress filter (the SECURITY_TOOL
    path already enforces this). A probe that tries to escape the workspace is
    contained by the sandbox provider's own fail-closed gate.

Integration:
    MethodLab reuses ToolsmithLoop to author + run the probe that implements the
    technique (Phase A gave Phase B its execution substrate). A confirmed
    technique's probe becomes a registered callable tool, so the being can later
    re-run the method against new targets through the same SECURITY_TOOL path.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sonic.llm.prompts import method_lab_system_prompt
from sonic.logger import get_logger

logger = get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _method_lab_db_path() -> str:
    from sonic.memory.sqlite_graph import _default_db_path as _g
    return os.environ.get("SONIC_METHOD_LAB_DB_PATH") or os.environ.get("SONIC_MEMORY_DB_PATH") or _g()

# The vector-memory namespace for the known-technique ledger. Techniques are
# indexed under this doc_id prefix so novelty search is scoped to methods, not
# to the curiosity loop's learned facts.
_TECHNIQUE_DOC_PREFIX = "technique-"


@dataclass
class InventedTechnique:
    """A technique the being synthesized itself (method + probe + run state)."""
    technique_id: str
    name: str
    family: str               # e.g. "auth-bypass", "parser-confusion", "fuzz-mutation"
    hypothesis: str           # the novel idea: what it tries and why it's new
    probe_source: str         # the Python that implements/tests the technique
    target_hint: str = ""    # what the probe should be aimed at (for re-runs)
    discovered_by: str = "self_invented"
    confirmed: bool = False
    reproduction_output: str = ""
    run_exit_code: int | None = None
    novelty_vs_ledger: float = 0.0   # how far from the known techniques (0..1)
    findings: list[dict[str, Any]] = field(default_factory=list)
    # Provenance timestamps for the audit trail — when the technique was
    # synthesized and when it was empirically confirmed in-sandbox.
    invented_at: str = ""
    confirmed_at: str = ""
    confirmed_workspace_id: str = ""


def _is_valid_name(name: str) -> bool:
    return bool(name) and re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None


class MethodLab:
    """Synthesize + confirm + persist novel offensive techniques.

    Args:
        llm:          an LLM router (ModelRouter) used to synthesize techniques.
        vector_memory: VectorMemory holding the known-technique ledger.
        toolsmith:    the ToolsmithLoop used to author + run the probe (Phase A).
        ledger_namespace: doc_id prefix for technique records (default
                      ``technique-``); set distinctly only for test isolation.
    """

    def __init__(
        self,
        llm: Any,
        vector_memory: Any | None,
        toolsmith: Any | None = None,
        ledger_namespace: str = _TECHNIQUE_DOC_PREFIX,
    ):
        self.llm = llm
        self.vector_memory = vector_memory
        self.toolsmith = toolsmith
        self.ledger_namespace = ledger_namespace
        self.invented: list[InventedTechnique] = []

    # ------------------------------------------------------------------
    def _ledger_facts(self) -> list[str]:
        """The list of known technique descriptions (for novelty bias)."""
        if self.vector_memory is None:
            return [t.hypothesis for t in self.invented if t.confirmed]
        try:
            results = self.vector_memory.search(
                "offensive technique method attack", top_k=10, score_threshold=0.0,
            )
            facts = []
            for r in results:
                meta = r.get("metadata", {}) or {}
                if meta.get("kind") == "technique":
                    facts.append(r.get("text", ""))
            # Also include in-session confirmed techniques not yet persisted.
            facts.extend(t.hypothesis for t in self.invented if t.confirmed)
            return facts
        except Exception as e:
            logger.warning("method_lab_ledger_read_failed", error=str(e))
            return [t.hypothesis for t in self.invented if t.confirmed]

    def _novelty(self, hypothesis: str, known: list[str]) -> float:
        """How far the hypothesis is from the known ledger (0=identical, 1=novel)."""
        from sonic.researcher.anomaly_engine import NoveltyEngine
        return NoveltyEngine.compute_novelty(hypothesis, known) if known else 1.0

    async def _llm_synthesize(
        self,
        observation: str,
        failure: str,
        known_techniques: list[str],
    ) -> dict[str, str] | None:
        """Ask the LLM to synthesize a NOVEL technique away from the ledger.

        Returns ``{name, family, hypothesis, probe_source, target_hint}`` or
        ``None`` if the LLM declines / proposes a known technique.
        """
        from sonic.llm.schemas import LLMRequest, Message, MessageRole

        known_str = "\n".join(f"- {t}" for t in known_techniques[:8]) or "(no known techniques yet)"
        system = method_lab_system_prompt(known_str)
        user = (
            f"Observation:\n{observation}\n\n"
            f"Failed attempt (what did NOT work):\n{failure or '(none)'}\n"
        )
        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=system),
                Message(role=MessageRole.USER, content=user),
            ],
            task_type="reasoning",
        )
        try:
            response = await self.llm.complete(request)
        except Exception as e:
            logger.warning("method_lab_llm_failed", error=str(e))
            return None

        text = getattr(response, "content", "") or ""
        if text.strip().splitlines()[0:1] and "DECLINE" in text.strip().splitlines()[0]:
            return None
        return self._parse_synthesis(text, known_techniques)

    @staticmethod
    def _parse_synthesis(text: str, known: list[str]) -> dict[str, str] | None:
        """Parse the LLM synthesis. None on any flaw (incl. a known duplicate)."""
        fields: dict[str, str] = {}
        probe_lines: list[str] = []
        in_probe = False
        for line in text.splitlines():
            if in_probe:
                probe_lines.append(line)
                continue
            key = line.split(":", 1)[0].strip().upper() if ":" in line else ""
            if key in ("NAME", "FAMILY", "HYPOTHESIS", "TARGET_HINT"):
                fields[key] = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("PROBE_SOURCE:"):
                in_probe = True
                rest = line.split(":", 1)[1]
                if rest.strip():
                    probe_lines.append(rest)
        probe_source = "\n".join(probe_lines).strip()
        name = fields.get("NAME", "").lower()
        hypothesis = fields.get("HYPOTHESIS", "")
        if not _is_valid_name(name) or not hypothesis or not probe_source:
            return None
        # Reject if the hypothesis is (near-)identical to a known technique.
        known_lower = [k.lower() for k in known]
        if any(hypothesis.lower() in k or k in hypothesis.lower() for k in known_lower):
            return None
        return {
            "name": name,
            "family": fields.get("FAMILY", "other"),
            "hypothesis": hypothesis,
            "target_hint": fields.get("TARGET_HINT", ""),
            "probe_source": probe_source,
        }

    # ------------------------------------------------------------------
    async def invent(
        self,
        observation: str,
        failure: str = "",
    ) -> InventedTechnique | None:
        """Synthesize a novel technique for the observation+failure.

        The technique is recorded (in-memory + persisted to the ledger) but
        ``confirmed`` stays False until ``confirm()`` runs the probe. Returns
        ``None`` when no novel technique is warranted (honest skip).
        """
        known = self._ledger_facts()
        spec = await self._llm_synthesize(observation, failure, known)
        if spec is None:
            logger.info("method_lab_no_novel_technique", known_count=len(known))
            return None

        novelty = self._novelty(spec["hypothesis"], known)
        technique = InventedTechnique(
            technique_id=f"tech-{abs(hash(spec['name'] + spec['hypothesis'])) % 10**8}",
            name=spec["name"],
            family=spec["family"],
            hypothesis=spec["hypothesis"],
            probe_source=spec["probe_source"],
            target_hint=spec["target_hint"],
            novelty_vs_ledger=novelty,
            invented_at=datetime.now(UTC).isoformat(),
        )
        self.invented.append(technique)
        logger.info(
            "method_lab_technique_invented", name=technique.name,
            family=technique.family, novelty=technique.novelty_vs_ledger,
            confirmed=False,
        )
        return technique

    async def confirm(
        self,
        technique: InventedTechnique,
        provider: Any,
        workspace_id: str,
        target: str = "",
        timeout: int = 60,
    ) -> InventedTechnique:
        """Run the technique's probe in-sandbox. Confirm ONLY on a real finding.

        If a ToolsmithLoop is wired, the probe is authored + run + (on success)
        registered as a callable tool — so a confirmed technique can be re-run
        against new targets through the SECURITY_TOOL path. If no toolsmith is
        wired, the probe is run directly via the provider (still in-sandbox,
        still fail-closed). The technique is added to the known-technique
        ledger (VectorMemory) ONLY when confirmed.
        """
        run_target = target or technique.target_hint or "localhost"
        if self.toolsmith is not None:
            # Route through the toolsmith so the probe becomes a real tool too.
            from sonic.being.toolsmith import AuthoredTool
            # Build a transient AuthoredTool from the technique's probe.
            probe = AuthoredTool(
                name=technique.name, source=technique.probe_source,
                rationale=technique.hypothesis,
            )
            self.toolsmith.authored.append(probe)
            probe = await self.toolsmith.confirm_and_register(
                probe, provider, workspace_id, timeout=timeout, target=run_target,
            )
            technique.run_exit_code = probe.run_exit_code
            technique.reproduction_output = probe.run_output
            technique.confirmed = probe.reproduced
        else:
            # Direct in-sandbox run (no toolsmith): still fail-closed via provider.
            if provider is None or not hasattr(provider, "execute"):
                return technique
            path = f"/home/sonic/workspace/toolsmith/{technique.name}.py"
            try:
                if hasattr(provider, "write_file"):
                    await provider.write_file(workspace_id, path, technique.probe_source)
                command = f"python {shlex.quote(path)} {shlex.quote(str(run_target))}"
                res = await provider.execute(workspace_id, command, timeout=timeout)
                technique.run_exit_code = getattr(res, "exit_code", None)
                technique.reproduction_output = getattr(res, "stdout", "") or ""
                output_lower = technique.reproduction_output.lower()
                failure_markers = [
                    "connection refused",
                    "command not found",
                    "syntaxerror",
                    "traceback",
                    "usage:",
                    "error:",
                ]
                has_failure = any(marker in output_lower for marker in failure_markers)
                technique.confirmed = (
                    technique.run_exit_code == 0
                    and technique.reproduction_output.strip() != ""
                    and not has_failure
                )
            except Exception as e:
                logger.warning("method_lab_confirm_failed", name=technique.name, error=str(e))

        if technique.confirmed:
            # Parse the reproduction output into structured findings.
            technique.findings = self._parse_findings(technique.reproduction_output)
            technique.confirmed_at = datetime.now(UTC).isoformat()
            technique.confirmed_workspace_id = workspace_id
            self._persist_to_ledger(technique)
            logger.info(
                "method_lab_technique_confirmed", name=technique.name,
                findings=len(technique.findings),
            )
        else:
            logger.info(
                "method_lab_technique_not_confirmed", name=technique.name,
                exit_code=technique.run_exit_code,
            )
        return technique

    @staticmethod
    def _parse_findings(stdout: str) -> list[dict[str, Any]]:
        """Parse JSON lines from the probe output (falls back to plain lines)."""
        import json as _json
        findings: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                findings.append(_json.loads(line))
            except Exception:
                findings.append({"finding": line})
        return findings

    def _persist_to_ledger(self, technique: InventedTechnique) -> None:
        """Add a CONFIRMED technique to the known-technique ledger (VectorMemory).

        Only confirmed techniques enter the ledger, so the ledger is a record
        of WORKING methods — not aspirations. Future invent() calls see these
        and steer away, so novelty compounds.
        """
        if self.vector_memory is None:
            return
        try:
            doc_id = f"{self.ledger_namespace}{technique.technique_id}"
            self.vector_memory.index_document(
                doc_id,
                f"[{technique.family}] {technique.name}: {technique.hypothesis}",
                metadata={"kind": "technique", "name": technique.name,
                          "family": technique.family, "confirmed": True},
            )
        except Exception as e:
            logger.warning("method_lab_ledger_persist_failed", error=str(e))

# ---------------------------------------------------------------------------
# NEXUS L6 -- Offense-Generative Vulnerability Researcher
# ---------------------------------------------------------------------------

@dataclass
class OffenseHypothesis:
    """A mutated vulnerability-class hypothesis generated from known patterns."""
    hypothesis_id: str
    family: str                 # mutation lineage
    source_patterns: list[str]
    mutated_technique: str
    parameters: dict[str, Any] = field(default_factory=dict)
    novelty_score: float = 0.0
    status: str = "generated"   # generated | tested | confirmed | rejected
    note: str = ""
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "family": self.family,
            "source_patterns": self.source_patterns,
            "mutated_technique": self.mutated_technique,
            "parameters": self.parameters,
            "novelty_score": self.novelty_score,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at,
        }


# Known vulnerability-pattern genome. Each carries deterministic mutation hooks.
KNOWN_VULN_PATTERNS: dict[str, list[str]] = {
    "sql_injection": [
        "parameterized query boundary",
        "boolean-based differential",
        "time-based sleep oracle",
        "union column enumeration",
    ],
    "xss": [
        "reflected sink",
        "DOM write sink",
        "event-handler attribute",
        "svg/math namespace tag",
    ],
    "ssrf": [
        "URL fetch endpoint",
        "redirect-following fetch",
        "DNS rebinding candidate",
        "protocol-relative fetch",
    ],
    "deserialization": [
        "untrusted object stream",
        "gadget chain discovery",
        "magic-method invocation",
        "type confusion on read",
    ],
    "auth_bypass": [
        "token replay",
        "password-reset oracle",
        "path-based role check",
        "JWT algorithm confusion",
    ],
    "race_condition": [
        "TOCTOU file op",
        "double-spend ledger",
        "limit-check-then-spend",
        "async idempotency bypass",
    ],
    "crypto_flaw": [
        "constant-time comparison missing",
        "deterministic IV reuse",
        "padding oracle",
        "weak key derivation",
    ],
    "template_injection": [
        "expression sandbox escape",
        "undefined-variable reflection",
        "recursive render hook",
        "config-delegate leak",
    ],
}

_MUTATORS = (
    "transpose_to_domain",     # carry the trick into another class (cross-domain)
    "parameterize_surface",    # generalize the injection point
    "conjoin_classes",         # combine two patterns into a compound hypothesis
    "invert_condition",        # flip the boolean expectation
)


class OffenseGenerator:
    """Grows a private catalog of vulnerability-class hypotheses via mutation.

    Pure hypothesis generation — no execution. A hypothesis is only worth
    testing, and only registered as a confirmed pattern after an empirical
    reproduction elsewhere (mark_tested).
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _method_lab_db_path()
        self._hypotheses: dict[str, OffenseHypothesis] = {}
        self._init_db()
        self._hydrate()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS offense_hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    family TEXT,
                    source_patterns TEXT,
                    mutated_technique TEXT,
                    parameters_json TEXT,
                    novelty_score REAL,
                    status TEXT,
                    note TEXT,
                    created_at TEXT
                )
                """
            )

    def _hydrate(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT hypothesis_id, family, source_patterns, mutated_technique,"
                    " parameters_json, novelty_score, status, note, created_at"
                    " FROM offense_hypotheses"
                ).fetchall()
            for hid, family, sp, mt, pj, novelty, status, note, created_at in rows:
                params = json.loads(pj) if pj else {}
                self._hypotheses[hid] = OffenseHypothesis(
                    hypothesis_id=hid, family=family,
                    source_patterns=json.loads(sp) if sp else [],
                    mutated_technique=mt, parameters=params, novelty_score=novelty,
                    status=status, note=note or "", created_at=created_at,
                )
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.warning("offense_hydrate_failed", error=str(e))

    def _persist(self, h: OffenseHypothesis) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO offense_hypotheses VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        h.hypothesis_id, h.family, json.dumps(h.source_patterns),
                        h.mutated_technique, json.dumps(h.parameters),
                        h.novelty_score, h.status, h.note, h.created_at,
                    ),
                )
        except sqlite3.Error as e:
            logger.warning("offense_persist_failed", error=str(e))

    @staticmethod
    def _novelty(family: str, parameters: dict[str, Any], mutated: str) -> float:
        """Deterministic novelty proxy: derivative complexity of the mutation."""
        complexity = len(parameters) * 0.2 + 0.1
        domain_cross = 0.5 if "transpose" in family else 0.0
        conjoined = 0.3 if "conjoin" in family else 0.0
        return round(min(1.0, 0.2 + complexity + domain_cross + conjoined), 3)

    def generate(
        self,
        limit: int = 12,
        families: list[str] | None = None,
    ) -> list[OffenseHypothesis]:
        """Generate new class hypotheses by mutating the known pattern genome."""
        patterns = KNOWN_VULN_PATTERNS if not families else {k: v for k, v in KNOWN_VULN_PATTERNS.items() if k in families}
        generated: list[OffenseHypothesis] = []
        class_names = list(patterns.keys())

        for family in class_names:
            techniques = patterns[family]
            for idx, mutant_name in enumerate(_MUTATORS):
                if idx >= limit:
                    break
                technique = techniques[idx % len(techniques)]
                hid = f"off-{uuid.uuid4().hex[:10]}"
                param = {"source": family, "mutator": mutant_name, "surface": technique}
                if mutant_name == "conjoin_classes" and len(class_names) > 1:
                    other = class_names[0] if family != class_names[0] else class_names[1]
                    param["conjoined_with"] = other
                mutate_technique = f"{technique} -> {mutant_name} ({family})"
                hypothesis = OffenseHypothesis(
                    hypothesis_id=hid,
                    family=family,
                    source_patterns=techniques[:2],
                    mutated_technique=mutate_technique,
                    parameters=param,
                    novelty_score=self._novelty(mutant_name, param, mutate_technique),
                )
                self._hypotheses[hid] = hypothesis
                self._persist(hypothesis)
                generated.append(hypothesis)

        return generated

    def mark_tested(self, hypothesis_id: str, confirmed: bool, evidence: str) -> bool:
        hyp = self._hypotheses.get(hypothesis_id)
        if not hyp:
            return False
        hyp.status = "confirmed" if confirmed else "rejected"
        if evidence:
            hyp.note = evidence
        self._persist(hyp)
        return True

    def confirmed_catalog(self) -> list[OffenseHypothesis]:
        return [h for h in self._hypotheses.values() if h.status == "confirmed"]

    def hypotheses(self) -> list[OffenseHypothesis]:
        return list(self._hypotheses.values())

    def count(self) -> int:
        return len(self._hypotheses)


# ---------------------------------------------------------------------------
# NEXUS L7 -- Adversarial Self-Play Arena
# ---------------------------------------------------------------------------

@dataclass
class ArenaRound:
    """One attacker-vs-defender exchange."""
    round_id: str
    attack_technique: str
    defense_model: str
    attack_score: float
    defense_score: float
    counterfactual_signal: str
    attack_adaptation: str
    defense_adaptation: str
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "attack_technique": self.attack_technique,
            "defense_model": self.defense_model,
            "attack_score": self.attack_score,
            "defense_score": self.defense_score,
            "counterfactual_signal": self.counterfactual_signal,
            "attack_adaptation": self.attack_adaptation,
            "defense_adaptation": self.defense_adaptation,
            "timestamp": self.timestamp,
        }


class AdversarialArena:
    """Closed-world attacker/defender simulation producing training signals.

    Round flow:
        1. Attacker proposes a technique/hypothesis.
        2. Defender responds with a defense model.
        3. A neutral referee scores the exchange (attack novelty x defense
           soundness), producing a counterfactual signal.
        4. Lessons persist (attack-strength, defense-strength, adapt directive).

    Pure closed-world modeling — no real target is ever touched.
    """

    _ATTACK_ANCHORS = ("novel", "blind", "chained", "persistent", "stealth")
    _DEFENSE_ANCHORS = ("segmentation", "canary", "rate-limit", "normalization", "allowlist")

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _method_lab_db_path()
        self._rounds: dict[str, ArenaRound] = {}
        self._round_counter = 0
        self._init_db()
        self._hydrate()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS arena_rounds (
                    round_id TEXT PRIMARY KEY,
                    attack_technique TEXT,
                    defense_model TEXT,
                    attack_score REAL,
                    defense_score REAL,
                    counterfactual_signal TEXT,
                    attack_adaptation TEXT,
                    defense_adaptation TEXT,
                    timestamp TEXT
                )
                """
            )

    def _hydrate(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT round_id, attack_technique, defense_model, attack_score,"
                    " defense_score, counterfactual_signal, attack_adaptation,"
                    " defense_adaptation, timestamp FROM arena_rounds"
                ).fetchall()
            for r in rows:
                self._rounds[r[0]] = ArenaRound(
                    round_id=r[0], attack_technique=r[1], defense_model=r[2],
                    attack_score=r[3], defense_score=r[4], counterfactual_signal=r[5],
                    attack_adaptation=r[6], defense_adaptation=r[7], timestamp=r[8],
                )
        except sqlite3.Error as e:
            logger.warning("arena_hydrate_failed", error=str(e))

    def _persist(self, r: ArenaRound) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO arena_rounds VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        r.round_id, r.attack_technique, r.defense_model,
                        r.attack_score, r.defense_score, r.counterfactual_signal,
                        r.attack_adaptation, r.defense_adaptation, r.timestamp,
                    ),
                )
        except sqlite3.Error as e:
            logger.warning("arena_persist_failed", error=str(e))

    @staticmethod
    def _score(text: str, anchors: tuple[str, ...]) -> float:
        hits = sum(1 for a in anchors if a in text.lower())
        return round(min(1.0, 0.25 + 0.15 * hits), 3)

    def play_round(
        self,
        attack_technique: str,
        defense_model: str,
        attack_adaptation: str = "",
        defense_adaptation: str = "",
    ) -> ArenaRound:
        """Run one attacker/defender exchange and persist the lesson."""
        self._round_counter += 1
        attack_score = self._score(attack_technique, self._ATTACK_ANCHORS)
        defense_score = self._score(defense_model, self._DEFENSE_ANCHORS)
        signal = (
            f"attack={attack_score:.2f}:defense={defense_score:.2f} -> "
            f"{'LEAN-ATTACK-CONTINUE' if attack_score > defense_score else 'HARDEN-DEFENSE'}"
        )
        round_ = ArenaRound(
            round_id=f"arena-{self._round_counter:06d}",
            attack_technique=attack_technique,
            defense_model=defense_model,
            attack_score=attack_score,
            defense_score=defense_score,
            counterfactual_signal=signal,
            attack_adaptation=attack_adaptation or (
                "adapt: pursue higher-novelty vector" if attack_score >= defense_score else "adapt: diversify approach"
            ),
            defense_adaptation=defense_adaptation or "defense: reinforce modeled boundary",
        )
        self._rounds[round_.round_id] = round_
        self._persist(round_)
        return round_

    def lessons(self, limit: int = 50) -> list[ArenaRound]:
        rounds = list(self._rounds.values())
        rounds.sort(key=lambda r: r.timestamp, reverse=True)
        return rounds[:limit]

    def round_count(self) -> int:
        return len(self._rounds)