"""
Atlas CLI — Evolution Proposal Management (Phase 11.1).

CLI is presentation only.
Delegates all business logic to EvolutionExecutionEngine.
Never calls ApprovalManager, EvolutionMemory, or OutcomeTracker directly.
"""

from datetime import datetime
from typing import Any

from atlas.evolution.models import ProposalStatus


def _format_proposal(proposal: Any) -> str:
    """Format a single proposal for display."""
    return (
        f"  [{proposal.proposal_id}] {proposal.title}\n"
        f"       Status: {proposal.status.name}\n"
        f"       Priority: {proposal.plan.priority.name}\n"
        f"       Created: {proposal.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"       Summary: {proposal.summary[:120]}"
    )


def cmd_proposals_list(engine: Any, args: Any) -> str:
    """
    List all evolution proposals.

    CLI: atlas proposals list
         atlas proposals list --pending

    Delegates to: EvolutionExecutionEngine.list_proposals()
    """
    pending_only = getattr(args, "pending", False)
    proposals = engine.list_proposals(pending_only=pending_only)

    if not proposals:
        if pending_only:
            return "No pending proposals found."
        return "No proposals found."

    lines = [f"Found {len(proposals)} proposal(s):\n"]
    for p in proposals:
        lines.append(_format_proposal(p))
        lines.append("")

    return "\n".join(lines).strip()


def cmd_proposals_show(engine: Any, args: Any) -> str:
    """
    Show full details of a single evolution proposal.

    CLI: atlas proposals show <proposal_id>

    Delegates to: EvolutionExecutionEngine.get_proposal()
    """
    proposal_id = getattr(args, "proposal_id", "")
    if not proposal_id:
        return "Error: proposal_id is required."

    proposal = engine.get_proposal(proposal_id)
    if proposal is None:
        return f"Proposal '{proposal_id}' not found."

    lines = [
        f"Proposal: {proposal.proposal_id}",
        f"Title: {proposal.title}",
        f"Status: {proposal.status.name}",
        f"Created: {proposal.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"Summary:",
        f"  {proposal.summary}",
        f"",
        f"Rationale:",
        f"  {proposal.rationale}",
        f"",
        f"Expected Benefit:",
        f"  {proposal.expected_benefit}",
        f"",
        f"Risks:",
        f"  {proposal.risks}",
        f"",
        f"Impact Analysis:",
        f"  {proposal.impact_analysis}",
        f"",
        f"Implementation Approach:",
        f"  {proposal.implementation_approach}",
    ]

    if proposal.approved_at:
        lines.append(f"Approved: {proposal.approved_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if proposal.rejection_reason:
        lines.append(f"Rejection Reason: {proposal.rejection_reason}")

    return "\n".join(lines)


def cmd_proposals_approve(engine: Any, args: Any) -> str:
    """
    Approve and execute a proposal.

    CLI: atlas proposals approve <proposal_id> --message "optional..."

    Delegates to: EvolutionExecutionEngine.approve_proposal_by_id()
    """
    proposal_id = getattr(args, "proposal_id", "")
    if not proposal_id:
        return "Error: proposal_id is required."

    message = getattr(args, "message", "")

    result = engine.approve_proposal_by_id(
        proposal_id=proposal_id,
        comment=message,
    )

    if result.success:
        output = f"✓ Proposal '{proposal_id}' approved and executed."
        if result.record_id:
            output += f"\n  Execution record: {result.record_id}"
        if result.tracked_goal_id:
            output += f"\n  Tracked goal: {result.tracked_goal_id}"
        return output

    return f"✗ Failed to approve proposal '{proposal_id}': {result.error}"


def cmd_proposals_reject(engine: Any, args: Any) -> str:
    """
    Reject a proposal.

    CLI: atlas proposals reject <proposal_id> --reason "optional..."

    Delegates to: EvolutionExecutionEngine.reject_proposal_by_id()
    """
    proposal_id = getattr(args, "proposal_id", "")
    if not proposal_id:
        return "Error: proposal_id is required."

    reason = getattr(args, "reason", "")
    if not reason:
        return "Error: rejection reason is required."

    result = engine.reject_proposal_by_id(
        proposal_id=proposal_id,
        reason=reason,
    )

    if result.success:
        return f"✓ Proposal '{proposal_id}' rejected."
    return f"✗ Failed to reject proposal '{proposal_id}': {result.error}"


def cmd_proposals_defer(engine: Any, args: Any) -> str:
    """
    Defer a proposal for later consideration.

    CLI: atlas proposals defer <proposal_id> --reason "optional..."

    Delegates to: EvolutionExecutionEngine.defer_proposal_by_id()
    """
    proposal_id = getattr(args, "proposal_id", "")
    if not proposal_id:
        return "Error: proposal_id is required."

    reason = getattr(args, "reason", "")

    result = engine.defer_proposal_by_id(
        proposal_id=proposal_id,
        reason=reason,
    )

    if result.success:
        return f"✓ Proposal '{proposal_id}' deferred."
    return f"✗ Failed to defer proposal '{proposal_id}': {result.error}"


def cmd_proposals_audit(engine: Any, args: Any) -> str:
    """
    Show the read-only evolution audit trail for a proposal.

    CLI: atlas proposals audit <proposal_id>

    Post-Core F8 — Inspection only: surfaces the proposal's lifecycle
    (status/priority/timestamps), the current approval decision, and the
    execution outcome already represented by the F7 EvolutionRecord.
    Read-only — never approves, executes, or touches governance.

    Delegates to: EvolutionExecutionEngine.get_proposal_audit()
    """
    proposal_id = getattr(args, "proposal_id", "")
    if not proposal_id:
        return "Error: proposal_id is required."

    audit = engine.get_proposal_audit(proposal_id)
    if audit is None:
        return f"Proposal '{proposal_id}' not found."

    lines = [
        f"Proposal: {audit['proposal_id']}",
        f"Title: {audit['title']}",
        f"Status: {audit['status']}",
        f"Priority: {audit['priority']}",
        f"Created: {audit['created_at']}",
    ]
    if audit["approved_at"]:
        lines.append(f"Approved: {audit['approved_at']}")
    if audit["rejection_reason"]:
        lines.append(f"Rejection Reason: {audit['rejection_reason']}")

    approval = audit["approval"]
    if approval is not None:
        lines.append(
            f"Approval Decision: {approval['decision']}"
            + (f" ({approval['comment']})" if approval["comment"] else "")
        )
        if approval["decided_at"]:
            lines.append(f"Decided At: {approval['decided_at']}")
    else:
        lines.append("Approval Decision: (none)")

    execution = audit["execution"]
    if execution is not None:
        outcome = "Success" if execution["success"] else "Failure"
        lines.append(f"Execution: {outcome}")
        lines.append(f"Execution Record: {execution['record_id']}")
        if execution["status"]:
            lines.append(f"Execution Status: {execution['status']}")
        if execution["error"]:
            lines.append(f"Execution Error: {execution['error']}")
        if execution["tracked_goal_id"]:
            lines.append(f"Tracked Goal: {execution['tracked_goal_id']}")
    else:
        lines.append("Execution: (not yet executed)")

    return "\n".join(lines)
