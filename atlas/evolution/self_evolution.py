"""Atlas Evolution — Phase 11: the bounded self-evolution loop.

ONE bounded, deterministic, model-independent cycle that carries a Phase-10
discovery candidate through the EXISTING governed lifecycle:

    Phase 10 discovery (candidate + assessment)
        -> 11.1 evolution candidate intake        (validate evidence)
        -> 11.2 eligibility assessment            (explainable state)
        -> 11.3 evolution objective               (existing DevelopmentNeed)
        -> 11.4/11.5/11.6 governed preparation    (existing DevelopmentCycleController
                                                   + research seam + ApprovalManager)
        -> STOP at the human approval boundary
        -> 11.7 sandbox execution                 (existing SelfDevelopmentLoop)
        -> 11.8 verification                      (existing DevelopmentVerification)
        -> 11.9 bounded diagnosis/recovery        (existing Diagnostic/Recovery)
        -> 11.10 lifecycle evidence               (existing EvolutionMemory/EvolutionRecord)
        -> 11.11 governed promotion + activation  (existing PromotionGate / PromotionExecutor
                                                   / CapabilityActivator)
        -> 11.12 self-model consistency           (existing CapabilityModel projection)
        -> 11.13 outcome learning                 (existing EvolutionRecord/Insight)
        -> TERMINATE (never auto-starts another cycle)

Architectural boundaries (enforced, not merely documented):

* It adds NO planner, research system, registry, sandbox, memory, governance
  system, or agent framework — every stage is the existing Atlas component.
* It never approves, promotes, or activates on its own authority: approval and
  promotion authorization are EXTERNAL human/OWNER decisions passed in by the
  caller; the loop only performs the state transition through the existing
  governed managers.
* Discovery and research never grant authority.
* Verification success is never promotion; review approval is never activation.
* One bounded invocation with an explicit terminal state. No loops, no
  daemons, no timers, no self-triggering, no auto-restart
  (``next_cycle_allowed`` is always ``False``).

Model-independent: stdlib + existing Atlas modules only. No AI, no network.
"""

from __future__ import annotations

import hashlib
import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Iterable

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.capability_activation import (
    CapabilityActivationError,
    CapabilityActivator,
)
from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoveryVerdict,
)
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentCyclePolicy,
    DevelopmentNeed,
)
from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.development_recovery import DevelopmentRecovery
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.development_verification import (
    DevelopmentVerification,
    VerificationStatus,
)
from atlas.evolution.models import (
    EvolutionInsight,
    EvolutionProposal,
    EvolutionRecord,
    ProposalStatus,
)
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.evolution.promotion_executor import PromotionExecutor, PromotionOutcome
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
    PromotionRequest,
    PromotionStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.self_knowledge.capability_model import build_capability_model

#: Hard upper bound for sandbox iterations inside ONE evolution cycle.
MAX_DEVELOPMENT_ITERATIONS: int = 3

#: Process-wide cycle sequence. A per-instance counter alone is not a durable
#: identity: two loop instances (or two restarted processes) would both begin at
#: ``000001``, leaving distinct cycles indistinguishable in persisted history.
#: The sequence makes ids unique within a process and the random suffix makes
#: them unique across restarts.
_CYCLE_SEQUENCE: "itertools.count[int]" = itertools.count(1)


def _stable_id(seed: str, length: int = 16) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]


def _text(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


# ---------------------------------------------------------------------------
# 11.1 — Evolution candidate intake
# ---------------------------------------------------------------------------


class EvolutionCandidateStatus(str, Enum):
    """Validity of a candidate as an evolution input."""

    DISCOVERED = "discovered"   # raw discovery output; not yet validated
    VALIDATED = "validated"     # evidence-backed; may be assessed for eligibility
    REJECTED = "rejected"       # unsupported/malformed; fails closed


@dataclass(frozen=True, slots=True)
class EvolutionCandidate:
    """A validated-or-rejected evolution input derived from discovery."""

    candidate_id: str
    subject: str
    status: EvolutionCandidateStatus
    rationale: str = ""
    evidence: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    uncertainty: str = ""
    research_status: str = ""
    goal_context: str = ""
    constraints: tuple[str, ...] = ()
    capability_state: str = ""
    dependencies: tuple[str, ...] = ()
    discovery_verdict: str = ""

    @property
    def validated(self) -> bool:
        return self.status is EvolutionCandidateStatus.VALIDATED

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "subject": self.subject,
            "status": self.status.value,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "provenance": list(self.provenance),
            "uncertainty": self.uncertainty,
            "research_status": self.research_status,
            "goal_context": self.goal_context,
            "constraints": list(self.constraints),
            "capability_state": self.capability_state,
            "dependencies": list(self.dependencies),
            "discovery_verdict": self.discovery_verdict,
        }


#: Phase-10 verdicts that can never validate an evolution candidate.
_NON_VALIDATING_VERDICTS: frozenset[DiscoveryVerdict] = frozenset(
    {
        DiscoveryVerdict.INSUFFICIENT_EVIDENCE,
        DiscoveryVerdict.ALREADY_SUPPORTED,
        DiscoveryVerdict.DUPLICATE,
        DiscoveryVerdict.BLOCKED_DEPENDENCY,
        DiscoveryVerdict.GOVERNANCE_BLOCKED,
    }
)


