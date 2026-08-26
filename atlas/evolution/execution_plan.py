"""Atlas Controlled Self-Improvement — ExecutionPlan (Phase 13.5+)

Pure domain layer for the controlled execution loop between an approved
EvolutionProposal and its verified EvolutionResult:

    Approved proposal → ExecutionPlan → controlled action execution
    → validation → verified result → EvolutionRecord → insights

Design constraints honored:
- Declaration, not capability: ``build_execution_plan`` derives a bounded,
  auditable list of actions from the proposal. It never touches files,
  networks, or storage. Actual action performance requires an explicitly
  injected ``action_executor`` inside EvolutionExecutionEngine — without
  one, execution stays ADMINISTRATIVE exactly as before.
- Governance untouched: plans are built and executed only inside
  ``EvolutionExecutionEngine.execute()``, which is reachable solely through
  the approval flow (directly or via the ExecutionGateway). There is no
  bypass path.
- Deterministic and JSON-safe: every structure here serializes cleanly into
  EvolutionRecord metadata for knowledge/insight feedback.

Pure logic. No AI. No threading. No infrastructure imports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Hard bound on derived actions: an approved proposal can never expand into
# an unbounded execution surface, regardless of its target_components list.
MAX_PLAN_ACTIONS = 16

# The only action type derivable today. Future governed scopes may add more;
# unknown types must fail validation rather than execute blindly.
ADMINISTRATIVE_RECORD = "administrative_record"


@dataclass(frozen=True, slots=True)
class ExecutionAction:
    """One bounded, declarative step of an ExecutionPlan."""

    action_type: str
    target: str
    description: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionActionResult:
    """Outcome of attempting a single ExecutionAction."""

    action: ExecutionAction
    success: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """The bounded set of actions approved for one proposal execution."""

    plan_id: str
    proposal_id: str
    actions: tuple[ExecutionAction, ...]
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection for EvolutionRecord metadata."""
        return {
            "plan_id": self.plan_id,
            "proposal_id": self.proposal_id,
            "action_count": len(self.actions),
            "action_types": sorted({a.action_type for a in self.actions}),
            "targets": [a.target for a in self.actions],
        }


def build_execution_plan(proposal: Any) -> ExecutionPlan:
    """
    Derive a deterministic ExecutionPlan from an approved EvolutionProposal.

    One ``administrative_record`` action is emitted per distinct target
    component (bounded by MAX_PLAN_ACTIONS; excess targets are dropped and
    noted in plan metadata). Derivation is pure — building a plan performs
    no action itself.

    Args:
        proposal: An APPROVED EvolutionProposal.

    Returns:
        An ExecutionPlan linked to the proposal.
    """
    targets = list(getattr(getattr(proposal, "plan", None), "target_components", []) or [])
    dropped = max(0, len(targets) - MAX_PLAN_ACTIONS)
    bounded = targets[:MAX_PLAN_ACTIONS]

    seen: set[str] = set()
    actions: list[ExecutionAction] = []
    for target in bounded:
        name = str(target).strip() or "unspecified"
        if name in seen:
            continue
        seen.add(name)
        actions.append(
            ExecutionAction(
                action_type=ADMINISTRATIVE_RECORD,
                target=name,
                description=(
                    f"Administrative recording for target '{name}' of "
                    f"proposal '{proposal.proposal_id}'"
                ),
                payload={"proposal_id": proposal.proposal_id},
            )
        )

    metadata: dict[str, Any] = {
        "proposal_title": proposal.title,
        "derived_targets": len(targets),
    }
    if dropped:
        metadata["dropped_targets"] = dropped

    counter = getattr(build_execution_plan, "_counter", 0)
    counter += 1
    setattr(build_execution_plan, "_counter", counter)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    return ExecutionPlan(
        plan_id=f"PLAN-{timestamp}-{counter:04d}",
        proposal_id=proposal.proposal_id,
        actions=tuple(actions),
        metadata=metadata,
    )


def verify_execution_results(
    plan: ExecutionPlan,
    results: list[ExecutionActionResult],
    final_status: str,
) -> tuple[bool, str]:
    """
    Validate an execution attempt against its plan.

    Verification passes only when every planned action succeeded and the
    proposal reached IMPLEMENTED. Pure function — no side effects.

    Args:
        plan: The plan that was executed.
        results: One result per attempted action.
        final_status: Final proposal status name after the attempt.

    Returns:
        ``(verified, summary)`` where summary explains any failure.
    """
    failed = [r for r in results if not r.success]
    if failed:
        details = "; ".join(
            f"{r.action.target}: {r.detail or 'unspecified failure'}"
            for r in failed[:5]
        )
        return False, f"{len(failed)} of {len(results)} actions failed ({details})"

    expected = len(plan.actions)
    if len(results) != expected:
        return (
            False,
            f"expected {expected} action results, got {len(results)}",
        )

    if final_status != "IMPLEMENTED":
        return False, f"final status '{final_status}' is not IMPLEMENTED"

    return True, "all actions succeeded and proposal is IMPLEMENTED"
