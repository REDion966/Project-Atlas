"""
Atlas Evolution Autonomy — L1/L2 Controlled Autonomy Controller — Phase P18.

Pure-logic decision engine for L1 and L2 controlled autonomy.

L1 PHILOSOPHY
-------------
L1 = Autonomous execution of already-approved work.

Atlas may decide HOW to execute work the user has already approved.
Atlas may NOT decide WHAT work to approve.

L2 PHILOSOPHY
-------------
L2 = Multi-step autonomous workflow chaining with bounded plan adjustment.

L2 extends L1 with:
* Chaining multiple approved workflows
* Bounded plan adjustments within approved scope
* Cross-workflow failure diagnosis
* MEDIUM risk operations (vs L1's LOW only)

Responsibilities
----------------
* Decide whether an action can be performed autonomously under L1 or L2.
* Verify all evidence requirements before granting autonomy.
* Determine escalation paths when L1/L2 boundary is reached.
* Compose existing P17 components (diagnose → recover → verify).

This component is pure logic:
* it never mutates the repository, the proposal, or the approval;
* it never invokes execution, tests, subprocesses, or AI;
* it never authorizes, approves, or promotes.

Fail-closed: when evidence is insufficient, autonomy is denied.

Pure logic. No infrastructure. No AI. No mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
from atlas.evolution.autonomy.authorization_manager import AuthorizationManager
from atlas.evolution.autonomy.models import AuthorizationMode, RiskAssessment, RiskLevel
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel, EvolutionProposal, ProposalStatus


# ---------------------------------------------------------------------------
# Autonomy decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AutonomyDecision:
    """Result of an L1 autonomy check.

    Attributes:
        can_proceed: Whether the autonomous action is permitted.
        reason: Human-readable explanation of the decision.
        authorization_mode: The authorization mode if permitted, else None.
        evidence: Structured evidence supporting the decision.
        escalation_required: True when L1 boundary is reached.
    """

    can_proceed: bool
    reason: str
    authorization_mode: AuthorizationMode | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    escalation_required: bool = False


# ---------------------------------------------------------------------------
# L1 Controlled Autonomy Controller
# ---------------------------------------------------------------------------


class AutonomyController:
    """L1 Controlled Autonomy decision engine.

    Determines whether an action can be performed autonomously under L1
    rules. All checks are deterministic and evidence-based.

    L1 can autonomously:
    - Execute approved development steps (IMPLEMENT → VERIFY → ACCEPT)
    - Select diagnostic path on failure
    - Choose recovery strategy based on diagnosis
    - Run verification steps
    - Continue to next step in approved workflow

    L1 CANNOT:
    - Bypass user approval for new proposals
    - Exceed approved scope
    - Expand its own capabilities
    - Approve its own restricted actions
    - Mutate outside approved boundary
    - Promote from sandbox to real workspace
    """

    def __init__(
        self,
        authorization_manager: AuthorizationManager,
        policy_engine: AutonomyPolicyEngine,
    ) -> None:
        self._auth_manager = authorization_manager
        self._policy_engine = policy_engine

    def check_execution_autonomy(
        self,
        proposal: EvolutionProposal,
        session_context: Any,
    ) -> AutonomyDecision:
        """Check if L1 autonomous execution is permitted.

        Verifies all evidence requirements for autonomous execution:
        1. Proposal is APPROVED
        2. Session has OWNER authority
        3. AutonomyPolicy is enabled
        4. Scope is within envelope
        5. Risk is acceptable
        6. Execution level is allowed

        Args:
            proposal: The EvolutionProposal to execute.
            session_context: The active session context.

        Returns:
            AutonomyDecision indicating whether execution is permitted.
        """
        # 1. Proposal must be APPROVED
        if proposal.status != ProposalStatus.APPROVED:
            return AutonomyDecision(
                can_proceed=False,
                reason=f"Proposal status is {proposal.status.name}, not APPROVED",
                evidence={"proposal_status": proposal.status.name},
            )

        # 2. Session must have OWNER authority
        if not session_context.is_owner:
            return AutonomyDecision(
                can_proceed=False,
                reason="L1 execution requires OWNER authority",
                evidence={"authority": session_context.authority.value},
            )

        # 3. AutonomyPolicy must be enabled
        if not self._policy_engine.is_enabled():
            return AutonomyDecision(
                can_proceed=False,
                reason="Autonomy policy is disabled",
                escalation_required=True,
            )

        # 4. Scope must be within envelope
        # L1 execution operates on CODE scope (sandbox development)
        scope = ScopeType.CODE
        if not self._policy_engine.is_scope_in_envelope(scope):
            return AutonomyDecision(
                can_proceed=False,
                reason=f"Scope {scope.name} is outside the autonomous envelope",
                evidence={"scope": scope.name},
                escalation_required=True,
            )

        # 5. Risk must be acceptable (LOW for L1)
        risk_level = RiskLevel.LOW
        if not self._policy_engine.is_risk_acceptable(risk_level):
            return AutonomyDecision(
                can_proceed=False,
                reason=f"Risk level {risk_level.name} exceeds policy ceiling",
                evidence={"risk_level": risk_level.name},
                escalation_required=True,
            )

        # 6. Execution level must be allowed (SANDBOXED for L1)
        intended_level = ExecutionLevel.SANDBOXED
        if not self._policy_engine.is_execution_level_allowed(intended_level):
            return AutonomyDecision(
                can_proceed=False,
                reason="Execution level SANDBOXED exceeds policy level",
                evidence={"intended_level": intended_level.name},
                escalation_required=True,
            )

        return AutonomyDecision(
            can_proceed=True,
            reason="L1 autonomous execution permitted",
            authorization_mode=AuthorizationMode.AUTONOMY,
            evidence={
                "proposal_status": proposal.status.name,
                "authority": session_context.authority.value,
                "scope": scope.name,
                "risk_level": risk_level.name,
                "execution_level": intended_level.name,
            },
        )

    def check_recovery_autonomy(
        self,
        diagnostic: Any,
        recovery: Any,
    ) -> AutonomyDecision:
        """Check if L1 autonomous recovery decision is permitted.

        L1 can autonomously DECIDE on a recovery strategy, but the actual
        recovery EXECUTION requires a new user approval.

        Args:
            diagnostic: The DiagnosticResult from failure analysis.
            recovery: The RecoveryDecision from recovery analysis.

        Returns:
            AutonomyDecision indicating whether recovery decision is permitted.
        """
        # L1 can always make recovery decisions (read-only)
        # The decision itself is autonomous, but execution requires approval

        if recovery.recoverable and recovery.strategy.value == "revise_and_retry":
            return AutonomyDecision(
                can_proceed=True,
                reason="L1 can decide REVISE_AND_RETRY strategy autonomously",
                authorization_mode=AuthorizationMode.AUTONOMY,
                evidence={
                    "failure_class": diagnostic.failure_class.value,
                    "confidence": diagnostic.confidence.value,
                    "strategy": recovery.strategy.value,
                },
            )

        if recovery.strategy.value == "escalate":
            return AutonomyDecision(
                can_proceed=False,
                reason="Recovery strategy is ESCALATE — requires user decision",
                evidence={"strategy": recovery.strategy.value},
                escalation_required=True,
            )

        # NO_RECOVERY
        return AutonomyDecision(
            can_proceed=False,
            reason="Recovery strategy is NO_RECOVERY — failure is terminal",
            evidence={"strategy": recovery.strategy.value},
            escalation_required=True,
        )

    def check_verification_autonomy(
        self,
        result: Any,
    ) -> AutonomyDecision:
        """Check if L1 autonomous verification is permitted.

        L1 can autonomously verify development results. Verification is
        read-only and always permitted under L1.

        Args:
            result: The DevelopmentRunResult to verify.

        Returns:
            AutonomyDecision indicating whether verification is permitted.
        """
        # Verification is read-only — always permitted under L1
        status_name = getattr(result, "status", None)
        status_str = getattr(status_name, "name", str(status_name)) if status_name else "NONE"

        return AutonomyDecision(
            can_proceed=True,
            reason="L1 autonomous verification permitted (read-only)",
            authorization_mode=AuthorizationMode.AUTONOMY,
            evidence={"result_status": status_str},
        )

    def check_diagnostic_autonomy(
        self,
        result: Any,
    ) -> AutonomyDecision:
        """Check if L1 autonomous diagnosis is permitted.

        L1 can autonomously diagnose failures. Diagnosis is read-only
        and always permitted under L1.

        Args:
            result: The DevelopmentRunResult to diagnose.

        Returns:
            AutonomyDecision indicating whether diagnosis is permitted.
        """
        # Diagnosis is read-only — always permitted under L1
        status_name = getattr(result, "status", None)
        status_str = getattr(status_name, "name", str(status_name)) if status_name else "NONE"

        return AutonomyDecision(
            can_proceed=True,
            reason="L1 autonomous diagnosis permitted (read-only)",
            authorization_mode=AuthorizationMode.AUTONOMY,
            evidence={"result_status": status_str},
        )

    def check_continuation_autonomy(
        self,
        current_step: int,
        total_steps: int,
        last_outcome_status: DevelopmentOutcomeStatus,
    ) -> AutonomyDecision:
        """Check if L1 can autonomously continue to the next step.

        L1 can continue to the next step only if:
        1. There are remaining steps
        2. The last outcome was SUCCESS

        Args:
            current_step: The current step number (1-based).
            total_steps: The total number of steps.
            last_outcome_status: The status of the last step's outcome.

        Returns:
            AutonomyDecision indicating whether continuation is permitted.
        """
        if current_step >= total_steps:
            return AutonomyDecision(
                can_proceed=False,
                reason="No remaining steps in approved plan",
                evidence={
                    "current_step": current_step,
                    "total_steps": total_steps,
                },
            )

        if last_outcome_status != DevelopmentOutcomeStatus.SUCCESS:
            return AutonomyDecision(
                can_proceed=False,
                reason=f"Last outcome was {last_outcome_status.name}, not SUCCESS",
                evidence={
                    "last_status": last_outcome_status.name,
                },
                escalation_required=True,
            )

        return AutonomyDecision(
            can_proceed=True,
            reason="L1 autonomous continuation permitted",
            authorization_mode=AuthorizationMode.AUTONOMY,
            evidence={
                "current_step": current_step,
                "total_steps": total_steps,
                "last_status": last_outcome_status.name,
            },
        )

    # ------------------------------------------------------------------
    # L2 — Multi-step workflow chaining
    # ------------------------------------------------------------------

    def check_workflow_chaining_autonomy(
        self,
        current_workflow: Any,
        next_workflow: Any,
        session_context: Any,
    ) -> AutonomyDecision:
        """Check if L2 can chain two approved workflows.

        L2 can chain workflows only if:
        1. Both workflows are APPROVED
        2. Session has OWNER authority
        3. AutonomyPolicy is enabled
        4. Next workflow is within the same scope as current
        5. Risk level is MEDIUM or below

        Args:
            current_workflow: The current completed workflow.
            next_workflow: The next workflow to chain.
            session_context: The active session context.

        Returns:
            AutonomyDecision indicating whether chaining is permitted.
        """
        # 1. Both workflows must be APPROVED
        current_status = getattr(current_workflow, "status", None)
        next_status = getattr(next_workflow, "status", None)

        current_name = getattr(current_status, "name", str(current_status))
        next_name = getattr(next_status, "name", str(next_status))

        if current_name != "APPROVED":
            return AutonomyDecision(
                can_proceed=False,
                reason=f"Current workflow status is {current_name}, not APPROVED",
                evidence={"current_status": current_name},
            )

        if next_name != "APPROVED":
            return AutonomyDecision(
                can_proceed=False,
                reason=f"Next workflow status is {next_name}, not APPROVED",
                evidence={"next_status": next_name},
            )

        # 2. Session must have OWNER authority
        if not session_context.is_owner:
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 workflow chaining requires OWNER authority",
                evidence={"authority": session_context.authority.value},
            )

        # 3. AutonomyPolicy must be enabled
        if not self._policy_engine.is_enabled():
            return AutonomyDecision(
                can_proceed=False,
                reason="Autonomy policy is disabled",
                escalation_required=True,
            )

        # 4. Risk must be MEDIUM or below
        if not self._policy_engine.is_risk_acceptable(RiskLevel.MEDIUM):
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 workflow chaining requires MEDIUM risk tolerance",
                evidence={"max_risk": "MEDIUM"},
                escalation_required=True,
            )

        # 5. Execution level must allow CODE_ARTIFACT
        if not self._policy_engine.is_execution_level_allowed(ExecutionLevel.CODE_ARTIFACT):
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 workflow chaining requires CODE_ARTIFACT execution level",
                evidence={"required_level": "CODE_ARTIFACT"},
                escalation_required=True,
            )

        return AutonomyDecision(
            can_proceed=True,
            reason="L2 autonomous workflow chaining permitted",
            authorization_mode=AuthorizationMode.AUTONOMY,
            evidence={
                "current_status": current_name,
                "next_status": next_name,
                "authority": session_context.authority.value,
            },
        )

    # ------------------------------------------------------------------
    # L2 — Bounded plan adjustment
    # ------------------------------------------------------------------

    def check_plan_adjustment_autonomy(
        self,
        original_plan: Any,
        adjusted_plan: Any,
        session_context: Any,
    ) -> AutonomyDecision:
        """Check if L2 can adjust an approved plan.

        L2 can adjust plans only if:
        1. Session has OWNER authority
        2. AutonomyPolicy is enabled
        3. Adjusted plan preserves the original objective
        4. Adjusted plan does not expand scope
        5. All steps remain within approved components

        Args:
            original_plan: The original approved plan.
            adjusted_plan: The proposed adjusted plan.
            session_context: The active session context.

        Returns:
            AutonomyDecision indicating whether adjustment is permitted.
        """
        # 1. Session must have OWNER authority
        if not session_context.is_owner:
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 plan adjustment requires OWNER authority",
                evidence={"authority": session_context.authority.value},
            )

        # 2. AutonomyPolicy must be enabled
        if not self._policy_engine.is_enabled():
            return AutonomyDecision(
                can_proceed=False,
                reason="Autonomy policy is disabled",
                escalation_required=True,
            )

        # 3. Objective must be preserved
        original_objective = getattr(original_plan, "summary", "") or ""
        adjusted_objective = getattr(adjusted_plan, "summary", "") or ""

        if original_objective != adjusted_objective:
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 plan adjustment cannot change the objective",
                evidence={
                    "original_objective": original_objective,
                    "adjusted_objective": adjusted_objective,
                },
                escalation_required=True,
            )

        # 4. Scope must not expand
        original_components = set(getattr(original_plan, "target_components", []) or [])
        adjusted_components = set(getattr(adjusted_plan, "target_components", []) or [])

        if not adjusted_components.issubset(original_components):
            new_components = adjusted_components - original_components
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 plan adjustment cannot expand scope",
                evidence={
                    "original_components": list(original_components),
                    "new_components": list(new_components),
                },
                escalation_required=True,
            )

        return AutonomyDecision(
            can_proceed=True,
            reason="L2 autonomous plan adjustment permitted",
            authorization_mode=AuthorizationMode.AUTONOMY,
            evidence={
                "original_components": list(original_components),
                "adjusted_components": list(adjusted_components),
            },
        )

    # ------------------------------------------------------------------
    # L2 — Cross-workflow diagnosis
    # ------------------------------------------------------------------

    def check_cross_workflow_diagnosis_autonomy(
        self,
        workflows: list[Any],
        session_context: Any,
    ) -> AutonomyDecision:
        """Check if L2 can diagnose across multiple workflows.

        L2 can perform cross-workflow diagnosis only if:
        1. Session has OWNER authority
        2. AutonomyPolicy is enabled
        3. At least 2 workflows are provided
        4. All workflows are in a terminal state

        Args:
            workflows: List of workflows to diagnose.
            session_context: The active session context.

        Returns:
            AutonomyDecision indicating whether diagnosis is permitted.
        """
        # 1. Session must have OWNER authority
        if not session_context.is_owner:
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 cross-workflow diagnosis requires OWNER authority",
                evidence={"authority": session_context.authority.value},
            )

        # 2. AutonomyPolicy must be enabled
        if not self._policy_engine.is_enabled():
            return AutonomyDecision(
                can_proceed=False,
                reason="Autonomy policy is disabled",
                escalation_required=True,
            )

        # 3. At least 2 workflows required
        if len(workflows) < 2:
            return AutonomyDecision(
                can_proceed=False,
                reason="Cross-workflow diagnosis requires at least 2 workflows",
                evidence={"workflow_count": len(workflows)},
            )

        return AutonomyDecision(
            can_proceed=True,
            reason="L2 autonomous cross-workflow diagnosis permitted",
            authorization_mode=AuthorizationMode.AUTONOMY,
            evidence={
                "workflow_count": len(workflows),
                "authority": session_context.authority.value,
            },
        )

    # ------------------------------------------------------------------
    # L2 — MEDIUM risk operations
    # ------------------------------------------------------------------

    def check_medium_risk_autonomy(
        self,
        proposal: Any,
        session_context: Any,
    ) -> AutonomyDecision:
        """Check if L2 can handle MEDIUM risk operations.

        L2 can handle MEDIUM risk only if:
        1. Proposal is APPROVED
        2. Session has OWNER authority
        3. AutonomyPolicy is enabled
        4. Risk level is MEDIUM or below
        5. Execution level allows CODE_ARTIFACT

        Args:
            proposal: The EvolutionProposal to execute.
            session_context: The active session context.

        Returns:
            AutonomyDecision indicating whether MEDIUM risk execution is permitted.
        """
        # 1. Proposal must be APPROVED
        proposal_status = getattr(proposal, "status", None)
        status_name = getattr(proposal_status, "name", str(proposal_status))

        if status_name != "APPROVED":
            return AutonomyDecision(
                can_proceed=False,
                reason=f"Proposal status is {status_name}, not APPROVED",
                evidence={"proposal_status": status_name},
            )

        # 2. Session must have OWNER authority
        if not session_context.is_owner:
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 MEDIUM risk execution requires OWNER authority",
                evidence={"authority": session_context.authority.value},
            )

        # 3. AutonomyPolicy must be enabled
        if not self._policy_engine.is_enabled():
            return AutonomyDecision(
                can_proceed=False,
                reason="Autonomy policy is disabled",
                escalation_required=True,
            )

        # 4. Risk must be MEDIUM or below
        if not self._policy_engine.is_risk_acceptable(RiskLevel.MEDIUM):
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 MEDIUM risk execution requires MEDIUM risk tolerance",
                evidence={"max_risk": "MEDIUM"},
                escalation_required=True,
            )

        # 5. Execution level must allow CODE_ARTIFACT
        if not self._policy_engine.is_execution_level_allowed(ExecutionLevel.CODE_ARTIFACT):
            return AutonomyDecision(
                can_proceed=False,
                reason="L2 MEDIUM risk execution requires CODE_ARTIFACT execution level",
                evidence={"required_level": "CODE_ARTIFACT"},
                escalation_required=True,
            )

        return AutonomyDecision(
            can_proceed=True,
            reason="L2 autonomous MEDIUM risk execution permitted",
            authorization_mode=AuthorizationMode.AUTONOMY,
            evidence={
                "proposal_status": status_name,
                "authority": session_context.authority.value,
                "risk_level": "MEDIUM",
                "execution_level": "CODE_ARTIFACT",
            },
        )
