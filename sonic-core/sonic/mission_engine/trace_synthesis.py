"""
SONIC-REDA — Mission Trace Synthesis (derive real artifacts from agent traces)
=============================================================================

Closes the PLAN.md audit item: the mission director hardcoded its milestones
(all force-SET to COMPLETED), deliverables ("JWT none algorithm bypass" +
fake commit hash), knowledge summary ("what_we_know" JWT strings), and
confidence (=1.00) — NONE of it derived from what the agent actually did.
That is scripted theater, not autonomy: the director reported success and
fabricated evidence regardless of the traces.

This module turns the agent's real ``ComputerDecisionTrace`` list into
honest, trace-derived mission artifacts:

    * ``synthesize_deliverables(mission_id, goal, traces)`` — one deliverable
      per concrete engineering action the agent ACTUALLY took and that
      succeeded/recovered: a FILE_WRITE that landed → ENGINEERING_PATCH; a
      GIT_COMMIT that landed → GIT_COMMIT; a SECURITY_TOOL run →
      EVIDENCE_PACKAGE. Content is the real observation text, not a hardcoded
      vuln name. No successful engineering action → no deliverables (honest).
    * ``synthesize_knowledge(goal, traces)`` — what_we_know = the agent's
      successful observations (what it actually did/saw); decisions = the
      actions it took; evidence = the raw observations; confidence = the
      success ratio (NOT 1.00 by decree).
    * ``milestone_status_from_traces(traces, plan)`` — a milestone is
      COMPLETED only if the traces contain at least one successful action whose
      type/target is relevant to that milestone's success conditions; otherwise
      it stays PENDING/ACTIVE. Progress is the fraction of completed milestones.

Honesty contract: if the agent did nothing (or everything failed), the director
reports an empty deliverable set, low confidence, and incomplete milestones —
never fabricated success.
"""

from __future__ import annotations

from sonic.computer_use.models import ComputerDecisionTrace
from sonic.mission_engine.models import (
    DeliverableType,
    MilestoneStatus,
    MissionDeliverable,
    MissionKnowledgeSummary,
    MissionMilestone,
    MissionPlan,
)

# Action-type -> deliverable type mapping (only for actions that PRODUCE an
# artifact when they succeed).
_ACTION_DELIVERABLE: dict[str, DeliverableType] = {
    "FILE_WRITE": DeliverableType.ENGINEERING_PATCH,
    "GIT_COMMIT": DeliverableType.GIT_COMMIT,
    "SECURITY_TOOL": DeliverableType.EVIDENCE_PACKAGE,
    "BROWSER_NAVIGATE": DeliverableType.EVIDENCE_PACKAGE,
}

_SUCCESS_STATES = {"SUCCESS", "COMPLETED", "RECOVERED", "VERIFIED"}


def _is_success(trace: ComputerDecisionTrace) -> bool:
    return str(getattr(trace.status, "value", trace.status)) in _SUCCESS_STATES or trace.status in _SUCCESS_STATES


def synthesize_deliverables(
    mission_id: str,
    goal: str,
    traces: list[ComputerDecisionTrace],
) -> list[MissionDeliverable]:
    """One deliverable per concrete successful engineering action.

    The deliverable content is the agent's actual observation, not a hardcoded
    vulnerability name. Returns an empty list if no artifact-producing action
    succeeded (honest: no fabricated deliverables).
    """
    deliverables: list[MissionDeliverable] = []
    seen: set[tuple[str, str]] = set()  # (action_type, target) dedupe

    for t in traces:
        if not _is_success(t):
            continue
        act_val = getattr(t.action_type, "value", str(t.action_type))
        dtype = _ACTION_DELIVERABLE.get(act_val)
        if dtype is None:
            continue
        key = (act_val, t.target_resource)
        if key in seen:
            continue
        seen.add(key)
        title = _deliverable_title(dtype, t)
        deliverables.append(MissionDeliverable(
            mission_id=mission_id,
            title=title,
            deliverable_type=dtype,
            content=t.actual_observation or f"{act_val} on {t.target_resource}",
            evidence_ids=[t.id],
        ))
    return deliverables


def _deliverable_title(dtype: DeliverableType, t: ComputerDecisionTrace) -> str:
    act_val = getattr(t.action_type, "value", str(t.action_type))
    if dtype == DeliverableType.ENGINEERING_PATCH:
        return f"Engineering patch: {t.target_resource}"
    if dtype == DeliverableType.GIT_COMMIT:
        return f"Git commit: {t.target_resource}"
    if dtype == DeliverableType.EVIDENCE_PACKAGE:
        return f"Evidence package: {t.target_resource} ({act_val})"
    return f"{dtype.value}: {t.target_resource}"


