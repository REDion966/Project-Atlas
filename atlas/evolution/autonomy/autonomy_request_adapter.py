"""
Atlas Evolution Autonomy — AutonomyRequestAdapter — Phase 16.1

The SOLE translator of ``EvolutionRequest`` into the scope-pinned
``EvolutionProposal`` form required by ``EvolutionExecutionGateway``.

Per Phase 16 Decision D2, ``target_components`` are derived EXCLUSIVELY
from ``EvolutionRequest.target_scope`` via the closed scope map in
``scope_classifier``. They are never derived from, or influenced by,
the change payload or any other user-controlled input. This makes
governance classification structurally impossible to smuggle.

The translated proposal is intentionally classified with the exact
scope-derived components, so the existing ``RuleEngine`` (Phase 13.1)
classifies it as the request's declared scope — never UNKNOWN for a
state-carrying request. An UNKNOWN-scope request produces UNKNOWN
components and is consequently refused at the gateway in later
sub-phases (UNKNOWN-close invariant).

The Phase 15 ``ExecutionRequestAdapter`` (goals → proposal) is
untouched. This is a separate, additive translator for Phase 16.

Deterministic: the same request always produces the same proposal.

Pure logic. No gateway access. No storage. No AI.
"""

from datetime import datetime

from atlas.evolution.autonomy.models import EvolutionRequest
from atlas.evolution.autonomy.scope_classifier import components_for_scope
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
    Weakness,
)

#: Prefix for proposals produced from EvolutionRequests, mirroring the
#: Phase 15 GOALX- prefix convention.
_REQUEST_PROPOSAL_PREFIX = "AUTOX-"


class AutonomyRequestAdapter:
    """
    Builds a scope-pinned ``EvolutionProposal`` from an ``EvolutionRequest``.

    Stateless and deterministic. The proposal's ``target_components``
    come exclusively from the closed scope map; the proposal status is
    ``APPROVED`` by construction (authorization is verified upstream in
    later sub-phases before this adapter is ever invoked at the gateway).
    """

    @staticmethod
    def to_proposal(request: EvolutionRequest) -> EvolutionProposal:
        """
        Translate an EvolutionRequest into a scope-pinned EvolutionProposal.

        The proposal:
          - proposal_id = "AUTOX-" + request.request_id
          - target_components derived ONLY from request.target_scope via
            the closed map (never from change_payload)
          - status = APPROVED (upstream authorization precondition)
          - scope metadata (scope name) carried into proposal.metadata

        Args:
            request: The EvolutionRequest to translate.

        Returns:
            An EvolutionProposal with APPROVED status and scope-pinned
            target_components.
        """
        scope = request.target_scope
        components = components_for_scope(scope)

        proposal_id = f"{_REQUEST_PROPOSAL_PREFIX}{request.request_id}"
        title = (
            request.change_payload.get("title", "")
            or f"Evolution request {request.request_id}: {scope.name}"
        )[:200]
        description = request.change_payload.get(
            "description",
            f"Governed evolution request {request.request_id} targeting {scope.name}.",
        )

        weakness = Weakness(
            area=_area_for_scope(scope),
            description=description,
            severity=ImprovementPriority.MEDIUM,
            supporting_observations=[request.request_id],
        )

        plan = ImprovementPlan(
            plan_id=f"plan-{proposal_id}",
            title=title,
            description=description,
            priority=ImprovementPriority.MEDIUM,
            weaknesses=[weakness],
            expected_benefit=_expected_benefit_for_scope(scope),
            complexity_estimate="low",
            target_components=components,
        )

        return EvolutionProposal(
            proposal_id=proposal_id,
            title=title,
            summary=(
                f"Evolution request: {title[:80]} "
                f"(scope {scope.name}, level {request.intended_level.name})"
            ),
            rationale=(
                f"Governed autonomous evolution. "
                f"Scope: {scope.name}. "
                f"Intended level: {request.intended_level.name}."
            ),
            expected_benefit=plan.expected_benefit,
            risks="Bounded by governance, rollback, and versioning safeguards.",
            impact_analysis=(f"Target scope: {scope.name}. Components "
                             f"derived from the closed scope map only."),
            implementation_approach=(
                f"AutonomyRequestAdapter with closed scope map; "
                f"applied by scope-specific appliers (later sub-phases)."
            ),
            plan=plan,
            status=ProposalStatus.APPROVED,
            approved_at=datetime.now(),
            metadata={
                "source_request_id": request.request_id,
                "source": request.source,
                "target_scope": scope.name,
                "intended_level": request.intended_level.name,
                "request_status": request.status.name,
            },
        )


def _area_for_scope(scope: ScopeType) -> str:
    """Canonical evolution area for a scope (domain mapping, deterministic)."""
    if scope == ScopeType.CONFIG:
        return "config"
    if scope == ScopeType.MEMORY:
        return "memory"
    if scope == ScopeType.KNOWLEDGE:
        return "knowledge"
    if scope == ScopeType.CAPABILITY:
        return "capability"
    return "governance:unknown"


def _expected_benefit_for_scope(scope: ScopeType) -> str:
    """Expected-benefit text for a scope (domain mapping, deterministic)."""
    if scope == ScopeType.CONFIG:
        return "Configuration change applied through governed evolution"
    if scope == ScopeType.MEMORY:
        return "Memory state change applied through governed evolution"
    if scope == ScopeType.KNOWLEDGE:
        return "Knowledge base change applied through governed evolution"
    if scope == ScopeType.CAPABILITY:
        return "Capability registry change applied through governed evolution"
    return "Governed evolution change on unclassified scope"