def evolution_candidate_from_discovery(
    candidate: Any,
    assessment: Any,
    *,
    goal_context: str = "",
    constraints: Iterable[str] = (),
) -> EvolutionCandidate:
    """Convert Phase-10 discovery output into an evolution candidate.

    Creating a candidate grants NO authority: it is a validated data record
    only. Unsupported or malformed discovery output fails closed to
    ``REJECTED`` (never silently actionable).
    """
    if not isinstance(candidate, CapabilityDiscoveryCandidate) or not isinstance(
        assessment, DiscoveryAssessment
    ):
        return EvolutionCandidate(
            candidate_id="",
            subject="",
            status=EvolutionCandidateStatus.REJECTED,
            rationale="malformed discovery input (fail closed)",
        )

    base = dict(
        candidate_id=candidate.candidate_id,
        subject=candidate.subject,
        evidence=tuple(candidate.evidence),
        provenance=tuple(candidate.sources),
        goal_context=_text(goal_context),
        constraints=tuple(_text(c) for c in constraints or ()),
        discovery_verdict=assessment.verdict.value,
    )
    limitations = "; ".join(candidate.limitations)

    if not candidate.evidence or not assessment.evidence:
        return EvolutionCandidate(
            **base,
            status=EvolutionCandidateStatus.REJECTED,
            rationale="no evidence supports this candidate",
            uncertainty=limitations,
        )
    if assessment.verdict in _NON_VALIDATING_VERDICTS:
        return EvolutionCandidate(
            **base,
            status=EvolutionCandidateStatus.REJECTED,
            rationale=f"discovery verdict '{assessment.verdict.value}' is not actionable",
            uncertainty=limitations,
        )
    if assessment.verdict is DiscoveryVerdict.ACTIONABLE_GAP:
        return EvolutionCandidate(
            **base,
            status=EvolutionCandidateStatus.VALIDATED,
            rationale="evidence-backed actionable capability gap",
            research_status="complete",
            capability_state="absent",
            uncertainty=limitations,
        )
    if assessment.verdict is DiscoveryVerdict.REQUIRES_RESEARCH:
        return EvolutionCandidate(
            **base,
            status=EvolutionCandidateStatus.VALIDATED,
            rationale="plausible gap; bounded research required before development",
            research_status="required",
            uncertainty=assessment.research_question or limitations,
            capability_state="unknown",
        )
    return EvolutionCandidate(
        **base,
        status=EvolutionCandidateStatus.REJECTED,
        rationale=f"verdict '{assessment.verdict.value}' does not authorize evolution",
        uncertainty=limitations,
    )


# ---------------------------------------------------------------------------
# 11.2 — Evolution eligibility
# ---------------------------------------------------------------------------


class EvolutionEligibilityState(str, Enum):
    """Explainable eligibility outcome (never authorization)."""

    ELIGIBLE = "eligible"
    REQUIRES_RESEARCH = "requires_research"
    BLOCKED_DEPENDENCY = "blocked_dependency"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ALREADY_SUPPORTED = "already_supported"
    GOVERNANCE_BLOCKED = "governance_blocked"
    INVALID_CANDIDATE = "invalid_candidate"


@dataclass(frozen=True, slots=True)
class EvolutionEligibility:
    """Deterministic, explainable eligibility assessment."""

    candidate_id: str
    state: EvolutionEligibilityState
    rationale: str
    evidence: tuple[str, ...] = ()
    research_question: str = ""

    @property
    def eligible(self) -> bool:
        return self.state is EvolutionEligibilityState.ELIGIBLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "state": self.state.value,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "research_question": self.research_question,
        }


def _capability_present(subject: str, capability_names: Iterable[str]) -> bool:
    """Deterministic token-overlap check against a known capability set."""
    from atlas.research._text import significant_tokens

    subject_tokens = significant_tokens(subject) | significant_tokens(
        subject.replace(".", " ").replace("_", " ")
    )
    if not subject_tokens:
        return False
    for name in capability_names or ():
        if not isinstance(name, str) or not name:
            continue
        name_tokens = significant_tokens(
            name.replace(".", " ").replace("_", " ").replace("-", " ")
        )
        if name_tokens and name_tokens <= subject_tokens:
            return True
    return False


def _knowledge_present(knowledge_retriever: Any | None, query: str) -> bool:
    """Best-effort validated-knowledge presence (never fabricated)."""
    if knowledge_retriever is None or not callable(
        getattr(knowledge_retriever, "retrieve", None)
    ):
        return False
    try:
        result = knowledge_retriever.retrieve(query)
    except Exception:
        return False
    items = getattr(result, "items", None)
    if items is None and isinstance(result, (list, tuple)):
        items = result
    try:
        return len(list(items or ())) > 0
    except TypeError:
        return False


