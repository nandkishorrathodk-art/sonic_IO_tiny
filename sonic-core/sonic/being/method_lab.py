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

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sonic.logger import get_logger

logger = get_logger(__name__)

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
    run_exit_code: Optional[int] = None
    novelty_vs_ledger: float = 0.0   # how far from the known techniques (0..1)
    findings: list[dict[str, Any]] = field(default_factory=list)


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
        vector_memory: Optional[Any],
        toolsmith: Optional[Any] = None,
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
    ) -> Optional[dict[str, str]]:
        """Ask the LLM to synthesize a NOVEL technique away from the ledger.

        Returns ``{name, family, hypothesis, probe_source, target_hint}`` or
        ``None`` if the LLM declines / proposes a known technique.
        """
        from sonic.llm.schemas import LLMRequest, Message, MessageRole

        known_str = "\n".join(f"- {t}" for t in known_techniques[:8]) or "(no known techniques yet)"
        system = (
            "You are the method-researcher of an autonomous offensive-security being. "
            "Given an observation, a FAILED attempt, and the techniques you ALREADY know, "
            "synthesize ONE genuinely NOVEL offensive technique that is NOT in the known "
            "list — a concrete attack method (auth-bypass logic, parser-confusion chain, "
            "fuzzer mutation strategy, header-injection primitive, race-condition probe, "
            "etc.). Implement it as a small self-contained Python 3 probe that takes a "
            "target as argv[1] and prints one JSON finding per line to stdout when the "
            "technique works. "
            f"KNOWN TECHNIQUES (do NOT re-invent these):\n{known_str}\n"
            "Output EXACTLY:\n"
            "NAME: <lowercase snake_case identifier>\n"
            "FAMILY: <one of: auth-bypass|parser-confusion|fuzz-mutation|"
            "header-injection|race-condition|info-leak|logic-flaw|other>\n"
            "HYPOTHESIS: <one line: the novel idea and why it differs from known>\n"
            "TARGET_HINT: <what the probe should be aimed at, e.g. an endpoint or host>\n"
            "PROBE_SOURCE:\n<full python source, runnable as `python <name>.py <target>`>\n"
            "If no genuinely novel technique is warranted, output exactly: DECLINE"
        )
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
    def _parse_synthesis(text: str, known: list[str]) -> Optional[dict[str, str]]:
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
    ) -> Optional[InventedTechnique]:
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
                probe, provider, workspace_id, timeout=timeout,
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
                res = await provider.execute(
                    workspace_id, f"python {path} {run_target}", timeout=timeout,
                )
                technique.run_exit_code = getattr(res, "exit_code", None)
                technique.reproduction_output = getattr(res, "stdout", "") or ""
                technique.confirmed = (
                    technique.run_exit_code == 0
                    and technique.reproduction_output.strip() != ""
                )
            except Exception as e:
                logger.warning("method_lab_confirm_failed", name=technique.name, error=str(e))

        if technique.confirmed:
            # Parse the reproduction output into structured findings.
            technique.findings = self._parse_findings(technique.reproduction_output)
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