def synthesize_knowledge(
    goal: str,
    traces: list[ComputerDecisionTrace],
    remaining_unknowns: list[str] | None = None,
    active_tracks: list[str] | None = None,
) -> MissionKnowledgeSummary:
    """Derive the knowledge snapshot from the agent's real traces.

    what_we_know   = successful observations (what the agent actually did/saw)
    decisions      = the actions taken (action_type + target)
    evidence       = the raw observations (including failed/blocked — they are
                     evidence too: "we tried X and it was denied")
    confidence     = success ratio, NOT a decree of 1.00
    """
    total = len(traces)
    succ = [t for t in traces if _is_success(t)]
    failed = [t for t in traces if not _is_success(t)]

    what_we_know = [
        f"{getattr(t.action_type, 'value', str(t.action_type))} {t.target_resource}: {t.actual_observation[:160]}"
        for t in succ
    ] or ["No successful actions were recorded during the mission."]

    decisions = [
        f"{getattr(t.action_type, 'value', str(t.action_type))} on {t.target_resource} ({t.status})"
        for t in traces
    ] or ["No actions were taken during the mission."]

    evidence = [
        f"[{t.status}] {getattr(t.action_type, 'value', str(t.action_type))} {t.target_resource}: {t.actual_observation[:200]}"
        for t in traces
    ]

    confidence = round(len(succ) / total, 2) if total else 0.0
    next_best = (
        f"Mission executed {total} actions ({len(succ)} succeeded, {len(failed)} failed)."
        if traces else "No actions were taken."
    )

    return MissionKnowledgeSummary(
        goal=goal,
        what_we_know=what_we_know,
        what_we_do_not_know=list(remaining_unknowns or []),
        current_hypotheses=[],
        active_investigations=list(active_tracks or []),
        evidence=evidence,
        contradictions=[],
        decisions=decisions,
        next_best_action=next_best,
        remaining_risks=[],
        resource_state={},
        confidence=confidence,
    )


def milestone_status_from_traces(
    traces: list[ComputerDecisionTrace],
    plan: MissionPlan | None,
) -> tuple[list[MissionMilestone], float]:
    """Mark milestones COMPLETED only where traces prove relevant progress.

    Returns (updated_milestones, overall_progress_pct). A milestone with no
    matching successful trace stays PENDING — never force-completed.
    """
    if not plan or not plan.milestones:
        # No plan milestones — progress is whether ANY successful action ran.
        done = any(_is_success(t) for t in traces)
        return [], (100.0 if done and traces else 0.0)

    succ_types = {getattr(t.action_type, "value", str(t.action_type)) for t in traces if _is_success(t)}
    succ_text = " ".join(
        f"{getattr(t.action_type, 'value', str(t.action_type))} {t.target_resource} {t.actual_observation}"
        for t in traces if _is_success(t)
    ).lower()

    updated: list[MissionMilestone] = []
    completed = 0
    for ms in plan.milestones:
        # A milestone is done if any successful trace's type or its
        # success-condition keywords appear in the traces.
        conditions_text = " ".join(ms.success_conditions).lower()
        matched = bool(
            succ_types
            and _milestone_matches(ms, succ_types, succ_text, conditions_text)
        )
        if matched:
            ms.status = MilestoneStatus.COMPLETED
            ms.progress_pct = 100.0
            completed += 1
        else:
            ms.status = MilestoneStatus.PENDING
            ms.progress_pct = 0.0
        updated.append(ms)

    progress = round(completed / len(plan.milestones) * 100.0, 1)
    return updated, progress


def _milestone_matches(
    milestone: MissionMilestone,
    succ_types: set[str],
    succ_text: str,
    conditions_text: str,
) -> bool:
    """Heuristic: does any successful trace satisfy this milestone?

    We check both the action types and keyword overlap between the milestone's
    success conditions and the actual trace text. This is deliberately
    conservative — a milestone completes only when there is real evidence.
    """
    # Milestone 1 (inspection): any FILE_READ / TERMINAL_EXEC / SECURITY_TOOL.
    if any(k in conditions_text for k in ("inspect", "identif", "reproduc", "locat")):
        return bool(succ_types & {"FILE_READ", "TERMINAL_EXEC", "SECURITY_TOOL", "BROWSER_NAVIGATE"})
    # Milestone 2 (remediation): a FILE_WRITE / patch landed.
    if any(k in conditions_text for k in ("patch", "remediat", "fix", "test", "verif")):
        return "FILE_WRITE" in succ_types or "GIT_COMMIT" in succ_types
    # Milestone 3 (commit/deliverable): a GIT_COMMIT landed.
    if any(k in conditions_text for k in ("commit", "deliverable", "evidence", "custody")):
        return "GIT_COMMIT" in succ_types
    # Fallback: any successful action that mentions the milestone objective.
    return milestone.objective.lower()[:20] in succ_text