def assess_evolution_eligibility(
    candidate: Any,
    *,
    capability_names: Iterable[str] = (),
    knowledge_retriever: Any | None = None,
    dependency_blocked: bool = False,
    governance_blocked: bool = False,
) -> EvolutionEligibility:
    """Assess whether a validated candidate may enter an evolution attempt.

    Deterministic precedence, fail-closed. The result is a discovery-side
    eligibility assessment, NOT authorization to develop.
    """
    if not isinstance(candidate, EvolutionCandidate) or not candidate.subject:
        return EvolutionEligibility(
            candidate_id="",
            state=EvolutionEligibilityState.INVALID_CANDIDATE,
            rationale="malformed candidate (fail closed)",
        )
    if not candidate.validated:
        return EvolutionEligibility(
            candidate_id=candidate.candidate_id,
            state=EvolutionEligibilityState.INVALID_CANDIDATE,
            rationale=f"candidate status is '{candidate.status.value}'",
            evidence=candidate.evidence,
        )
    if governance_blocked:
        return EvolutionEligibility(
            candidate_id=candidate.candidate_id,
            state=EvolutionEligibilityState.GOVERNANCE_BLOCKED,
            rationale="governance blocks evolution for this subject",
            evidence=candidate.evidence,
        )
    if not candidate.evidence:
        return EvolutionEligibility(
            candidate_id=candidate.candidate_id,
            state=EvolutionEligibilityState.INSUFFICIENT_EVIDENCE,
            rationale="no evidence accompanies the candidate",
        )
    if _capability_present(candidate.subject, capability_names):
        return EvolutionEligibility(
            candidate_id=candidate.candidate_id,
            state=EvolutionEligibilityState.ALREADY_SUPPORTED,
            rationale="the subject already matches a registered capability",
            evidence=candidate.evidence,
        )
    if dependency_blocked or candidate.dependencies:
        return EvolutionEligibility(
            candidate_id=candidate.candidate_id,
            state=EvolutionEligibilityState.BLOCKED_DEPENDENCY,
            rationale="a required dependency is unavailable",
            evidence=candidate.evidence,
        )
    if candidate.research_status == "required":
        question = candidate.uncertainty or f"what is required to {candidate.subject}"
        if not _knowledge_present(knowledge_retriever, question):
            return EvolutionEligibility(
                candidate_id=candidate.candidate_id,
                state=EvolutionEligibilityState.REQUIRES_RESEARCH,
                rationale="evidence is insufficient; bounded research is required first",
                evidence=candidate.evidence,
                research_question=question,
            )
    return EvolutionEligibility(
        candidate_id=candidate.candidate_id,
        state=EvolutionEligibilityState.ELIGIBLE,
        rationale="evidence-backed, unsupported, unblocked capability gap",
        evidence=candidate.evidence,
    )


# ---------------------------------------------------------------------------
# 11.3 — Evolution objective (the EXISTING DevelopmentNeed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvolutionObjective:
    """A bounded, verifiable evolution objective.

    Deliberately thin: the objective of record IS the existing
    ``DevelopmentNeed`` (see :meth:`to_development_need`); no parallel
    planning model is introduced.
    """

    objective_id: str
    candidate_id: str
    title: str
    summary: str
    rationale: str
    expected_benefit: str
    evidence: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    affected_surfaces: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    target_module: str = ""
    capability_name: str = ""
    test_module: str = ""

    def to_development_need(self) -> DevelopmentNeed:
        """Render the objective as the existing ``DevelopmentNeed``."""
        return DevelopmentNeed(
            title=self.title,
            summary=self.summary,
            rationale=self.rationale,
            expected_benefit=self.expected_benefit,
            target_components=(self.target_module,),
            candidate_id=self.candidate_id,
            evidence_knowledge_ids=self.evidence,
            metadata={
                "scaffold": {
                    "module": self.target_module,
                    "capability_name": self.capability_name,
                    **({"test_module": self.test_module} if self.test_module else {}),
                },
                "evolution_objective": self.to_dict(),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "candidate_id": self.candidate_id,
            "title": self.title,
            "summary": self.summary,
            "rationale": self.rationale,
            "expected_benefit": self.expected_benefit,
            "evidence": list(self.evidence),
            "constraints": list(self.constraints),
            "success_criteria": list(self.success_criteria),
            "affected_surfaces": list(self.affected_surfaces),
            "risks": list(self.risks),
            "target_module": self.target_module,
            "capability_name": self.capability_name,
            "test_module": self.test_module,
        }


def form_evolution_objective(
    candidate: Any,
    *,
    target_module: str,
    capability_name: str,
    test_module: str = "",
    success_criteria: Iterable[str] = (),
    affected_surfaces: Iterable[str] = (),
) -> EvolutionObjective | None:
    """Form a bounded objective for an eligible candidate, or ``None``.

    Fails closed (returns ``None``) when the candidate is not validated, the
    evidence is empty, or the target module/capability is malformed or not
    sandbox-confined. No objective is invented for an invalid candidate.
    """
    if not isinstance(candidate, EvolutionCandidate) or not candidate.validated:
        return None
    if not candidate.evidence:
        return None
    module = (target_module or "").strip().replace("\\", "/")
    capability = (capability_name or "").strip()
    if not module or not capability:
        return None
    from atlas.evolution.development_cycle import validate_change_path

    try:
        validate_change_path(module)
        if test_module:
            validate_change_path(test_module.strip().replace("\\", "/"))
    except ValueError:
        return None  # path escape / malformed target -> fail closed

    return EvolutionObjective(
        objective_id="EVOBJ-" + _stable_id(f"{candidate.candidate_id}:{module}:{capability}"),
        candidate_id=candidate.candidate_id,
        title=f"Evolve capability: {capability}",
        summary=(
            f"Introduce the '{capability}' capability in {module} so Atlas can "
            f"perform what the discovered gap requires."
        ),
        rationale=candidate.rationale,
        expected_benefit=(
            f"Atlas gains the '{capability}' capability and no longer has the "
            f"discovered gap: {candidate.subject}"
        ),
        evidence=tuple(candidate.evidence),
        constraints=tuple(candidate.constraints) + tuple(_text(c) for c in affected_surfaces or ()),
        success_criteria=tuple(_text(c) for c in success_criteria or ())
        or (f"'{capability}' is registered, verified, and routable",),
        affected_surfaces=tuple(_text(s) for s in affected_surfaces or ()) or (module,),
        risks=(
            "Draft content is unverified; requires human approval, sandbox "
            "verification, and governed promotion before any effect.",
        ),
        target_module=module,
        capability_name=capability,
        test_module=(test_module or "").strip().replace("\\", "/"),
    )


# ---------------------------------------------------------------------------
# 11.12 — Self-model consistency (after governed activation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SelfModelValidation:
    """Deterministic projection of the self-model after activation."""

    capability: str
    represented: bool = False
    routable: bool = False
    invocable: bool = False
    availability: str = ""
    dependency: str = ""
    reason: str = ""

    @property
    def consistent(self) -> bool:
        return self.represented and self.routable and self.invocable

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "represented": self.represented,
            "routable": self.routable,
            "invocable": self.invocable,
            "availability": self.availability,
            "dependency": self.dependency,
            "consistent": self.consistent,
            "reason": self.reason,
        }


