"""Atlas Autonomy — Integrated Autonomous Intelligence Loop (Step 25).

A bounded, deterministic, model-free COORDINATOR that connects the completed
post-L10 capabilities into one governed end-to-end cycle:

    request
      -> understanding / adjudication        (EXISTING Step 15 knowledge need)
      -> knowledge assessment                (EXISTING Steps 16-21: research,
                                              provenance, retention, temporal,
                                              refresh request, monitoring)
      -> capability assessment               (EXISTING Step 22 gap adjudicator)
      -> specification / design              (EXISTING Step 23, only for a
                                              CONFIRMED genuine gap)
      -> governed self-development           (EXISTING Step 24 bridge: bounded
                                              need, DRAFT proposal, human
                                              approval boundary, sandbox
                                              execution, verification)
      -> promotion boundary                  (EXISTING promotion review)
      -> truthful response

It is orchestration ONLY. It adds no engine, planner, registry, store, approval
system, promotion path, source authorization or model dependency: every stage
calls an injected EXISTING seam and routes on that seam's OWN typed result.

Design guarantees:

* **Capability-driven, not a command cascade.** The next stage is chosen from the
  closed vocabulary of the previous stage's result (`KnowledgeNeedKind` /
  `KnowledgeNeedStatus`, `ResearchStatus`, `CapabilityGapKind`,
  `SpecificationStatus`, `SelfDevelopmentStage`) through explicit routing tables.
  A result that is not recognised is never guessed at: it fails closed.
* **Every governance boundary is preserved.** The loop never approves, never
  authorizes a source or a capability, never promotes and never writes to the
  live repository. Development stops at ``awaiting_approval``; promotion remains
  the separate OWNER decision; a refresh of stale knowledge happens ONLY when the
  caller explicitly asks for it and only through the EXISTING deny-by-default
  governed acquisition.
* **Deterministic and model-independent.** No model is consulted anywhere in this
  module and no external AI is ever treated as authority.
* **Fail-closed.** A missing seam, an unexpected result, or an exception at any
  stage ends the loop in ``failed`` naming the stage; insufficient evidence,
  ambiguity, missing knowledge, a refused design, an invalid authorization, a
  failed verification or a promoting-gate veto all produce a truthful non-success
  outcome rather than a claim.
* **No success before the work succeeds.** ``answered``/``refused``/
  ``not_promotable``/``failed`` describe what actually happened; a promotion
  boundary is reported only after the EXISTING verification actually reported
  ``verified``.
* **State survives the human boundary.** The immutable result carries every
  artifact of the cycle, so a human approval can interrupt the loop and
  :meth:`IntegratedIntelligenceLoop.resume` continues from the PRESERVED state
  (the proposal id and the specification), never by re-deriving or re-executing
  the completed prefix.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable

from atlas.evolution.specification_development import SelfDevelopmentStage
from atlas.research.knowledge_need import KnowledgeNeedKind, KnowledgeNeedStatus
from atlas.research.research_outcome import ResearchStatus
from atlas.self_knowledge.capability_gap import CapabilityGapKind
from atlas.self_knowledge.capability_specification import SpecificationStatus

#: Bounds (a malformed or hostile input can never produce unbounded output).
_MAX_REQUEST_CHARS: int = 300
_MAX_TEXT_CHARS: int = 300
_MAX_EVIDENCE_LINES: int = 16
_MAX_REASON_CHARS: int = 300
_MAX_URLS: int = 5
_MAX_PAYLOAD_ITEMS: int = 5

#: The loop's rule, stated once so callers can report it verbatim.
INTEGRATED_LOOP_RULE: str = (
    "Every stage of the integrated loop delegates to an existing capability and "
    "routes on that capability's own typed result. The loop approves nothing, "
    "authorizes nothing, promotes nothing and never touches the live repository: "
    "development stops at the existing human approval boundary, verification must "
    "actually succeed before a promotion boundary is reported, and insufficient "
    "evidence, ambiguity, missing knowledge, a refused design or an invalid "
    "authorization fail closed."
)


class LoopStage(str, Enum):
    """The stage of the cycle the loop actually reached (closed set)."""

    UNDERSTANDING = "understanding"
    RESEARCH = "research"
    PROVENANCE = "provenance"
    RETENTION = "retention"
    TEMPORAL = "temporal"
    REFRESH = "refresh"
    MONITORING = "monitoring"
    CAPABILITY = "capability"
    SPECIFICATION = "specification"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    PROMOTION = "promotion"


class LoopStatus(str, Enum):
    """The truthful conclusion of one loop invocation (closed set)."""

    ANSWERED = "answered"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_PROMOTION = "awaiting_promotion"
    REFUSED = "refused"
    NOT_PROMOTABLE = "not_promotable"
    FAILED = "failed"


class LoopAction(str, Enum):
    """The bounded next step the loop reports (never performs by itself)."""

    NONE = "none"
    PROVIDE_CHANGE_PAYLOAD = "provide_change_payload"
    PROVIDE_EVIDENCE = "provide_evidence"
    AUTHORIZE_SOURCE = "authorize_source"
    RESOLVE_AMBIGUITY = "resolve_ambiguity"
    ADDRESS_FAILURE = "address_failure"
    REVISE_DESIGN = "revise_design"
    APPROVE_PROPOSAL = "approve_proposal"
    PROVIDE_AUTHORIZATION = "provide_authorization"
    OWNER_PROMOTION = "owner_promotion"


# ---------------------------------------------------------------------------
# Routing tables — the loop is capability-driven: the next stage is selected
# from the previous stage's OWN typed result, never from raw text.
# ---------------------------------------------------------------------------

#: Knowledge-need kinds that require the governed research path.
_RESEARCH_ENTRY: frozenset[str] = frozenset(
    {
        KnowledgeNeedKind.MISSING.value,
        KnowledgeNeedKind.STALE.value,
        KnowledgeNeedKind.INSUFFICIENT.value,
        KnowledgeNeedKind.CONTRADICTORY.value,
    }
)

#: Knowledge-need kind that means "no knowledge work is required".
_NO_KNOWLEDGE_WORK: frozenset[str] = frozenset({KnowledgeNeedKind.NONE.value})

#: Research outcomes that leave evidence worth evaluating downstream.
_EVALUATE_AFTER_RESEARCH: frozenset[str] = frozenset(
    {ResearchStatus.RESEARCHED.value, ResearchStatus.NOT_NEEDED.value}
)

#: Knowledge-need kinds the loop cannot act on by itself.
_KNOWLEDGE_ACTIONS: dict[str, LoopAction] = {
    KnowledgeNeedKind.UNSUPPORTED_CAPABILITY.value: LoopAction.NONE,
    KnowledgeNeedKind.AMBIGUOUS.value: LoopAction.RESOLVE_AMBIGUITY,
    KnowledgeNeedKind.UNKNOWN.value: LoopAction.PROVIDE_EVIDENCE,
}

#: Research outcomes that blocked the knowledge step (with its own reason).
_RESEARCH_ACTIONS: dict[str, LoopAction] = {
    ResearchStatus.NO_AUTHORIZED_SOURCE.value: LoopAction.AUTHORIZE_SOURCE,
    ResearchStatus.INSUFFICIENT.value: LoopAction.PROVIDE_EVIDENCE,
    ResearchStatus.FAILED.value: LoopAction.ADDRESS_FAILURE,
    ResearchStatus.UNKNOWN.value: LoopAction.PROVIDE_EVIDENCE,
}

_RESEARCH_REASONS: dict[str, str] = {
    ResearchStatus.NO_AUTHORIZED_SOURCE.value: (
        "no authorized source is available for this subject"
    ),
    ResearchStatus.INSUFFICIENT.value: (
        "research produced insufficient evidence for this subject"
    ),
    ResearchStatus.FAILED.value: "the research step failed closed",
    ResearchStatus.UNKNOWN.value: "the research outcome could not be established",
}

#: Every non-gap adjudication, with the bounded next step it implies.
_GAP_ACTIONS: dict[str, LoopAction] = {
    CapabilityGapKind.SUPPORTED.value: LoopAction.NONE,
    CapabilityGapKind.TEMPORARILY_BLOCKED.value: LoopAction.NONE,
    CapabilityGapKind.GOVERNED.value: LoopAction.NONE,
    CapabilityGapKind.MISSING_KNOWLEDGE.value: LoopAction.PROVIDE_EVIDENCE,
    CapabilityGapKind.AMBIGUOUS.value: LoopAction.RESOLVE_AMBIGUITY,
    CapabilityGapKind.EXECUTION_FAILURE.value: LoopAction.ADDRESS_FAILURE,
    CapabilityGapKind.UNKNOWN.value: LoopAction.PROVIDE_EVIDENCE,
}

#: The development stage's own result mapped onto the loop's state machine.
_DEVELOPMENT_ROUTES: dict[str, tuple[LoopStage, LoopStatus, LoopAction]] = {
    SelfDevelopmentStage.AWAITING_APPROVAL.value: (
        LoopStage.PLANNING,
        LoopStatus.AWAITING_APPROVAL,
        LoopAction.APPROVE_PROPOSAL,
    ),
    SelfDevelopmentStage.IMPLEMENTATION.value: (
        LoopStage.IMPLEMENTATION,
        LoopStatus.FAILED,
        LoopAction.ADDRESS_FAILURE,
    ),
    SelfDevelopmentStage.VERIFICATION.value: (
        LoopStage.VERIFICATION,
        LoopStatus.AWAITING_PROMOTION,
        LoopAction.OWNER_PROMOTION,
    ),
    SelfDevelopmentStage.PROMOTION_REVIEW.value: (
        LoopStage.PROMOTION,
        LoopStatus.AWAITING_PROMOTION,
        LoopAction.OWNER_PROMOTION,
    ),
    SelfDevelopmentStage.NOT_PROMOTABLE.value: (
        LoopStage.VERIFICATION,
        LoopStatus.NOT_PROMOTABLE,
        LoopAction.ADDRESS_FAILURE,
    ),
    SelfDevelopmentStage.REFUSED.value: (
        LoopStage.PLANNING,
        LoopStatus.REFUSED,
        LoopAction.PROVIDE_AUTHORIZATION,
    ),
    SelfDevelopmentStage.FAILED.value: (
        LoopStage.PLANNING,
        LoopStatus.FAILED,
        LoopAction.ADDRESS_FAILURE,
    ),
}

#: Statuses the loop can be resumed from (the human boundaries plus the input gap).
_RESUMABLE: frozenset[LoopStatus] = frozenset(
    {LoopStatus.AWAITING_INPUT, LoopStatus.AWAITING_APPROVAL}
)

#: Knowledge-stage blockers that name a concrete remedy ("authorize a source",
#: "address the failure"). They survive a generic capability-stage verdict.
_KNOWLEDGE_BLOCKERS: frozenset[LoopAction] = frozenset(
    {LoopAction.AUTHORIZE_SOURCE, LoopAction.ADDRESS_FAILURE}
)

#: Capability-stage verdicts the knowledge stage never overrides (they describe
#: the request itself, not the knowledge shortage).
_GAP_BLOCKERS: frozenset[LoopAction] = frozenset(
    {LoopAction.RESOLVE_AMBIGUITY, LoopAction.REVISE_DESIGN}
)


def _resolve_action(
    provisional: LoopAction, gap_action: LoopAction, knowledge_verdict: bool
) -> LoopAction:
    """Report the MOST SPECIFIC next step the cycle actually established.

    The capability adjudicator is authoritative — it already reconciles the
    knowledge signal into its verdict — so its action wins, including its honest
    ``none`` for a supported request whose subject merely could not be researched.
    The ONE exception: when the verdict IS a knowledge verdict (a knowledge
    shortage, or evidence too thin to conclude anything) and the knowledge stage
    named a concrete remedy (``authorize_source`` / ``address_failure``), that
    remedy is reported instead of the generic "provide evidence".
    """
    if gap_action in _GAP_BLOCKERS:
        return gap_action
    if knowledge_verdict and provisional in _KNOWLEDGE_BLOCKERS:
        return provisional
    return gap_action


def _value(value: Any, limit: int = 60) -> str:
    """Bounded string form of an enum member, string, or anything else."""
    raw = getattr(value, "value", value)
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    return raw.strip()[:limit]


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _strings(values: Any, limit: int = _MAX_URLS) -> tuple[str, ...]:
    if not values:
        return ()
    try:
        items = list(values)
    except TypeError:
        return ()
    out: list[str] = []
    for item in items:
        text = _clean(item, 256)
        if text and text not in out:
            out.append(text)
    return tuple(out[:limit])


def _pairs(values: Any, limit: int = _MAX_PAYLOAD_ITEMS) -> tuple[tuple[str, str], ...]:
    if not values:
        return ()
    try:
        items = list(values)
    except TypeError:
        return ()
    out: list[tuple[str, str]] = []
    for item in items:
        try:
            path, content = item
        except Exception:
            continue
        path_text = _clean(path, 256)
        if path_text and isinstance(content, str):
            out.append((path_text, content))
    return tuple(out[:limit])


# ---------------------------------------------------------------------------
# Seams — every stage delegates to an EXISTING capability
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoopSeams:
    """The EXISTING capability seams the loop composes (all injected).

    Each seam is the corresponding EXISTING kernel entry point (Steps 15-24).
    ``None`` means the capability is unavailable, and the loop fails closed at
    the stage that needs it rather than inventing behaviour.
    """

    knowledge_need: Callable[..., Any] | None = None
    research: Callable[..., Any] | None = None
    provenance: Callable[..., Any] | None = None
    retention: Callable[..., Any] | None = None
    retained: Callable[..., Any] | None = None
    temporal: Callable[..., Any] | None = None
    refresh_requests: Callable[..., Any] | None = None
    refresh: Callable[..., Any] | None = None
    monitoring: Callable[..., Any] | None = None
    capability_gap: Callable[..., Any] | None = None
    specification: Callable[..., Any] | None = None
    development: Callable[..., Any] | None = None


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IntegratedLoopResult:
    """The immutable, auditable outcome of one loop invocation.

    It carries the truthful conclusion, the stage actually reached, the bounded
    next step, EVERY artifact the cycle produced (so provenance and evidence
    survive the whole cycle) and a truthful response. It is also the loop's
    resumable state: handing it back to ``resume`` continues the cycle without
    re-deriving anything.
    """

    status: LoopStatus
    stage: LoopStage
    action: LoopAction
    request: str = ""
    response: str = ""
    reason: str = ""
    knowledge_need: Any = field(default=None, repr=False, compare=False)
    research: Any = field(default=None, repr=False, compare=False)
    provenance: Any = field(default=None, repr=False, compare=False)
    retention: Any = field(default=None, repr=False, compare=False)
    retained: Any = field(default=None, repr=False, compare=False)
    temporal: Any = field(default=None, repr=False, compare=False)
    refresh_requests: tuple[Any, ...] = field(default=(), repr=False, compare=False)
    monitoring: Any = field(default=None, repr=False, compare=False)
    gap: Any = field(default=None, repr=False, compare=False)
    specification: Any = field(default=None, repr=False, compare=False)
    development: Any = field(default=None, repr=False, compare=False)
    proposal_id: str = ""
    approval_request_id: str = ""
    promotion_request_id: str = ""
    evidence: tuple[str, ...] = ()

    @property
    def terminal(self) -> bool:
        """True when no human decision or further input is pending."""
        return self.status in (
            LoopStatus.ANSWERED,
            LoopStatus.REFUSED,
            LoopStatus.NOT_PROMOTABLE,
            LoopStatus.FAILED,
        )

    @property
    def awaiting(self) -> bool:
        """True when the loop is paused at a boundary it may not cross."""
        return self.status in (
            LoopStatus.AWAITING_INPUT,
            LoopStatus.AWAITING_APPROVAL,
            LoopStatus.AWAITING_PROMOTION,
        )

    @property
    def executed(self) -> bool:
        """True once the EXISTING governed development actually ran."""
        return self.stage in (
            LoopStage.IMPLEMENTATION,
            LoopStage.VERIFICATION,
            LoopStage.PROMOTION,
        )

    @property
    def verified(self) -> bool:
        """True only when the EXISTING verifier actually reported ``verified``."""
        development = self.development
        return (
            development is not None
            and getattr(development, "verification_status", "") == "verified"
        )

    @property
    def promotable(self) -> bool:
        """True only when verified work reached the promotion boundary."""
        return self.status is LoopStatus.AWAITING_PROMOTION and self.verified

    @property
    def outcome(self) -> str:
        """The bounded outcome token for a truthful response."""
        return self.status.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "stage": self.stage.value,
            "action": self.action.value,
            "request": self.request,
            "response": self.response,
            "reason": self.reason,
            "proposal_id": self.proposal_id,
            "approval_request_id": self.approval_request_id,
            "promotion_request_id": self.promotion_request_id,
            "knowledge_need": _value(getattr(self.knowledge_need, "kind", "")),
            "research": _value(getattr(self.research, "status", "")),
            "capability_gap": _value(getattr(self.gap, "kind", "")),
            "specification": _value(getattr(self.specification, "spec_id", "")),
            "development_stage": _value(getattr(self.development, "stage", "")),
            "evidence": list(self.evidence),
            "terminal": self.terminal,
            "awaiting": self.awaiting,
            "executed": self.executed,
            "verified": self.verified,
            "promotable": self.promotable,
            "integrated_loop_rule": INTEGRATED_LOOP_RULE,
        }


@dataclass
class _State:
    """Internal accumulator for one invocation (the result is immutable)."""

    text: str
    status: LoopStatus = LoopStatus.ANSWERED
    stage: LoopStage = LoopStage.UNDERSTANDING
    action: LoopAction = LoopAction.NONE
    reason: str = ""
    need: Any = None
    research: Any = None
    provenance: Any = None
    retention: Any = None
    retained: Any = None
    temporal: Any = None
    requests: tuple[Any, ...] = ()
    monitoring: Any = None
    gap: Any = None
    specification: Any = None
    development: Any = None
    proposal_id: str = ""
    approval_request_id: str = ""
    promotion_request_id: str = ""
    evidence: list[str] = field(default_factory=list)


def _response_for(state: _State) -> str:
    """A bounded, truthful response derived from what actually happened."""
    status = state.status
    reason = _clean(state.reason, _MAX_REASON_CHARS)
    if status is LoopStatus.AWAITING_INPUT:
        return (
            "A reviewable design exists but carries no implementation, so a "
            "bounded change payload is required before development can be prepared."
        )
    if status is LoopStatus.AWAITING_APPROVAL:
        return (
            f"Development proposal {state.proposal_id or 'unknown'} was prepared from "
            "the specification and is awaiting OWNER approval; nothing was executed."
        )
    if status is LoopStatus.AWAITING_PROMOTION:
        if state.promotion_request_id:
            return (
                "The change was verified inside the sandbox and a promotion review was "
                "opened; promotion remains an explicit OWNER decision."
            )
        return (
            "The change was verified inside the sandbox; promotion remains an explicit "
            "OWNER decision."
        )
    if status is LoopStatus.NOT_PROMOTABLE:
        return f"The change was not promoted because it did not verify: {reason}"
    if status is LoopStatus.REFUSED:
        return f"The loop cannot proceed: {reason}"
    if status is LoopStatus.FAILED:
        return f"The loop failed closed at the {state.stage.value} stage: {reason}"

    gap = state.gap
    kind = _value(getattr(gap, "kind", ""))
    if kind == CapabilityGapKind.SUPPORTED.value:
        capability = _clean(getattr(gap, "capability", ""), 80)
        return (
            f"The request is supported by the existing capability"
            f"{f' {capability}' if capability else ''}; no development is required."
        )
    if kind == CapabilityGapKind.MISSING_KNOWLEDGE.value:
        return (
            "The request needs knowledge that is not currently established, so no "
            "capability claim is made; evidence or an authorized source is required."
        )
    if kind == CapabilityGapKind.TEMPORARILY_BLOCKED.value:
        return (
            "The capability exists but is currently unavailable, so nothing was "
            "developed or claimed."
        )
    if kind == CapabilityGapKind.GOVERNED.value:
        return (
            "The request is stopped by a governance boundary, so no development was "
            "prepared."
        )
    if kind == CapabilityGapKind.AMBIGUOUS.value:
        return "The request is ambiguous, so the loop stopped rather than guessing."
    if kind == CapabilityGapKind.EXECUTION_FAILURE.value:
        return (
            "The last execution of this request failed, so the loop reports the "
            "failure rather than a capability conclusion."
        )
    return (
        "The available evidence is insufficient to conclude anything about this "
        "request, so the loop makes no claim."
    )


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


class IntegratedIntelligenceLoop:
    """Compose the EXISTING post-L10 capabilities into one governed cycle.

    The loop owns NO capability: every stage calls an injected seam and routes
    on that seam's own typed result. It never approves, authorizes, promotes,
    refreshes without an explicit request, or writes to the live repository.
    """

    def __init__(self, *, seams: LoopSeams | None = None) -> None:
        self._seams = seams or LoopSeams()

    # -- entry points ------------------------------------------------------

    def run(
        self,
        request: Any,
        *,
        candidate_urls: Any = (),
        capability: str = "",
        ambiguous: bool = False,
        execution_failed: bool = False,
        code_changes: Any = (),
        test_files: Any = (),
        target_components: Any = (),
        evidence_ids: Any = (),
        authorization: Any = None,
        refresh: bool = False,
    ) -> IntegratedLoopResult:
        """Run ONE bounded pass of the integrated loop.

        ``refresh`` is the caller's EXPLICIT request to act on a stale-knowledge
        finding through the EXISTING governed refresh; it defaults to ``False``,
        so monitoring observes and reports without fetching anything.
        """
        text = _clean(request, _MAX_REQUEST_CHARS)
        if not text:
            return IntegratedLoopResult(
                status=LoopStatus.REFUSED,
                stage=LoopStage.UNDERSTANDING,
                action=LoopAction.NONE,
                request="",
                reason="a non-empty request is required (fail-closed)",
                response="The loop cannot proceed: a non-empty request is required.",
            )
        urls = _strings(candidate_urls)
        state = _State(text=text)

        # 1. UNDERSTANDING — the EXISTING classifier decides whether any
        #    knowledge work is required at all.
        need, error = self._call(
            "knowledge_need", self._seams.knowledge_need, text, capability=capability
        )
        if error:
            return self._failed(state, LoopStage.UNDERSTANDING, error)
        state.need = need
        kind = _value(getattr(need, "kind", ""))
        need_status = _value(getattr(need, "status", ""))
        state.evidence.append(
            f"knowledge need: {kind or 'unknown'} / {need_status or 'unknown'}"
        )

        # 2. KNOWLEDGE — research only when the classifier says it is actionable;
        #    then the EXISTING provenance/retention/temporal/refresh/monitoring
        #    stages describe what is actually known.
        if kind in _RESEARCH_ENTRY:
            state.stage = LoopStage.RESEARCH
            outcome, error = self._call(
                "research", self._seams.research, text, candidate_urls=urls
            )
            if error:
                return self._failed(state, LoopStage.RESEARCH, error)
            state.research = outcome
            research_status = _value(getattr(outcome, "status", ""))
            state.evidence.append(
                f"research: {research_status or 'unknown'} "
                f"({_value(getattr(outcome, 'mechanism', '')) or 'none'})"
            )
            if research_status in _EVALUATE_AFTER_RESEARCH:
                stopped = self._evaluate_knowledge(
                    state, outcome=outcome, urls=urls, refresh=refresh
                )
                if stopped:
                    return stopped
            else:
                state.action = _RESEARCH_ACTIONS.get(
                    research_status, LoopAction.PROVIDE_EVIDENCE
                )
                state.reason = _RESEARCH_REASONS.get(
                    research_status, "the knowledge step could not be completed"
                )
        elif kind in _NO_KNOWLEDGE_WORK or need_status == (
            KnowledgeNeedStatus.SATISFIED.value
        ):
            stopped = self._evaluate_knowledge(
                state, outcome=None, urls=urls, refresh=refresh
            )
            if stopped:
                return stopped
        else:
            state.action = _KNOWLEDGE_ACTIONS.get(kind, LoopAction.PROVIDE_EVIDENCE)

        # 3. CAPABILITY — the EXISTING adjudicator decides whether a GENUINE gap
        #    remains after everything the knowledge stages established.
        state.stage = LoopStage.CAPABILITY
        gap, error = self._call(
            "capability_gap",
            self._seams.capability_gap,
            text,
            capability=capability,
            ambiguous=ambiguous,
            execution_failed=execution_failed,
        )
        if error:
            return self._failed(state, LoopStage.CAPABILITY, error)
        state.gap = gap
        gap_kind = _value(getattr(gap, "kind", ""))
        state.evidence.append(
            f"capability assessment: {gap_kind or 'unknown'} "
            f"({_value(getattr(gap, 'boundary', '')) or 'none'})"
        )
        if gap_kind != CapabilityGapKind.UNSUPPORTED_CAPABILITY.value:
            state.status = LoopStatus.ANSWERED
            state.action = _resolve_action(
                state.action,
                _GAP_ACTIONS.get(gap_kind, LoopAction.PROVIDE_EVIDENCE),
                gap_kind
                in (
                    CapabilityGapKind.MISSING_KNOWLEDGE.value,
                    CapabilityGapKind.UNKNOWN.value,
                ),
            )
            state.reason = _clean(getattr(gap, "reason", ""), _MAX_REASON_CHARS)
            return self._finish(state)

        # 4. SPECIFICATION — only a CONFIRMED genuine gap is designed.
        state.stage = LoopStage.SPECIFICATION
        specification, error = self._call(
            "specification",
            self._seams.specification,
            text,
            capability=capability,
            ambiguous=ambiguous,
            execution_failed=execution_failed,
        )
        if error:
            return self._failed(state, LoopStage.SPECIFICATION, error)
        state.specification = specification
        spec_status = _value(getattr(specification, "status", ""))
        spec_id = _clean(getattr(specification, "spec_id", ""), 128) or "none"
        state.evidence.append(f"specification: {spec_id} {spec_status or 'unknown'}")
        if spec_status != SpecificationStatus.SPECIFIED.value:
            state.status = LoopStatus.REFUSED
            state.action = LoopAction.REVISE_DESIGN
            state.reason = _clean(
                getattr(specification, "reason", ""), _MAX_REASON_CHARS
            ) or "the specification was refused"
            return self._finish(state)

        # 5. DEVELOPMENT — the design carries no implementation, so the loop
        #    needs the caller's bounded change payload before it may prepare one.
        payload = _pairs(code_changes) + _pairs(test_files)
        if not payload:
            state.stage = LoopStage.PLANNING
            state.status = LoopStatus.AWAITING_INPUT
            state.action = LoopAction.PROVIDE_CHANGE_PAYLOAD
            state.reason = (
                "the specification states what the capability is for but carries no "
                "implementation, so a bounded change payload is required"
            )
            return self._finish(state)

        return self._develop(
            state,
            specification,
            urls=urls,
            proposal_id="",
            authorization=authorization,
            code_changes=code_changes,
            test_files=test_files,
            target_components=target_components,
            evidence_ids=evidence_ids,
        )

    def resume(
        self,
        prior: Any,
        *,
        authorization: Any = None,
        code_changes: Any = (),
        test_files: Any = (),
        target_components: Any = (),
        evidence_ids: Any = (),
        candidate_urls: Any = (),
        refresh: bool = False,
    ) -> IntegratedLoopResult:
        """Continue an interrupted loop from its PRESERVED state.

        The completed prefix (knowledge, capability, specification) is taken from
        ``prior`` verbatim — it is never re-derived — and only the development
        stage runs again, through the EXISTING bridge, against the SAME persisted
        proposal. A human approval therefore interrupts and resumes the loop
        without losing state, and resuming without the required authorization is a
        deterministic no-op.
        """
        if not isinstance(prior, IntegratedLoopResult):
            return IntegratedLoopResult(
                status=LoopStatus.REFUSED,
                stage=LoopStage.UNDERSTANDING,
                action=LoopAction.NONE,
                reason="no loop state was supplied to resume (fail-closed)",
                response=(
                    "The loop cannot resume: no preserved loop state was supplied."
                ),
            )
        if prior.status is LoopStatus.AWAITING_PROMOTION:
            return replace(
                prior,
                status=LoopStatus.REFUSED,
                action=LoopAction.OWNER_PROMOTION,
                reason=(
                    "the loop already reached the promotion boundary; promotion is a "
                    "separate OWNER decision"
                ),
                response=(
                    "The loop already reached the promotion boundary; promotion "
                    "remains an explicit OWNER decision."
                ),
            )
        if prior.status not in _RESUMABLE:
            return replace(
                prior,
                status=LoopStatus.REFUSED,
                action=LoopAction.NONE,
                reason=(
                    f"the loop is not at a resumable boundary (status "
                    f"{prior.status.value!r})"
                ),
                response=(
                    "The loop cannot resume: it is not paused at a boundary that a "
                    "human can continue."
                ),
            )

        state = _state_from(prior)
        specification = prior.specification
        if prior.status is LoopStatus.AWAITING_INPUT:
            if not (_pairs(code_changes) + _pairs(test_files)):
                return self._finish(state)  # still awaiting the same bounded input
            return self._develop(
                state,
                specification,
                urls=_strings(candidate_urls),
                proposal_id="",
                authorization=authorization,
                code_changes=code_changes,
                test_files=test_files,
                target_components=target_components,
                evidence_ids=evidence_ids,
            )
        # AWAITING_APPROVAL: continue against the SAME preserved proposal.
        return self._develop(
            state,
            specification,
            urls=_strings(candidate_urls),
            proposal_id=prior.proposal_id,
            authorization=authorization,
            code_changes=code_changes,
            test_files=test_files,
            target_components=target_components,
            evidence_ids=evidence_ids,
        )

    # -- stages ------------------------------------------------------------

    def _evaluate_knowledge(
        self,
        state: _State,
        *,
        outcome: Any,
        urls: tuple[str, ...],
        refresh: bool,
    ) -> IntegratedLoopResult | None:
        """Describe what is actually known (Steps 17-21). Returns an error result."""
        if outcome is not None:
            state.stage = LoopStage.PROVENANCE
            provenance, error = self._call(
                "provenance", self._seams.provenance, outcome
            )
            if error:
                return self._failed(state, LoopStage.PROVENANCE, error)
            state.provenance = provenance
            state.evidence.append(
                f"provenance: {len(getattr(provenance, 'claims', ()) or ())} claims, "
                f"{len(getattr(provenance, 'sources', ()) or ())} sources"
            )
            state.stage = LoopStage.RETENTION
            retention, error = self._call("retention", self._seams.retention, outcome)
            if error:
                return self._failed(state, LoopStage.RETENTION, error)
            state.retention = retention
            state.evidence.append(
                f"retention: {len(getattr(retention, 'records', ()) or ())} retained, "
                f"{len(getattr(retention, 'refused', ()) or ())} refused"
            )

        state.stage = LoopStage.RETENTION
        retained, error = self._call("retained", self._seams.retained, state.text)
        if error:
            return self._failed(state, LoopStage.RETENTION, error)
        state.retained = retained
        state.evidence.append(
            "retained knowledge: "
            f"{_value(getattr(retained, 'status', '')) or 'unknown'} "
            f"({len(getattr(retained, 'records', ()) or ())} records)"
        )

        state.stage = LoopStage.TEMPORAL
        temporal, error = self._call("temporal", self._seams.temporal, state.text)
        if error:
            return self._failed(state, LoopStage.TEMPORAL, error)
        state.temporal = temporal
        state.evidence.append(
            f"temporal: {_value(getattr(temporal, 'status', '')) or 'unknown'} "
            f"({len(getattr(temporal, 'entries', ()) or ())} entries)"
        )

        state.stage = LoopStage.REFRESH
        requests, error = self._call(
            "refresh_requests", self._seams.refresh_requests, state.text
        )
        if error:
            return self._failed(state, LoopStage.REFRESH, error)
        state.requests = tuple(requests or ())
        required = [
            item for item in state.requests if bool(getattr(item, "required", False))
        ]
        state.evidence.append(
            f"refresh: {len(required)} required of {len(state.requests)}"
        )
        if required and refresh:
            refreshed, error = self._call(
                "refresh", self._seams.refresh, state.text, candidate_urls=urls
            )
            if error:
                return self._failed(state, LoopStage.REFRESH, error)
            outcomes = tuple(getattr(refreshed, "outcomes", ()) or ())
            state.evidence.append(
                "refresh outcomes: "
                + ", ".join(
                    f"{_value(getattr(item, 'status', '')) or 'unknown'}"
                    for item in outcomes
                )
            )
        elif required:
            # Observing only: the loop never authorizes a source or fetches by
            # itself, so a stale-knowledge finding is reported to the caller.
            state.action = LoopAction.AUTHORIZE_SOURCE
            state.reason = (
                "retained knowledge is reported as requiring refresh; acting on it "
                "needs an authorized source"
            )

        state.stage = LoopStage.MONITORING
        monitoring, error = self._call("monitoring", self._seams.monitoring, state.text)
        if error:
            return self._failed(state, LoopStage.MONITORING, error)
        state.monitoring = monitoring
        state.evidence.append(
            f"monitoring: {_value(getattr(monitoring, 'status', '')) or 'unknown'} "
            f"({len(getattr(monitoring, 'observations', ()) or ())} observations)"
        )
        return None

    def _develop(
        self,
        state: _State,
        specification: Any,
        *,
        urls: tuple[str, ...],
        proposal_id: str,
        authorization: Any,
        code_changes: Any,
        test_files: Any,
        target_components: Any,
        evidence_ids: Any,
    ) -> IntegratedLoopResult:
        """Run the EXISTING governed development bridge and map its stage."""
        state.stage = LoopStage.PLANNING
        development, error = self._call(
            "development",
            self._seams.development,
            specification,
            proposal_id=proposal_id,
            authorization=authorization,
            code_changes=_pairs(code_changes),
            test_files=_pairs(test_files),
            target_components=_strings(target_components),
            evidence_ids=_strings(evidence_ids),
        )
        if error:
            return self._failed(state, LoopStage.PLANNING, error)
        state.development = development
        development_stage = _value(getattr(development, "stage", ""))
        state.proposal_id = _clean(getattr(development, "proposal_id", ""), 128)
        state.approval_request_id = _clean(
            getattr(development, "approval_request_id", ""), 128
        )
        state.promotion_request_id = _clean(
            getattr(development, "promotion_request_id", ""), 128
        )
        state.evidence.append(
            f"development: {development_stage or 'unknown'}"
            + (f" proposal={state.proposal_id}" if state.proposal_id else "")
        )
        verification = _value(getattr(development, "verification_status", ""))
        if verification:
            state.evidence.append(f"verification: {verification}")
        for line in tuple(getattr(development, "evidence", ()) or ())[:3]:
            text = _clean(line, _MAX_TEXT_CHARS)
            if text and text not in state.evidence:
                state.evidence.append(text)

        route = _DEVELOPMENT_ROUTES.get(development_stage)
        if route is None:
            return self._failed(
                state,
                LoopStage.PLANNING,
                f"unrecognised development stage {development_stage or 'unknown'!r} "
                "(fail-closed)",
            )
        state.stage, state.status, state.action = route
        reasons = tuple(getattr(development, "reasons", ()) or ())
        if reasons:
            state.reason = _clean("; ".join(str(item) for item in reasons[:2]), 300)
        return self._finish(state)

    # -- helpers -----------------------------------------------------------

    def _call(self, name: str, seam: Any, *args: Any, **kwargs: Any):
        """Call one seam, converting any failure into a bounded reason."""
        if seam is None:
            return None, f"the {name} capability is not wired (fail-closed)"
        try:
            return seam(*args, **kwargs), ""
        except Exception as exc:  # fail-closed: no stage may crash the loop
            return None, f"the {name} stage failed closed ({type(exc).__name__})"

    def _failed(
        self, state: _State, stage: LoopStage, reason: str
    ) -> IntegratedLoopResult:
        state.stage = stage
        state.status = LoopStatus.FAILED
        state.action = LoopAction.ADDRESS_FAILURE
        state.reason = reason
        return self._finish(state)

    def _finish(self, state: _State) -> IntegratedLoopResult:
        recorded: list[str] = []
        for line in state.evidence:
            text = _clean(line, _MAX_TEXT_CHARS)
            if text and text not in recorded:
                recorded.append(text)
        return IntegratedLoopResult(
            status=state.status,
            stage=state.stage,
            action=state.action,
            request=state.text,
            response=_response_for(state),
            reason=_clean(state.reason, _MAX_REASON_CHARS),
            knowledge_need=state.need,
            research=state.research,
            provenance=state.provenance,
            retention=state.retention,
            retained=state.retained,
            temporal=state.temporal,
            refresh_requests=state.requests,
            monitoring=state.monitoring,
            gap=state.gap,
            specification=state.specification,
            development=state.development,
            proposal_id=state.proposal_id,
            approval_request_id=state.approval_request_id,
            promotion_request_id=state.promotion_request_id,
            evidence=tuple(recorded[:_MAX_EVIDENCE_LINES]),
        )


def _state_from(prior: IntegratedLoopResult) -> _State:
    """Restore the preserved prefix of an interrupted loop (no re-derivation)."""
    return _State(
        text=prior.request,
        status=prior.status,
        stage=prior.stage,
        action=prior.action,
        reason=prior.reason,
        need=prior.knowledge_need,
        research=prior.research,
        provenance=prior.provenance,
        retention=prior.retention,
        retained=prior.retained,
        temporal=prior.temporal,
        requests=tuple(prior.refresh_requests or ()),
        monitoring=prior.monitoring,
        gap=prior.gap,
        specification=prior.specification,
        development=prior.development,
        proposal_id=prior.proposal_id,
        approval_request_id=prior.approval_request_id,
        promotion_request_id=prior.promotion_request_id,
        evidence=list(prior.evidence),
    )


def integrated_intelligence_loop(*, seams: LoopSeams | None = None):
    """Convenience constructor for :class:`IntegratedIntelligenceLoop`."""
    return IntegratedIntelligenceLoop(seams=seams)


__all__ = [
    "INTEGRATED_LOOP_RULE",
    "IntegratedIntelligenceLoop",
    "IntegratedLoopResult",
    "LoopAction",
    "LoopSeams",
    "LoopStage",
    "LoopStatus",
    "integrated_intelligence_loop",
]
