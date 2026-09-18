"""
SONIC v2 — Dynamic Strategy Adaptation Engine
=============================================
Empowers the agent to autonomously evolve its offensive strategies based on
real feedback from targets (e.g. 403 Forbidden, WAF block, filtered port,
rate limiting, connection reset).

USER DIRECTION:
"isko scripted puppet nahi banana hai, force mat karo koi bhi tool ke liye
yeh khud things develop karega."

Core Principles:
1. Target-First Adaptation: Feedback from the target (status code, headers,
   body, firewall signatures, filter state) determines the next strategic posture.
2. No Scripted Puppet / No Forced Tools: If a tool is blocked or fails, the
   system does not force a canned tool sequence; instead, it adapts strategic
   posture and triggers autonomous probe/method synthesis via MethodLab and
   ToolsmithLoop.
3. Closed-Loop Learning: Distills failures into AVOID directives in
   LessonsLedger so identical failed attempts are not repeated.
4. Autonomous Novel Development: Encourages novel target-tailored probes
   rather than static templates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


class TargetFeedbackSignal(StrEnum):
    """Semantic signal derived from real target response data."""
    HTTP_403_FORBIDDEN = "HTTP_403_FORBIDDEN"
    HTTP_401_UNAUTHORIZED = "HTTP_401_UNAUTHORIZED"
    HTTP_429_RATE_LIMITED = "HTTP_429_RATE_LIMITED"
    WAF_BLOCK = "WAF_BLOCK"
    PORT_FILTERED = "PORT_FILTERED"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    PAYLOAD_SYNTAX_REJECTED = "PAYLOAD_SYNTAX_REJECTED"
    TARGET_SERVER_ERROR = "TARGET_SERVER_ERROR"
    TIMEOUT_UNRESPONSIVE = "TIMEOUT_UNRESPONSIVE"
    NOVEL_SURFACE_DETECTED = "NOVEL_SURFACE_DETECTED"
    BINARY_CRASH_OR_SEGFAULT = "BINARY_CRASH_OR_SEGFAULT"
    FLAG_DISCOVERED = "FLAG_DISCOVERED"
    CRYPTO_ORACLE_FAILURE = "CRYPTO_ORACLE_FAILURE"
    BINARY_OBFUSCATION = "BINARY_OBFUSCATION"
    FORENSIC_CORRUPT_HEADER = "FORENSIC_CORRUPT_HEADER"
    UNKNOWN_FEEDBACK = "UNKNOWN_FEEDBACK"


class StrategicPosture(StrEnum):
    """Adapted offensive posture reacting to target feedback."""
    DIRECT_EXPLORATION = "DIRECT_EXPLORATION"
    HEADER_AND_VERB_MUTATION = "HEADER_AND_VERB_MUTATION"      # For 403 Forbidden / ACLs
    WAF_EVASION_MUTATION = "WAF_EVASION_MUTATION"              # For WAF blocks
    ALTERNATIVE_SURFACE_PIVOT = "ALTERNATIVE_SURFACE_PIVOT"    # For filtered / dead ports
    RATE_THROTTLING_AND_BACKOFF = "RATE_THROTTLING_AND_BACKOFF"# For 429 rate limit
    AUTONOMOUS_METHOD_INVENTION = "AUTONOMOUS_METHOD_INVENTION"# Trigger MethodLab
    CUSTOM_TOOL_AUTHORING = "CUSTOM_TOOL_AUTHORING"            # Trigger Toolsmith
    EXPLOIT_PAYLOAD_MUTATION = "EXPLOIT_PAYLOAD_MUTATION"      # For binary crashes/segfaults
    FLAG_EXTRACTION_AND_TRIAGE = "FLAG_EXTRACTION_AND_TRIAGE"  # For flag discovery
    CRYPTO_ORACLE_ANALYSIS = "CRYPTO_ORACLE_ANALYSIS"          # For crypto oracle failures
    REVERSE_ENGINEERING_DEOBFUSCATION = "REVERSE_ENGINEERING_DEOBFUSCATION"  # For stripped/packed binaries
    FORENSIC_HEADER_REPAIR = "FORENSIC_HEADER_REPAIR"          # For corrupted file headers


@dataclass
class StrategyAdaptationPlan:
    """Actionable strategy adaptation based on target feedback."""
    signal: TargetFeedbackSignal
    posture: StrategicPosture
    rationale: str
    action_mutation: str
    avoid_directive: str
    synthesize_novel_method: bool = False
    author_custom_tool: bool = False
    suggested_actions: list[str] = field(default_factory=list)


class DynamicStrategyEngine:
    """
    Evaluates real target feedback and evolves offensive strategies dynamically.
    Enforces non-puppet autonomy: develops custom probes and methods tailored
    to what the target reports.
    """

    # Signatures for WAFs and security intermediaries
    WAF_SIGNATURES = [
        "cloudflare",
        "cf-ray",
        "blocked by waf",
        "web application firewall",
        "mod_security",
        "modsecurity",
        "imperva",
        "incapsula",
        "akamai",
        "aws waf",
        "sucuri",
        "barracuda",
        "fortiweb",
        "f5 big-ip asm",
        "request blocked by security",
        "access denied by security",
        "security check",
    ]

    def analyze_feedback(
        self,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        status_code: int | None = None,
    ) -> TargetFeedbackSignal:
        """
        Derive semantic TargetFeedbackSignal from real target output and network signals.
        """
        combined = f"{stderr}\n{stdout}".strip()
        combined_lower = combined.lower()

        # 1. Check explicit or parsed HTTP status codes
        if status_code == 403 or "403 forbidden" in combined_lower or "status: 403" in combined_lower or "http/1.1 403" in combined_lower or "http/2 403" in combined_lower:
            # Distinguish WAF block returning 403 from pure application ACL 403
            if any(sig in combined_lower for sig in self.WAF_SIGNATURES):
                return TargetFeedbackSignal.WAF_BLOCK
            return TargetFeedbackSignal.HTTP_403_FORBIDDEN

        if status_code == 401 or "401 unauthorized" in combined_lower or "http/1.1 401" in combined_lower or "http/2 401" in combined_lower:
            return TargetFeedbackSignal.HTTP_401_UNAUTHORIZED

        if status_code == 429 or "429 too many requests" in combined_lower or "rate limit exceeded" in combined_lower or "too many requests" in combined_lower:
            return TargetFeedbackSignal.HTTP_429_RATE_LIMITED

        # 2. General WAF indicators (even without explicit 403 code)
        if any(sig in combined_lower for sig in self.WAF_SIGNATURES):
            return TargetFeedbackSignal.WAF_BLOCK

        # 3. Network Filter / Firewall port filtering
        if any(
            term in combined_lower
            for term in (
                "filtered",
                "all 1000 scanned ports",
                "ignored states (filtered)",
                "packet dropped",
                "host seems down",
            )
        ):
            return TargetFeedbackSignal.PORT_FILTERED

        # 4. Connection refused
        if "connection refused" in combined_lower or "failed to connect" in combined_lower:
            return TargetFeedbackSignal.CONNECTION_REFUSED

        # 5. Target server errors (500, 502, 503)
        if any(term in combined_lower for term in ("500 internal server error", "502 bad gateway", "503 service unavailable", "http/1.1 500", "http/1.1 502", "http/1.1 503")):
            return TargetFeedbackSignal.TARGET_SERVER_ERROR

        # 6. Timeouts
        if exit_code == 124 or "timed out" in combined_lower or "deadline exceeded" in combined_lower:
            return TargetFeedbackSignal.TIMEOUT_UNRESPONSIVE

        # 7. Payload rejection
        if any(term in combined_lower for term in ("invalid syntax", "syntax error", "bad request", "400 bad request", "unrecognized option")):
            return TargetFeedbackSignal.PAYLOAD_SYNTAX_REJECTED

        # 8. CTF Flag Detection (immediate capture signal)
        if re.search(r"\b(?:flag|ctf|picoctf|htb)\{[^\}]+\}", stdout + stderr, re.IGNORECASE):
            return TargetFeedbackSignal.FLAG_DISCOVERED

        # 9. Binary Exploitation & Pwn (segfault / memory crash)
        if any(term in combined_lower for term in ("segmentation fault", "core dumped", "sigsegv", "signal 11", "sigill", "illegal instruction")):
            return TargetFeedbackSignal.BINARY_CRASH_OR_SEGFAULT

        # 10. Cryptography Oracle Failures
        if any(term in combined_lower for term in ("padding error", "bad padding", "decryption failed", "mac check failed", "invalid key length", "rsa key error")):
            return TargetFeedbackSignal.CRYPTO_ORACLE_FAILURE

        # 11. Reverse Engineering & Binary Packing
        if any(term in combined_lower for term in ("stripped binary", "upx compressed", "ptrace: operation not permitted", "anti-debug")):
            return TargetFeedbackSignal.BINARY_OBFUSCATION

        # 12. Forensics & File Corruption
        if any(term in combined_lower for term in ("not a valid png", "corrupt header", "magic bytes mismatch", "unrecognized archive", "damaged zip")):
            return TargetFeedbackSignal.FORENSIC_CORRUPT_HEADER

        return TargetFeedbackSignal.UNKNOWN_FEEDBACK

    def adapt_strategy(
        self,
        signal: TargetFeedbackSignal,
        target: str = "",
        current_technique: str = "",
        goal: str = "",
    ) -> StrategyAdaptationPlan:
        """
        Determines the adapted offensive strategy posture and concrete recommendations.
        """
        tgt = target or "target"

        if signal == TargetFeedbackSignal.HTTP_403_FORBIDDEN:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.HEADER_AND_VERB_MUTATION,
                rationale=f"Target {tgt} returned 403 Forbidden. Path or authentication ACL is active.",
                action_mutation=(
                    "Do NOT repeat the identical request. Mutate request headers "
                    "(X-Forwarded-For, X-Original-URL, X-Rewrite-URL, Client-IP), "
                    "test HTTP verb tampering (GET/POST/PUT/HEAD), or test path normalization quirks (//, /./, %2e/)."
                ),
                avoid_directive=f"Avoid direct unmodified requests to {tgt} resulting in 403 Forbidden.",
                synthesize_novel_method=True,
                suggested_actions=[
                    f"curl -sI -H 'X-Original-URL: /' {tgt}",
                    f"curl -sI -H 'X-Forwarded-For: 127.0.0.1' {tgt}",
                    "Invent novel auth-bypass technique via MethodLab",
                ],
            )

        if signal == TargetFeedbackSignal.WAF_BLOCK:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.WAF_EVASION_MUTATION,
                rationale=f"Target {tgt} is shielded by a Web Application Firewall (WAF) or security filter.",
                action_mutation=(
                    "Standard known payloads are signature-blocked. Synthesize a NOVEL attack hypothesis "
                    "via MethodLab. Use payload chunking, parameter pollution, character encoding (URL double encode, Unicode), "
                    "or custom probe scripts tailored to target parser quirks."
                ),
                avoid_directive=f"Avoid standard static exploit signatures against {tgt} (blocked by WAF).",
                synthesize_novel_method=True,
                author_custom_tool=True,
                suggested_actions=[
                    "Synthesize novel parser-confusion or evasion technique via MethodLab",
                    "Author custom obfuscated probe via Toolsmith",
                ],
            )

        if signal == TargetFeedbackSignal.PORT_FILTERED:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.ALTERNATIVE_SURFACE_PIVOT,
                rationale=f"Port(s) on {tgt} are reported FILTERED. Firewall/packet filter drops direct SYN packets.",
                action_mutation=(
                    "Do NOT exhaust the step budget repeating scans on filtered ports. "
                    "Pivot to discovering active web services, HTTP/HTTPS APIs, subdomains via CT logs, "
                    "or test alternative TCP flags (FIN, NULL, ACK) or UDP probes."
                ),
                avoid_directive=f"Avoid repeated SYN port scanning against filtered ports on {tgt}.",
                synthesize_novel_method=False,
                suggested_actions=[
                    f"Inspect active web services or HTTP/HTTPS endpoints on {tgt}",
                    "Perform subdomain and virtual host discovery",
                ],
            )

        if signal == TargetFeedbackSignal.HTTP_429_RATE_LIMITED:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.RATE_THROTTLING_AND_BACKOFF,
                rationale=f"Target {tgt} applied rate limiting (429 / Throttled).",
                action_mutation="Apply delay backoff, request jitter, and header rotation.",
                avoid_directive=f"Avoid high-frequency consecutive probing against {tgt}.",
                synthesize_novel_method=False,
                suggested_actions=["Introduce backoff delay between requests", "Rotate client headers"],
            )

        if signal == TargetFeedbackSignal.HTTP_401_UNAUTHORIZED:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.HEADER_AND_VERB_MUTATION,
                rationale=f"Target {tgt} requires authentication (401 Unauthorized).",
                action_mutation="Inspect login flows, token issuance endpoints, or test default/guest permissions.",
                avoid_directive=f"Avoid unauthenticated access to protected endpoint {tgt}.",
                synthesize_novel_method=True,
                suggested_actions=["Inspect login/auth endpoint", "Check for guest/public credentials"],
            )

        if signal == TargetFeedbackSignal.FLAG_DISCOVERED:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.FLAG_EXTRACTION_AND_TRIAGE,
                rationale=f"CTF Flag signature discovered in target output from {tgt}.",
                action_mutation="Halt broad discovery. Extract and isolate the exact flag string, verify format, and submit immediately.",
                avoid_directive="Avoid redundant scanning or exploration after flag has been discovered.",
                synthesize_novel_method=False,
                author_custom_tool=False,
                suggested_actions=["Extract flag matching flag{...}", "Submit flag to verification engine"],
            )

        if signal == TargetFeedbackSignal.BINARY_CRASH_OR_SEGFAULT:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.EXPLOIT_PAYLOAD_MUTATION,
                rationale=f"Target binary {tgt} crashed with segmentation fault or memory violation. Potential memory corruption / pwnable condition.",
                action_mutation="Inspect crash state via gdb/dmesg, determine precise RIP/EIP offset using cyclic patterns, check binary protections (checksec), and author a reliable exploit probe.",
                avoid_directive=f"Avoid sending arbitrary payload lengths to {tgt} without inspecting crash registers.",
                synthesize_novel_method=True,
                author_custom_tool=True,
                suggested_actions=["Run checksec on binary", "Inspect core dump / crash registers with gdb", "Synthesize precise ROP/buffer payload via MethodLab"],
            )

        if signal == TargetFeedbackSignal.CRYPTO_ORACLE_FAILURE:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.CRYPTO_ORACLE_ANALYSIS,
                rationale=f"Target {tgt} emitted cryptographic error (padding/MAC failure). Potential side-channel or padding oracle.",
                action_mutation="Measure timing and error differentiation across bit-flipped ciphertexts. Author a targeted oracle solver.",
                avoid_directive=f"Avoid sending random ciphertexts to {tgt} without differential analysis.",
                synthesize_novel_method=True,
                author_custom_tool=True,
                suggested_actions=["Analyze padding oracle response differences", "Author custom decryption solver in Toolsmith"],
            )

        if signal == TargetFeedbackSignal.BINARY_OBFUSCATION:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.REVERSE_ENGINEERING_DEOBFUSCATION,
                rationale=f"Target binary {tgt} is stripped, packed, or anti-debugging protected.",
                action_mutation="Unpack executable (upx -d), run dynamic tracing (ltrace / strace), or load into Ghidra/radare2 for decompilation.",
                avoid_directive=f"Avoid basic static strings analysis on packed binary {tgt}.",
                synthesize_novel_method=False,
                author_custom_tool=True,
                suggested_actions=["Unpack binary", "Trace system calls with strace", "Decompile entrypoint in Ghidra"],
            )

        if signal == TargetFeedbackSignal.FORENSIC_CORRUPT_HEADER:
            return StrategyAdaptationPlan(
                signal=signal,
                posture=StrategicPosture.FORENSIC_HEADER_REPAIR,
                rationale=f"Target file {tgt} has corrupted magic bytes or unrecognized container structure.",
                action_mutation="Inspect raw byte hex offset with xxd/hexdump, repair damaged magic bytes (e.g. PNG, ZIP, ELF header), and carve nested files with binwalk.",
                avoid_directive=f"Avoid opening corrupted file {tgt} with standard viewers before byte repair.",
                synthesize_novel_method=False,
                author_custom_tool=True,
                suggested_actions=["Inspect file magic bytes with xxd", "Repair container header", "Carve embedded data with binwalk"],
            )

        # Default fallback for unclassified or syntax failures: empower autonomous creation
        return StrategyAdaptationPlan(
            signal=signal,
            posture=StrategicPosture.AUTONOMOUS_METHOD_INVENTION,
            rationale=f"Target feedback ({signal.value}) indicates standard approach failed.",
            action_mutation=(
                "Do NOT rely on a static library of known exploit templates. "
                "Synthesize a novel attack hypothesis tailored to the target via MethodLab or author a custom tool."
            ),
            avoid_directive=f"Avoid repeating failed technique '{current_technique}' on {tgt}.",
            synthesize_novel_method=True,
            author_custom_tool=True,
            suggested_actions=[
                "Synthesize novel hypothesis via MethodLab tailored to observation",
                "Author custom targeted script via Toolsmith",
            ],
        )

    def evolve_on_failure(
        self,
        tool: str,
        raw_output: str,
        exit_code: int = 0,
        target: str = "",
        goal: str = "",
        lessons_ledger: Any | None = None,
    ) -> StrategyAdaptationPlan:
        """
        High-level hook called when an action against a target fails.
        Analyzes output, derives adapted strategy plan, and persists lessons.
        """
        signal = self.analyze_feedback(stdout=raw_output, exit_code=exit_code)
        plan = self.adapt_strategy(signal=signal, target=target, current_technique=tool, goal=goal)

        # Record into LessonsLedger if provided (closes the learn->apply loop)
        if lessons_ledger is not None:
            try:
                # Check if it's the Being lessons ledger or Memory lessons ledger
                if hasattr(lessons_ledger, "record"):
                    from sonic.being.lessons import Lesson as BeingLesson
                    from sonic.being.lessons import LessonKind
                    lesson = BeingLesson(
                        lesson_id=f"dyn-lsn-{abs(hash(tool + target + signal.value)) % 10**8}",
                        kind=LessonKind.AVOID,
                        goal=goal,
                        approach=f"{tool} on {target}",
                        evidence=f"Target signal {signal.value}: {plan.avoid_directive}",
                        tags=[tool.lower(), signal.value.lower(), "adapted_strategy"],
                    )
                    lessons_ledger.record([lesson])
                elif hasattr(lessons_ledger, "record_lesson"):
                    from sonic.memory.lessons import LessonType
                    lessons_ledger.record_lesson(
                        lesson_type=LessonType.FAILURE,
                        target_pattern=target or "target",
                        technique=tool,
                        summary=f"Failed with target signal {signal.value}",
                        guidance=plan.avoid_directive,
                    )
            except Exception as e:
                logger.warning("dynamic_strategy_failed_to_record_lesson", error=str(e))

        logger.info(
            "offensive_strategy_evolved",
            target=target,
            signal=signal.value,
            posture=plan.posture.value,
            synthesize_novel_method=plan.synthesize_novel_method,
        )
        return plan