def project_evolved_capability(
    component_registry: Any,
    *,
    module_path: str,
    capability_name: str,
    component_name: str = "",
) -> ComponentMetadata | None:
    """Project a newly activated capability into the self-model inputs.

    The smallest necessary deterministic projection: the existing
    ``ComponentRegistry`` is authoritative for "which component provides which
    capability", so the activated module is registered as a HEALTHY provider
    so the capability model reflects it honestly. Read-only with respect to
    production code; returns ``None`` when the capability is already provided.
    """
    if component_registry is None:
        return None
    module = (module_path or "").strip().replace("\\", "/")
    capability = (capability_name or "").strip()
    if not module or not capability:
        return None
    for component in component_registry.get_all():
        if capability in tuple(getattr(component, "provided_capabilities", ()) or ()):
            return None  # already represented; never invent duplication
    dotted = module[:-3] if module.endswith(".py") else module
    package = ".".join(dotted.split("/")[:-1]) or "atlas"
    name = component_name or ("evolved_" + _stable_id(f"{module}:{capability}", 10))
    metadata = ComponentMetadata(
        name=name,
        package=package,
        module_path=dotted.replace("/", "."),
        status=ComponentStatus.HEALTHY,
        provided_capabilities=[capability],
    )
    component_registry.register(metadata)
    return metadata


def validate_self_model(
    capability_name: str,
    *,
    component_registry: Any = None,
    capability_registry: Any = None,
) -> SelfModelValidation:
    """Verify the self-model accurately reflects an activated capability.

    Read-only: builds the existing capability model and probes the existing
    router/dispatcher. Never fabricates self-knowledge — an unrepresented
    capability is reported as unrepresented.
    """
    capability = (capability_name or "").strip()
    if not capability or capability_registry is None:
        return SelfModelValidation(
            capability=capability, reason="capability registry unavailable"
        )

    model = build_capability_model(
        component_registry if component_registry is not None else ComponentRegistry(),
        capability_registry=capability_registry,
    )
    entry = next((e for e in model.entries if e.name == capability), None)
    represented = entry is not None

    routable = False
    invocable = False
    try:
        routes = CapabilityRouter(capability_registry).route([Capability(name=capability)])
        routable = bool(routes) and routes[0].capability == capability
    except Exception:
        routable = False
    try:
        results = CapabilityDispatcher(capability_registry).dispatch(
            [Capability(name=capability)]
        )
        invocable = bool(results) and bool(results[0].success)
    except Exception:
        invocable = False

    return SelfModelValidation(
        capability=capability,
        represented=represented,
        routable=routable,
        invocable=invocable,
        availability=entry.availability.value if entry else "",
        dependency=entry.dependency.value if entry else "",
        reason=(
            "self-model reflects the activated capability"
            if represented
            else "capability is not represented in the capability model"
        ),
    )


# ---------------------------------------------------------------------------
# 11.13 — Outcome learning
# ---------------------------------------------------------------------------


class EvolutionOutcomeKind(str, Enum):
    """Post-cycle outcome classification for future evidence-based reasoning."""

    SUCCESSFUL_EVOLUTION = "successful_evolution"
    UNSUCCESSFUL_ATTEMPT = "unsuccessful_attempt"
    VERIFICATION_FAILURE = "verification_failure"
    GOVERNANCE_REJECTION = "governance_rejection"
    RESEARCH_INSUFFICIENCY = "research_insufficiency"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    PARTIAL_RESULT = "partial_result"


class SelfEvolutionTerminal(str, Enum):
    """The explicit, single terminal state of one evolution cycle."""

    REJECTED_CANDIDATE = "rejected_candidate"
    INELIGIBLE = "ineligible"
    RESEARCH_REQUIRED = "research_required"
    INVALID_OBJECTIVE = "invalid_objective"
    PREPARATION_FAILED = "preparation_failed"
    STOPPED_AT_APPROVAL = "stopped_at_approval"
    SANDBOX_FAILED = "sandbox_failed"
    VERIFICATION_FAILED = "verification_failed"
    PROMOTION_NOT_READY = "promotion_not_ready"
    PENDING_PROMOTION_REVIEW = "pending_promotion_review"
    PROMOTION_NOT_AUTHORIZED = "promotion_not_authorized"
    PROMOTION_FAILED = "promotion_failed"
    ACTIVATED = "activated"
    SELF_MODEL_INCONSISTENT = "self_model_inconsistent"
    INVALID_LIFECYCLE_STATE = "invalid_lifecycle_state"


