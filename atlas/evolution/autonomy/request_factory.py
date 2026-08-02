"""
Atlas Evolution Autonomy — Request Factory — Phase 16.1

Deterministic constructors that build ``EvolutionRequest`` draft artifacts
from the four approved sources:

  1. Approved Phase 15 ``EvolutionProposal`` targeting a state scope.
  2. Phase 15 ``ImprovementGoal`` + ``GoalAuthorization`` (D12 transcription).
  3. Evolution ``ImprovementOpportunity`` from the scheduler.
  4. CLI invocation (presentation-only; payload is provided directly).

The factory is pure logic: it creates DRAFTED requests with deterministic
IDs, scope-aligned execution levels, and version anchors. It performs no
validation, no authorization, no scheduling, no storage, and no gateway
calls. Those belong to later sub-phases.

Pure logic. No infrastructure. No AI. No gateway access.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any

from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    EvolutionRequestStatus,
    TargetKind,
    VersionTarget,
)
from atlas.evolution.autonomy.scope_classifier import STATE_SCOPES
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import (
    EvolutionProposal,
    ExecutionLevel,
)
from atlas.goals.execution_models import GoalAuthorization
from atlas.goals.models import (
    ImprovementGoal,
    ImprovementOpportunity,
)


class EvolutionRequestFactory:
    """Creates ``EvolutionRequest`` drafts from approved sources.

    A single, stateless factory. All public methods return a DRAFTED
    ``EvolutionRequest`` with deterministic ID generation and a version
    anchor. Methods refuse protected scopes (IDENTITY, CODE) with
    ``ValueError`` where the caller explicitly selects the target scope.

    The factory accepts an optional ``goal_repository`` for goal-by-ID
    transcription. The repository is expected to expose ``get_goal(goal_id)``.
    """

    def __init__(self, goal_repository: Any | None = None):
        self._goal_repository = goal_repository

    # ------------------------------------------------------------------
    # Public constructors
    # ------------------------------------------------------------------

    def from_proposal(self, proposal: EvolutionProposal) -> EvolutionRequest:
        """Draft an EvolutionRequest from an approved proposal.

        The proposal's scope is classified from its plan.target_components
        using the closed scope map. Unknown-scope proposals still produce a
        DRAFTED request so the audit trail is preserved; refusal occurs at
        the translation/gateway layers in later sub-phases.
        """
        scope = self._classify_proposal_scope(proposal)
        source = proposal.proposal_id
        payload = self._proposal_payload(proposal)

        return EvolutionRequest(
            request_id=self._new_request_id(),
            source=source,
            target_scope=scope,
            change_payload=payload,
            intended_level=_level_for_scope(scope),
            status=EvolutionRequestStatus.DRAFTED,
            version_target=self._version_anchor(scope),
            metadata={
                "source_type": "proposal",
                "proposal_id": proposal.proposal_id,
            },
        )

    def from_goal(
        self,
        goal: ImprovementGoal,
        authorization: GoalAuthorization,
        target_scope: ScopeType,
    ) -> EvolutionRequest:
        """Transcribe an authorized Phase 15 goal into an EvolutionRequest.

        Per Decision D12, the ``GoalAuthorization`` evidence snapshot is
        preserved in request metadata so the Phase 17 evidence chain is
        intact. Protected scopes are refused structurally.
        """
        self._require_state_scope(target_scope)

        payload = {
            "title": goal.title,
            "description": goal.description,
            "category": goal.category.name,
            "goal_id": goal.goal_id,
        }

        return EvolutionRequest(
            request_id=self._new_request_id(),
            source=goal.goal_id,
            target_scope=target_scope,
            change_payload=payload,
            intended_level=_level_for_scope(target_scope),
            status=EvolutionRequestStatus.DRAFTED,
            version_target=self._version_anchor(target_scope),
            metadata={
                "source_type": "goal",
                "authorized_by": authorization.authorized_by,
                "strategy_key": authorization.strategy_key,
                "strategy_name": authorization.strategy_name,
                "planning_context_version": authorization.planning_context_version,
            },
        )

    def from_goal_record(
        self,
        goal_id: str,
        authorization: GoalAuthorization,
        target_scope: ScopeType,
    ) -> EvolutionRequest | None:
        """Transcribe a goal by ID using the injected repository.

        Returns ``None`` when no repository is injected or the goal is
        missing, keeping the factory fail-closed and deterministic.
        """
        if self._goal_repository is None:
            return None

        goal = self._goal_repository.get_goal(goal_id)
        if goal is None:
            return None

        return self.from_goal(goal, authorization, target_scope)

    def from_scheduler(
        self,
        opportunity: ImprovementOpportunity,
        target_scope: ScopeType,
    ) -> EvolutionRequest:
        """Draft an EvolutionRequest from a scheduler opportunity.

        The caller must explicitly declare the state scope; protected
        scopes raise ``ValueError``.
        """
        self._require_state_scope(target_scope)

        payload = {
            "title": opportunity.title,
            "description": opportunity.description,
            "category": opportunity.category.name,
            "opportunity_id": opportunity.opportunity_id,
        }

        metadata = {
            "source_type": "scheduler",
            "opportunity_id": opportunity.opportunity_id,
        }
        if opportunity.priority_score is not None:
            metadata["priority_score"] = str(opportunity.priority_score)

        return EvolutionRequest(
            request_id=self._new_request_id(),
            source=opportunity.opportunity_id,
            target_scope=target_scope,
            change_payload=payload,
            intended_level=_level_for_scope(target_scope),
            status=EvolutionRequestStatus.DRAFTED,
            version_target=self._version_anchor(target_scope),
            metadata=metadata,
        )

    def from_cli(
        self,
        target_scope: ScopeType,
        change_payload: dict[str, Any],
        source: str = "cli",
    ) -> EvolutionRequest:
        """Draft an EvolutionRequest from a CLI invocation.

        The payload is shallow-copied to prevent external mutation after
        construction. Protected scopes raise ``ValueError``.
        """
        self._require_state_scope(target_scope)

        return EvolutionRequest(
            request_id=self._new_request_id(),
            source=source,
            target_scope=target_scope,
            change_payload=copy.copy(change_payload),
            intended_level=_level_for_scope(target_scope),
            status=EvolutionRequestStatus.DRAFTED,
            version_target=self._version_anchor(target_scope),
            metadata={"source_type": "cli"},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _new_request_id() -> str:
        """Deterministic request ID: AUTORQ- prefix plus a UUID4 token."""
        return f"AUTORQ-{uuid.uuid4().hex[:16].upper()}"

    @staticmethod
    def _version_anchor(scope: ScopeType) -> VersionTarget:
        """Build the optimistic-concurrency version anchor.

        In Phase 16.1 the factory uses the genesis state version string
        ``1.0.0`` as the optimistic-concurrency anchor. Later sub-phases
        will read the live ``AtlasStateVersion`` when one exists.
        """
        return VersionTarget(
            target_kind=_target_kind_for_scope(scope),
            current_version="1.0.0",
            target_version="",
            state_version_at_creation="1.0.0",
        )

    @staticmethod
    def _require_state_scope(scope: ScopeType) -> None:
        """Fail closed when the caller attempts a protected scope."""
        if scope not in STATE_SCOPES:
            raise ValueError(
                f"Scope {scope.name} is not a valid Phase 16 state scope"
            )

    @staticmethod
    def _classify_proposal_scope(proposal: EvolutionProposal) -> ScopeType:
        """Classify a proposal's scope from its target_components.

        Uses the closed scope map so payload-derived components cannot
        influence classification.
        """
        from atlas.evolution.autonomy.scope_classifier import classify_components

        components = list(proposal.plan.target_components)
        return classify_components(components)

    @staticmethod
    def _proposal_payload(proposal: EvolutionProposal) -> dict[str, Any]:
        """Extract a deterministic payload from a proposal."""
        return {
            "title": proposal.title,
            "summary": proposal.summary,
            "proposal_id": proposal.proposal_id,
            "expected_benefit": proposal.expected_benefit,
        }


# ---------------------------------------------------------------------------
# Deterministic scope mapping helpers
# ---------------------------------------------------------------------------


def _level_for_scope(scope: ScopeType) -> ExecutionLevel:
    """Map a state scope to the execution level required to apply it.

    Per the approved architecture:
      - CONFIG      -> SELF_CONFIG
      - MEMORY      -> INFORMATION
      - KNOWLEDGE   -> INFORMATION
      - CAPABILITY  -> SELF_CONFIG
      - UNKNOWN     -> ADMINISTRATIVE (audit-only, fails at gateway)
    """
    if scope == ScopeType.CONFIG:
        return ExecutionLevel.SELF_CONFIG
    if scope == ScopeType.CAPABILITY:
        return ExecutionLevel.SELF_CONFIG
    if scope in (ScopeType.MEMORY, ScopeType.KNOWLEDGE):
        return ExecutionLevel.INFORMATION
    return ExecutionLevel.ADMINISTRATIVE


def _target_kind_for_scope(scope: ScopeType) -> TargetKind:
    """Map a state scope to the corresponding VersionTarget kind."""
    mapping = {
        ScopeType.CONFIG: TargetKind.CONFIG,
        ScopeType.MEMORY: TargetKind.MEMORY,
        ScopeType.KNOWLEDGE: TargetKind.KNOWLEDGE,
        ScopeType.CAPABILITY: TargetKind.CAPABILITY,
    }
    return mapping.get(scope, TargetKind.CONFIG)
