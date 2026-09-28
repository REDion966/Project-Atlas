"""Atlas — Autonomous Knowledge Need Detection (Step 15).

A bounded, deterministic, model-free representation of *what knowledge Atlas
would need* to answer or complete a request, and whether that need is real.

It is NOT a second source of truth: the sufficiency half is the EXISTING
``KnowledgeSufficiency`` decision (``atlas.research.knowledge_decision``), the
acquisition half is the EXISTING ``ExternalAcquisitionStatus``
(``atlas.research.external_acquisition``), and the capability half is the
EXISTING unified capability model (Steps 12-13). This module only CLASSIFIES
that already-computed evidence into one bounded, structured result.

Design guarantees:

* **Deterministic and model-free.** Pure logic over already-computed evidence:
  stdlib only, no AI, no network, no storage, no execution, no authority.
* **Never inferred from wording.** The classifier never inspects the request for
  unfamiliar words; a knowledge need is only ever established from a grounded
  sufficiency decision.
* **Never inferred from an unavailable capability.** An unavailable (or blocked)
  capability is reported as ``UNSUPPORTED_CAPABILITY`` — the gap is capability,
  not knowledge — and is never turned into a knowledge need.
* **Fail-closed.** With no grounded sufficiency evidence the kind and status are
  ``unknown``; ``missing``/``stale``/``insufficient`` are never guessed.
* **Bounded.** Every field is length-capped and the evidence list is short.

Classification (a bounded outcome, not a plan):

* ``none`` — Atlas already holds validated knowledge that covers the request.
* ``missing`` — the request needs information Atlas does not possess.
* ``stale`` — relevant knowledge exists but is not current.
* ``insufficient`` — knowledge exists but does not cover the request.
* ``contradictory`` — material conflicting evidence exists.
* ``unsupported_capability`` — the request is not a knowledge need at all.
* ``ambiguous`` — the request needs clarification before any need is real.
* ``unknown`` — no grounded evidence; the need is not established.

Status (actionability, also bounded):

* ``satisfied`` — no need to act on.
* ``actionable`` — an authorized knowledge/research mechanism obtained evidence,
  so the need can be pursued through it (research itself is NOT performed here).
* ``unsatisfiable`` — no authorized acquisition path (deny-by-default), a failed
  acquisition, or no acquisition mechanism at all.
* ``unknown`` — actionability could not be established.

This step detects and represents only. It performs no acquisition, evaluates no
source, stores/learns nothing, and detects no capability gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Bounds applied so a malformed source cannot produce unbounded output.
_MAX_TEXT_CHARS: int = 400
_MAX_REASON_CHARS: int = 400
_MAX_EVIDENCE_ITEMS: int = 6

#: Recognised sufficiency values (the EXISTING D3 ``KnowledgeSufficiency``).
SUFFICIENCY_SUFFICIENT = "sufficient"
SUFFICIENCY_CONTRADICTORY = "contradictory"
SUFFICIENCY_STALE = "stale"
SUFFICIENCY_INSUFFICIENT = "insufficient"
SUFFICIENCY_UNKNOWN = "unknown"
SUFFICIENCY_UNSUPPORTED = "unsupported"

#: Recognised acquisition values (the EXISTING D2 ``ExternalAcquisitionStatus``).
ACQUISITION_EXISTING = "existing_knowledge"
ACQUISITION_ACQUIRED = "acquired"
ACQUISITION_NO_AUTHORIZED_SOURCE = "no_authorized_source"
ACQUISITION_FAILED = "failed"

#: Capability states (Steps 12-13) that mean the gap is CAPABILITY, not knowledge.
_UNSUPPORTED_CAPABILITY_STATES: frozenset[str] = frozenset({"unavailable", "blocked"})


class KnowledgeNeedKind(str, Enum):
    """What kind of knowledge situation Atlas detected (bounded, closed set)."""

    NONE = "none"
    MISSING = "missing"
    STALE = "stale"
    INSUFFICIENT = "insufficient"
    CONTRADICTORY = "contradictory"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class KnowledgeNeedStatus(str, Enum):
    """Whether the detected need can currently be acted on (bounded, closed)."""

    SATISFIED = "satisfied"
    ACTIONABLE = "actionable"
    UNSATISFIABLE = "unsatisfiable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class KnowledgeNeed:
    """A bounded, structured knowledge-need result (immutable).

    Every field is grounded in evidence Atlas already holds; nothing is
    invented. ``evidence`` carries the short provenance references a later
    (separately authorized) research step could reason about — this object
    authorizes and performs nothing.
    """

    kind: KnowledgeNeedKind
    status: KnowledgeNeedStatus
    objective: str
    query: str = ""
    capability: str = ""
    capability_state: str = ""
    sufficiency: str = ""
    acquisition_status: str = ""
    freshness_required: bool = False
    reason: str = ""
    evidence: tuple[str, ...] = ()

    @property
    def is_need(self) -> bool:
        """True only for a genuine, established knowledge need."""
        return self.kind in (
            KnowledgeNeedKind.MISSING,
            KnowledgeNeedKind.STALE,
            KnowledgeNeedKind.INSUFFICIENT,
            KnowledgeNeedKind.CONTRADICTORY,
        )

    @property
    def is_actionable(self) -> bool:
        """True only when an authorized mechanism is known to be able to act."""
        return self.is_need and self.status is KnowledgeNeedStatus.ACTIONABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status.value,
            "objective": self.objective,
            "query": self.query,
            "capability": self.capability,
            "capability_state": self.capability_state,
            "sufficiency": self.sufficiency,
            "acquisition_status": self.acquisition_status,
            "freshness_required": self.freshness_required,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "is_need": self.is_need,
            "is_actionable": self.is_actionable,
        }


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return text[:limit]


def _value(value: Any) -> str:
    """Normalize an enum (or string) to its lowercased value."""
    raw = getattr(value, "value", value)
    return _clean(raw, 64).lower()


def _need(
    kind: KnowledgeNeedKind,
    status: KnowledgeNeedStatus,
    *,
    objective: str,
    query: str = "",
    capability: str = "",
    capability_state: str = "",
    sufficiency: str = "",
    acquisition_status: str = "",
    freshness_required: bool = False,
    reason: str = "",
    evidence: tuple[str, ...] = (),
) -> KnowledgeNeed:
    return KnowledgeNeed(
        kind=kind,
        status=status,
        objective=_clean(objective),
        query=_clean(query, 200),
        capability=_clean(capability, 64),
        capability_state=_clean(capability_state, 32).lower(),
        sufficiency=sufficiency,
        acquisition_status=acquisition_status,
        freshness_required=bool(freshness_required),
        reason=_clean(reason, _MAX_REASON_CHARS),
        evidence=tuple(evidence)[:_MAX_EVIDENCE_ITEMS],
    )


def _actionability(
    acquisition_status: str, sufficiency: str, capability: str
) -> tuple[KnowledgeNeedStatus, str]:
    """Derive actionability ONLY from the existing D2 acquisition outcome."""
    acquisition = _value(acquisition_status)
    if acquisition in (ACQUISITION_ACQUIRED, ACQUISITION_EXISTING):
        return (
            KnowledgeNeedStatus.ACTIONABLE,
            "An authorized knowledge/research mechanism obtained evidence for "
            f"this request (acquisition: {acquisition}), so the need can be "
            "pursued through the existing mechanism.",
        )
    if acquisition == ACQUISITION_NO_AUTHORIZED_SOURCE:
        return (
            KnowledgeNeedStatus.UNSATISFIABLE,
            "Deny-by-default: no authorized source is configured, so the need "
            "cannot currently be satisfied.",
        )
    if acquisition == ACQUISITION_FAILED:
        return (
            KnowledgeNeedStatus.UNSATISFIABLE,
            "The authorized acquisition mechanism failed closed, so the need "
            "cannot currently be satisfied.",
        )
    return (
        KnowledgeNeedStatus.UNSATISFIABLE,
        "No external acquisition path is available, so the need cannot "
        "currently be satisfied.",
    )


def classify_knowledge_need(
    *,
    objective: str,
    sufficiency: Any = "",
    acquisition_status: Any = "",
    has_evidence: bool = False,
    ambiguous: bool = False,
    freshness_required: bool = False,
    capability: str = "",
    capability_state: Any = "",
    capability_reason: str = "",
) -> KnowledgeNeed:
    """Classify already-computed evidence into a bounded knowledge need.

    Deterministic, model-free and fail-closed. The text is NEVER inspected for
    unfamiliar wording, and an unavailable capability is reported as a
    capability gap rather than a knowledge need.
    """
    value = _value(sufficiency)
    acquisition = _value(acquisition_status)
    state = _value(capability_state)
    capability_name = _clean(capability, 64)

    evidence: list[str] = []
    if value:
        evidence.append(f"knowledge_decision:{value}")
    if acquisition:
        evidence.append(f"acquisition:{acquisition}")
    if capability_name:
        evidence.append(f"capability:{capability_name}={state or 'unknown'}")

    # 1. Ambiguity is never a knowledge need — clarification comes first.
    if ambiguous:
        return _need(
            KnowledgeNeedKind.AMBIGUOUS,
            KnowledgeNeedStatus.UNKNOWN,
            objective=objective,
            capability=capability_name,
            capability_state=state,
            sufficiency=value,
            acquisition_status=acquisition,
            reason=(
                "The request is ambiguous; clarification is required before a "
                "knowledge need can be established."
            ),
            evidence=tuple(evidence),
        )

    # 2. An unavailable/blocked capability is a CAPABILITY gap, not a knowledge
    #    need — a capability is never turned into missing knowledge.
    if capability_name and state in _UNSUPPORTED_CAPABILITY_STATES:
        reason = (
            f"'{capability_name}' is {state}: the request is not answerable from "
            "knowledge because the capability itself is unavailable."
        )
        if _clean(capability_reason):
            reason = f"{reason} {_clean(capability_reason)}"
        return _need(
            KnowledgeNeedKind.UNSUPPORTED_CAPABILITY,
            KnowledgeNeedStatus.UNSATISFIABLE,
            objective=objective,
            capability=capability_name,
            capability_state=state,
            sufficiency=value,
            acquisition_status=acquisition,
            reason=reason,
            evidence=tuple(evidence),
        )

    # 3. Atlas already knows enough. An explicit sufficiency decision outranks
    #    the presence of items (a non-sufficient decision WITH items is reported
    #    as insufficient, never as satisfied).
    if value == SUFFICIENCY_SUFFICIENT or (not value and has_evidence):
        return _need(
            KnowledgeNeedKind.NONE,
            KnowledgeNeedStatus.SATISFIED,
            objective=objective,
            capability=capability_name,
            capability_state=state,
            sufficiency=value or SUFFICIENCY_SUFFICIENT,
            acquisition_status=acquisition,
            freshness_required=freshness_required,
            reason="Atlas already holds knowledge that covers the request.",
            evidence=tuple(evidence),
        )

    # 4. Conflicting material evidence is reported as-is; it is never resolved
    #    or averaged away here.
    if value == SUFFICIENCY_CONTRADICTORY:
        return _need(
            KnowledgeNeedKind.CONTRADICTORY,
            KnowledgeNeedStatus.UNSATISFIABLE,
            objective=objective,
            capability=capability_name,
            capability_state=state,
            sufficiency=value,
            acquisition_status=acquisition,
            freshness_required=freshness_required,
            reason=(
                "Material conflicting evidence exists for this request; the "
                "contradiction is preserved rather than resolved."
            ),
            evidence=tuple(evidence),
        )

    # 5. A genuine need — kind derived from the sufficiency decision only.
    if value == SUFFICIENCY_STALE:
        kind = KnowledgeNeedKind.STALE
        base = (
            "Relevant knowledge exists but is not current for this request "
            "(freshness required)."
        )
    elif value in (SUFFICIENCY_INSUFFICIENT, SUFFICIENCY_UNKNOWN):
        kind = (
            KnowledgeNeedKind.INSUFFICIENT if has_evidence else KnowledgeNeedKind.MISSING
        )
        base = (
            "Knowledge exists but does not cover the request."
            if has_evidence
            else "The request requires information Atlas does not currently possess."
        )
    else:
        # No grounded sufficiency evidence ("" or "unsupported"): fail closed.
        return _need(
            KnowledgeNeedKind.UNKNOWN,
            KnowledgeNeedStatus.UNKNOWN,
            objective=objective,
            capability=capability_name,
            capability_state=state,
            sufficiency=value,
            acquisition_status=acquisition,
            freshness_required=freshness_required,
            reason=(
                "No grounded knowledge-sufficiency evidence is available, so a "
                "knowledge need is not established (fail-closed)."
            ),
            evidence=tuple(evidence),
        )

    status, actionability_reason = _actionability(acquisition, value, capability_name)
    return _need(
        kind,
        status,
        objective=objective,
        capability=capability_name,
        capability_state=state,
        sufficiency=value,
        acquisition_status=acquisition,
        freshness_required=freshness_required,
        reason=f"{base} {actionability_reason}",
        evidence=tuple(evidence),
    )


class KnowledgeNeedDetector:
    """Composes the EXISTING evidence and classifies it (read-only, fail-soft).

    ``capability_model_provider`` and ``knowledge_status_provider`` are the same
    read-only callables the conversation already uses; a failing or missing
    source degrades to the fail-closed ``unknown`` classification rather than
    raising or guessing.
    """

    def __init__(
        self,
        *,
        capability_model_provider: Any | None = None,
        knowledge_status_provider: Any | None = None,
    ) -> None:
        self._capability_model_provider = capability_model_provider
        self._knowledge_status_provider = knowledge_status_provider

    def detect(
        self,
        objective: str,
        *,
        query: str = "",
        capability: str = "",
        ambiguous: bool = False,
    ) -> KnowledgeNeed:
        """Return the bounded knowledge need for ``objective`` (never raises)."""
        text = _clean(objective)
        question = _clean(query, 200) or text
        sufficiency = ""
        acquisition = ""
        has_evidence = False
        answer = self._status(question)
        if answer is not None:
            sufficiency = _value(getattr(answer, "status", ""))
            acquisition = _value(getattr(answer, "acquisition_status", ""))
            has_evidence = bool(
                getattr(answer, "claims", ()) or getattr(answer, "sources", ())
            )
        state = ""
        reason = ""
        if capability:
            entry = self._find_capability(capability)
            if entry is not None:
                state = _value(getattr(entry, "state", ""))
                reason = _clean(getattr(entry, "reason", ""))
        return classify_knowledge_need(
            objective=text,
            sufficiency=sufficiency,
            acquisition_status=acquisition,
            has_evidence=has_evidence,
            ambiguous=ambiguous,
            capability=capability,
            capability_state=state,
            capability_reason=reason,
        )

    # ------------------------------------------------------------------
    # Evidence access (fail-soft, read-only)
    # ------------------------------------------------------------------

    def _status(self, query: str) -> Any | None:
        provider = self._knowledge_status_provider
        if provider is None or not query:
            return None
        try:
            return provider(query)
        except Exception:  # fail closed
            return None

    def _find_capability(self, name: str) -> Any | None:
        provider = self._capability_model_provider
        if provider is None:
            return None
        try:
            model = provider()
        except Exception:  # fail closed
            return None
        finder = getattr(model, "find", None)
        if not callable(finder):
            return None
        try:
            return finder(name)
        except Exception:  # fail closed
            return None


def detect_knowledge_need(
    objective: str,
    *,
    sufficiency: Any = "",
    acquisition_status: Any = "",
    has_evidence: bool = False,
    ambiguous: bool = False,
    freshness_required: bool = False,
    capability: str = "",
    capability_state: Any = "",
    capability_reason: str = "",
) -> KnowledgeNeed:
    """Convenience wrapper: classify already-computed evidence (no providers)."""
    return classify_knowledge_need(
        objective=objective,
        sufficiency=sufficiency,
        acquisition_status=acquisition_status,
        has_evidence=has_evidence,
        ambiguous=ambiguous,
        freshness_required=freshness_required,
        capability=capability,
        capability_state=capability_state,
        capability_reason=capability_reason,
    )


def knowledge_need_detector(
    *,
    capability_model_provider: Any | None = None,
    knowledge_status_provider: Any | None = None,
) -> KnowledgeNeedDetector:
    """Convenience constructor for :class:`KnowledgeNeedDetector`."""
    return KnowledgeNeedDetector(
        capability_model_provider=capability_model_provider,
        knowledge_status_provider=knowledge_status_provider,
    )


__all__ = [
    "KnowledgeNeed",
    "KnowledgeNeedDetector",
    "KnowledgeNeedKind",
    "KnowledgeNeedStatus",
    "classify_knowledge_need",
    "detect_knowledge_need",
    "knowledge_need_detector",
]