_OUTCOME_BY_TERMINAL: dict[SelfEvolutionTerminal, EvolutionOutcomeKind] = {
    SelfEvolutionTerminal.ACTIVATED: EvolutionOutcomeKind.SUCCESSFUL_EVOLUTION,
    SelfEvolutionTerminal.REJECTED_CANDIDATE: EvolutionOutcomeKind.PARTIAL_RESULT,
    SelfEvolutionTerminal.INELIGIBLE: EvolutionOutcomeKind.PARTIAL_RESULT,
    SelfEvolutionTerminal.RESEARCH_REQUIRED: EvolutionOutcomeKind.RESEARCH_INSUFFICIENCY,
    SelfEvolutionTerminal.INVALID_OBJECTIVE: EvolutionOutcomeKind.UNSUCCESSFUL_ATTEMPT,
    SelfEvolutionTerminal.PREPARATION_FAILED: EvolutionOutcomeKind.UNSUCCESSFUL_ATTEMPT,
    SelfEvolutionTerminal.STOPPED_AT_APPROVAL: EvolutionOutcomeKind.GOVERNANCE_REJECTION,
    SelfEvolutionTerminal.SANDBOX_FAILED: EvolutionOutcomeKind.UNSUCCESSFUL_ATTEMPT,
    SelfEvolutionTerminal.VERIFICATION_FAILED: EvolutionOutcomeKind.VERIFICATION_FAILURE,
    SelfEvolutionTerminal.PROMOTION_NOT_READY: EvolutionOutcomeKind.PARTIAL_RESULT,
    SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW: EvolutionOutcomeKind.PARTIAL_RESULT,
    SelfEvolutionTerminal.PROMOTION_NOT_AUTHORIZED: EvolutionOutcomeKind.GOVERNANCE_REJECTION,
    SelfEvolutionTerminal.PROMOTION_FAILED: EvolutionOutcomeKind.UNSUCCESSFUL_ATTEMPT,
    SelfEvolutionTerminal.SELF_MODEL_INCONSISTENT: EvolutionOutcomeKind.PARTIAL_RESULT,
    SelfEvolutionTerminal.INVALID_LIFECYCLE_STATE: EvolutionOutcomeKind.UNSUCCESSFUL_ATTEMPT,
}


def classify_evolution_outcome(terminal: Any) -> EvolutionOutcomeKind:
    """Map a terminal state to the outcome fed back into history."""
    if isinstance(terminal, SelfEvolutionTerminal):
        return _OUTCOME_BY_TERMINAL.get(terminal, EvolutionOutcomeKind.PARTIAL_RESULT)
    return EvolutionOutcomeKind.PARTIAL_RESULT


def record_evolution_outcome(
    memory: Any,
    *,
    cycle_id: str,
    candidate: Any,
    terminal: Any,
    summary: str = "",
    proposal_id: str = "",
) -> EvolutionRecord | None:
    """Persist the cycle outcome through the EXISTING evolution memory.

    Stores one ``evolution_outcome`` record plus one ``EvolutionInsight`` so
    future discovery/planning can consume the evidence. Never creates a second
    history store, and never starts another cycle.
    """
    if memory is None:
        return None
    kind = classify_evolution_outcome(terminal)
    # Durable identity must be unique per cycle AND per subject: the cycle
    # counter alone restarts with each loop instance (and across restarts), so
    # seeding on it would let two distinct cycles collide on one record id and
    # make the persisted history indistinguishable. The subject and the
    # proposal id (unique per prepared cycle) disambiguate them.
    subject = _text(getattr(candidate, "subject", ""), 200)
    record = EvolutionRecord(
        record_id=f"EVO-{_stable_id(f'{cycle_id}:{subject}:{proposal_id}:{kind.value}')}",
        event_type="evolution_outcome",
        description=_text(
            f"Self-evolution cycle {cycle_id} terminated as "
            f"'{getattr(terminal, 'value', terminal)}' ({kind.value}). {summary}",
            500,
        ),
        related_ids=[i for i in (proposal_id, getattr(candidate, "candidate_id", "")) if i],
        metadata={
            "cycle_id": cycle_id,
            "terminal": getattr(terminal, "value", str(terminal)),
            "outcome_kind": kind.value,
            "subject": subject,
        },
    )
    memory.store_record(record)
    try:
        memory.store_insight(
            EvolutionInsight(
                insight_id=f"INS-{_stable_id(record.record_id)}",
                proposal_id=proposal_id or "",
                execution_record_id=record.record_id,
                tracked_goal_id="",
                outcome=kind.value,
                confidence=1.0,
                effectiveness_score=(
                    1.0 if kind is EvolutionOutcomeKind.SUCCESSFUL_EVOLUTION else 0.0
                ),
                evidence_summary=_text(summary, 500),
                evidence_count=1,
                evidence_quality=1.0 if getattr(candidate, "evidence", ()) else 0.0,
                regression_risk=0.0,
                proposal_title=getattr(candidate, "subject", ""),
                proposal_summary=kind.value,
                metadata={"cycle_id": cycle_id, "terminal": record.metadata["terminal"]},
            )
        )
    except Exception:
        pass  # insight persistence must never break the cycle record
    return record


# ---------------------------------------------------------------------------
# 11.14 — The bounded cycle
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SelfEvolutionPolicy:
    """Deterministic bounds for one evolution cycle."""

    max_development_iterations: int = 1
    max_message_chars: int = 400
    require_promotion_review: bool = True

    def __post_init__(self) -> None:
        if self.max_development_iterations < 1:
            raise ValueError("max_development_iterations must be >= 1")
        if self.max_development_iterations > MAX_DEVELOPMENT_ITERATIONS:
            raise ValueError(
                f"max_development_iterations must be <= {MAX_DEVELOPMENT_ITERATIONS}"
            )


@dataclass(frozen=True, slots=True)
class SelfEvolutionCycleResult:
    """Bounded, evidence-rich result of ONE evolution cycle."""

    cycle_id: str
    terminal: SelfEvolutionTerminal
    candidate: EvolutionCandidate | None = None
    eligibility: EvolutionEligibility | None = None
    objective: EvolutionObjective | None = None
    proposal_id: str = ""
    approval_request_id: str = ""
    approval_status: str = ""
    development_status: str = ""
    verification_status: str = ""
    failure_class: str = ""
    recovery_strategy: str = ""
    promotion_review_status: str = ""
    promotion_outcome: str = ""
    activated_capabilities: tuple[str, ...] = ()
    self_model: SelfModelValidation | None = None
    outcome: EvolutionOutcomeKind | None = None
    evidence_records: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    next_cycle_allowed: bool = False

    @property
    def ok(self) -> bool:
        return self.terminal is SelfEvolutionTerminal.ACTIVATED

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "terminal": self.terminal.value,
            "ok": self.ok,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "eligibility": self.eligibility.to_dict() if self.eligibility else None,
            "objective": self.objective.to_dict() if self.objective else None,
            "proposal_id": self.proposal_id,
            "approval_request_id": self.approval_request_id,
            "approval_status": self.approval_status,
            "development_status": self.development_status,
            "verification_status": self.verification_status,
            "failure_class": self.failure_class,
            "recovery_strategy": self.recovery_strategy,
            "promotion_review_status": self.promotion_review_status,
            "promotion_outcome": self.promotion_outcome,
            "activated_capabilities": list(self.activated_capabilities),
            "self_model": self.self_model.to_dict() if self.self_model else None,
            "outcome": self.outcome.value if self.outcome else None,
            "evidence_records": list(self.evidence_records),
            "messages": list(self.messages),
            "next_cycle_allowed": self.next_cycle_allowed,
        }


class SelfEvolutionLoop:
    """The bounded, governed, model-independent self-evolution loop.

    Every dependency is the EXISTING Atlas component. Approval and promotion
    authorization are external human/OWNER decisions passed into :meth:`run`
    — the loop never mints authority and never starts another cycle.
    """

    def __init__(
        self,
        *,
        approval_manager: ApprovalManager | None = None,
        change_supplier: Any = None,
        researcher: Callable[..., Any] | None = None,
        evolution_memory: Any = None,
        promotion_gate: Any = None,
        component_registry: Any = None,
        capability_registry: Any = None,
        repo_root: Any = None,
        policy: SelfEvolutionPolicy | None = None,
        development_loop: Any = None,
    ) -> None:
        self._approval_manager = approval_manager or ApprovalManager()
        self._change_supplier = change_supplier or ScaffoldChangeSupplier()
        self._researcher = researcher
        self._memory = evolution_memory
        self._gate = promotion_gate or PromotionGate(evolution_memory=evolution_memory)
        self._components = component_registry or ComponentRegistry()
        self._capabilities = capability_registry or CapabilityRegistry()
        self._repo_root = repo_root
        self._policy = policy or SelfEvolutionPolicy()
        self._development_loop = development_loop or SelfDevelopmentLoop()
        self._counter = 0

    @property
    def policy(self) -> SelfEvolutionPolicy:
        return self._policy

    # -- public single-shot entry ------------------------------------------

    def run(
        self,
        candidate: Any,
        assessment: Any,
        *,
        target_module: str,
        capability_name: str,
        test_module: str = "",
        goal_context: str = "",
        constraints: Iterable[str] = (),
        success_criteria: Iterable[str] = (),
        affected_surfaces: Iterable[str] = (),
        capability_names: Iterable[str] | None = None,
        knowledge_retriever: Any | None = None,
        dependency_blocked: bool = False,
        governance_blocked: bool = False,
        owner_approved: bool = False,
        promotion_authorized: bool = False,
    ) -> SelfEvolutionCycleResult:
        """Run ONE bounded evolution cycle and terminate.

        ``owner_approved`` and ``promotion_authorized`` represent EXTERNAL
        human/OWNER decisions (the same seam as
        ``PromotionExecutor.promote(authorized=...)``); the loop performs the
        governed state transitions but never decides them.
        """
        self._counter += 1
        cycle_id = f"SEV-{next(_CYCLE_SEQUENCE):06d}-{uuid.uuid4().hex[:8]}"
        names = capability_names
        if names is None:
            names = self._known_capabilities()

        evidence_records: list[str] = []
        messages: list[str] = []

        def _finish(terminal: SelfEvolutionTerminal, **kwargs: Any) -> SelfEvolutionCycleResult:
            outcome = classify_evolution_outcome(terminal)
            record = record_evolution_outcome(
                self._memory,
                cycle_id=cycle_id,
                candidate=kwargs.get("candidate"),
                terminal=terminal,
                summary=kwargs.get("summary", ""),
                proposal_id=kwargs.get("proposal_id", ""),
            )
            if record is not None:
                evidence_records.append(record.record_id)
            return SelfEvolutionCycleResult(
                cycle_id=cycle_id,
                terminal=terminal,
                outcome=outcome,
                evidence_records=tuple(evidence_records),
                messages=tuple(messages),
                next_cycle_allowed=False,  # a cycle NEVER auto-starts another
                **{k: v for k, v in kwargs.items() if k != "summary"},
            )

        # --- 11.1 candidate intake ----------------------------------------
        evolution_candidate = evolution_candidate_from_discovery(
            candidate, assessment, goal_context=goal_context, constraints=constraints
        )
        messages.append(f"intake: {evolution_candidate.status.value}")
        if not evolution_candidate.validated:
            return _finish(
                SelfEvolutionTerminal.REJECTED_CANDIDATE,
                candidate=evolution_candidate,
                summary=evolution_candidate.rationale,
            )

        # --- 11.2 eligibility ---------------------------------------------
        eligibility = assess_evolution_eligibility(
            evolution_candidate,
            capability_names=names,
            knowledge_retriever=knowledge_retriever,
            dependency_blocked=dependency_blocked,
            governance_blocked=governance_blocked,
        )
        messages.append(f"eligibility: {eligibility.state.value}")
        if not eligibility.eligible:
            terminal = (
                SelfEvolutionTerminal.RESEARCH_REQUIRED
                if eligibility.state is EvolutionEligibilityState.REQUIRES_RESEARCH
                else SelfEvolutionTerminal.INELIGIBLE
            )
            return _finish(
                terminal,
                candidate=evolution_candidate,
                eligibility=eligibility,
                summary=eligibility.rationale,
            )

        # --- 11.3 objective -------------------------------------------------
        objective = form_evolution_objective(
            evolution_candidate,
            target_module=target_module,
            capability_name=capability_name,
            test_module=test_module,
            success_criteria=success_criteria,
            affected_surfaces=affected_surfaces,
        )
        if objective is None:
            messages.append("objective: invalid")
            return _finish(
                SelfEvolutionTerminal.INVALID_OBJECTIVE,
                candidate=evolution_candidate,
                eligibility=eligibility,
                summary="objective formation failed closed",
            )
        messages.append(f"objective: {objective.objective_id}")

        # --- 11.4/11.5/11.6 governed preparation (research + plan + approval)
        store = _ProposalCapture()
        controller = DevelopmentCycleController(
            approval_manager=self._approval_manager,
            change_supplier=self._change_supplier,
            researcher=self._researcher,
            policy=DevelopmentCyclePolicy(),
            proposal_store=store,
            approval_request_store=store,
        )
        cycle = controller.run_development_cycle(objective.to_development_need())
        if not cycle.ok or not store.proposals or not store.requests:
            failures = "; ".join(f"{stage}: {msg}" for stage, msg in cycle.failures)
            messages.append(f"preparation: failed ({failures})")
            return _finish(
                SelfEvolutionTerminal.PREPARATION_FAILED,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                summary=failures or "preparation failed closed",
            )
        proposal: EvolutionProposal = store.proposals[0]
        request = store.requests[0]
        messages.append(f"prepared: {proposal.proposal_id} -> {proposal.status.name}")

        if proposal.status is not ProposalStatus.PENDING_APPROVAL:
            return _finish(
                SelfEvolutionTerminal.INVALID_LIFECYCLE_STATE,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_status=proposal.status.name,
                summary="prepared proposal is not at the approval boundary",
            )

        # --- THE HUMAN APPROVAL BOUNDARY ----------------------------------
        if not owner_approved:
            messages.append("approval: withheld (stopping at the boundary)")
            return _finish(
                SelfEvolutionTerminal.STOPPED_AT_APPROVAL,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_request_id=getattr(request, "request_id", ""),
                approval_status=proposal.status.name,
                summary="awaiting explicit human/OWNER approval",
            )
        try:
            self._approval_manager.approve(request, comment="owner-approved")
            self._approval_manager.update_proposal_from_decision(proposal, request)
        except Exception as exc:
            return _finish(
                SelfEvolutionTerminal.INVALID_LIFECYCLE_STATE,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_request_id=getattr(request, "request_id", ""),
                approval_status=proposal.status.name,
                summary=f"approval transition failed: {type(exc).__name__}",
            )
        if proposal.status is not ProposalStatus.APPROVED:
            return _finish(
                SelfEvolutionTerminal.INVALID_LIFECYCLE_STATE,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_status=proposal.status.name,
                summary="proposal did not reach APPROVED",
            )

        # --- 11.7 sandbox execution ------------------------------------------
        run = self._development_loop.run(
            proposal, max_iterations=self._policy.max_development_iterations
        )
        development_status = getattr(run.status, "name", str(run.status))
        messages.append(f"development: {development_status}")

        # --- 11.8 verification (implementation != verification) --------------
        verification = DevelopmentVerification().verify(run)
        messages.append(f"verification: {verification.status.value}")

        diagnosis = None
        recovery = None
        if run.status is not DevelopmentOutcomeStatus.SUCCESS:
            diagnosis = DevelopmentDiagnostic().diagnose(run)
            recovery = DevelopmentRecovery().decide(run, diagnosis)
            return _finish(
                SelfEvolutionTerminal.SANDBOX_FAILED,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_request_id=getattr(request, "request_id", ""),
                approval_status=proposal.status.name,
                development_status=development_status,
                verification_status=verification.status.value,
                failure_class=getattr(
                    getattr(diagnosis, "failure_class", None), "value", ""
                ),
                recovery_strategy=getattr(
                    getattr(recovery, "strategy", None), "value", ""
                ),
                summary=f"development failed ({development_status}); no success claimed",
            )
        if verification.status is not VerificationStatus.VERIFIED:
            return _finish(
                SelfEvolutionTerminal.VERIFICATION_FAILED,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_request_id=getattr(request, "request_id", ""),
                approval_status=proposal.status.name,
                development_status=development_status,
                verification_status=verification.status.value,
                summary="development was not verified; no evolution claimed",
            )

        # --- 11.10 lifecycle evidence -----------------------------------------
        dev_record = EvolutionRecord(
            record_id=f"DEVEV-{_stable_id(cycle_id + proposal.proposal_id)}",
            event_type="self_evolution_development",
            description=_text(
                f"Sandbox development for {objective.capability_name} verified "
                f"({verification.status.value})."
            ),
            related_ids=[proposal.proposal_id],
            metadata={
                "cycle_id": cycle_id,
                "objective_id": objective.objective_id,
                "changed_files": list(getattr(verification, "changed_files", ()) or ()),
                "iterations": run.iterations_used,
                "evidence": verification.evidence,
            },
        )
        if self._memory is not None:
            self._memory.store_record(dev_record)
            evidence_records.append(dev_record.record_id)

        # --- 11.11 promotion review (review is NOT promotion) ------------------
        gate = self._gate
        promotion_assessment = gate.assess(run, proposal_id=proposal.proposal_id)
        review: PromotionRequest = gate.request_review(promotion_assessment)
        review_status = review.status.value
        messages.append(f"promotion review: {review_status}")
        if promotion_assessment.recommendation is not PromotionRecommendation.READY_FOR_PROMOTION:
            return _finish(
                SelfEvolutionTerminal.PROMOTION_NOT_READY,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_status=proposal.status.name,
                development_status=development_status,
                verification_status=verification.status.value,
                promotion_review_status=review_status,
                summary="promotion review is not ready; no promotion performed",
            )

        # --- THE PROMOTION AUTHORIZATION BOUNDARY -----------------------------
        if not promotion_authorized:
            messages.append("promotion: not authorized (stopping at the boundary)")
            return _finish(
                SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_status=proposal.status.name,
                development_status=development_status,
                verification_status=verification.status.value,
                promotion_review_status=review_status,
                summary="verified; promotion awaits explicit OWNER authorization",
            )
        gate.approve(review, comment="owner-authorized")
        review_status = review.status.value

        # --- 11.11 governed promotion + activation ----------------------------
        repo_root = self._repo_root
        if repo_root is None:
            return _finish(
                SelfEvolutionTerminal.PROMOTION_FAILED,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                approval_status=proposal.status.name,
                development_status=development_status,
                verification_status=verification.status.value,
                promotion_review_status=review_status,
                summary="no repository root available for governed promotion",
            )
        try:
            artifact = capture_promotion_artifact(
                list(proposal.metadata.get("code_changes", [])),
                proposal_id=proposal.proposal_id,
                repo_root=repo_root,
            )
        except Exception as exc:
            return _finish(
                SelfEvolutionTerminal.PROMOTION_FAILED,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                verification_status=verification.status.value,
                promotion_review_status=review_status,
                summary=f"artifact capture failed closed: {type(exc).__name__}",
            )
        executor = PromotionExecutor(
            repo_root,
            activator=CapabilityActivator(repo_root, self._capabilities),
        )
        promotion = executor.promote(artifact, authorized=True)
        messages.append(f"promotion: {promotion.outcome.value}")
        if promotion.outcome is PromotionOutcome.REFUSED_UNAUTHORIZED:
            return _finish(
                SelfEvolutionTerminal.PROMOTION_NOT_AUTHORIZED,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                verification_status=verification.status.value,
                promotion_review_status=review_status,
                promotion_outcome=promotion.outcome.value,
                summary="promotion refused: not authorized",
            )
        if not promotion.ok:
            return _finish(
                SelfEvolutionTerminal.PROMOTION_FAILED,
                candidate=evolution_candidate,
                eligibility=eligibility,
                objective=objective,
                proposal_id=proposal.proposal_id,
                verification_status=verification.status.value,
                promotion_review_status=review_status,
                promotion_outcome=promotion.outcome.value,
                summary=f"promotion failed closed ({promotion.outcome.value})",
            )

        # --- 11.12 self-model consistency --------------------------------------
        project_evolved_capability(
            self._components,
            module_path=objective.target_module,
            capability_name=objective.capability_name,
        )
        self_model = validate_self_model(
            objective.capability_name,
            component_registry=self._components,
            capability_registry=self._capabilities,
        )
        messages.append(
            f"self-model: {'consistent' if self_model.consistent else 'inconsistent'}"
        )
        terminal = (
            SelfEvolutionTerminal.ACTIVATED
            if self_model.consistent
            else SelfEvolutionTerminal.SELF_MODEL_INCONSISTENT
        )
        return _finish(
            terminal,
            candidate=evolution_candidate,
            eligibility=eligibility,
            objective=objective,
            proposal_id=proposal.proposal_id,
            approval_status=proposal.status.name,
            development_status=development_status,
            verification_status=verification.status.value,
            promotion_review_status=review_status,
            promotion_outcome=promotion.outcome.value,
            activated_capabilities=tuple(promotion.activated_capabilities),
            self_model=self_model,
            summary="governed activation complete; self-model validated",
        )

    # -- internals ----------------------------------------------------------

    def _known_capabilities(self) -> tuple[str, ...]:
        """Deterministic union of the existing authoritative capability names."""
        names: set[str] = set()
        try:
            names.update(str(n) for n in (self._capabilities.registered_names or ()))
        except Exception:
            pass
        try:
            for component in self._components.get_all():
                for cap in tuple(getattr(component, "provided_capabilities", ()) or ()):
                    names.add(str(cap))
        except Exception:
            pass
        return tuple(sorted(names))


class _ProposalCapture:
    """Minimal in-cycle store for the prepared proposal + approval request.

    Not a persistence layer: it only lets the loop read back what the EXISTING
    ``DevelopmentCycleController`` just submitted to the ``ApprovalManager``
    within this single bounded invocation.
    """

    def __init__(self) -> None:
        self.proposals: list[Any] = []
        self.requests: list[Any] = []

    def store_proposal(self, proposal: Any) -> None:
        self.proposals.append(proposal)

    def store_approval_request(self, request: Any) -> None:
        self.requests.append(request)
