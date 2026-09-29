"""Atlas Self-Knowledge — Capability Gap Adjudicator (Step 22).

A bounded, deterministic, model-free diagnosis that decides whether a request
exposes a GENUINE capability gap, or whether it is instead something else the
existing machinery already explains: a supported capability, a temporarily
unavailable/blocked one, a knowledge need, an ambiguity, a governance boundary,
or an execution failure.

It is NOT a new capability registry, discovery engine or development path. The
base request-level adjudication is the EXISTING
``atlas.evolution.development_gap.assess_development_gap``; the capability state is
the EXISTING unified capability model (Steps 12-13); the knowledge signal is the
EXISTING Step 15 ``KnowledgeNeed``; and the caller may supply the EXISTING grounded
ambiguity (Step 9) and execution-failure outcomes. This module only ADJUDICATES
those grounded signals into one explainable diagnosis.

Design guarantees:

* **Evidence-backed, never "Atlas could not answer".** A gap is reported ONLY when
  the request resolves to no existing capability while the request is not a
  knowledge request, not ambiguous, not governed and not an execution failure.
  Unfamiliar wording, unknown entities, temporary source denial and missing
  knowledge are never capability gaps.
* **Absence is distinguished from unavailability.** A matched capability whose
  grounded state is ``unavailable``/``blocked``/``partially_supported`` is
  ``temporarily_blocked`` (a capability EXISTS), never ``unsupported_capability``.
* **Authorization is not absence.** A matched capability whose state is
  ``governed`` is a governance boundary, not a gap.
* **Failure is not absence.** An execution failure with a matched capability is
  ``execution_failure``, never a capability absence.
* **Fail-closed.** With no grounded capability evidence — a blank request, no
  capability model, or the EXISTING adjudicator's ``unclear`` outcome — the result
  is ``unknown``: the module never claims a gap because evidence is missing.
* **Bounded and immutable.** Every field is length-capped and every collection is
  capped; no AI, no network, no storage write, no authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Bounds (a malformed request can never produce unbounded output).
_MAX_TEXT_CHARS: int = 300
_MAX_REASON_CHARS: int = 300
_MAX_ITEMS: int = 8
_MAX_EVIDENCE: int = 6

#: Grounded capability states (Steps 12-13) that mean the capability EXISTS but
#: cannot currently act — unavailability, never absence.
_BLOCKED_STATES: frozenset[str] = frozenset(
    {"unavailable", "blocked", "partially_supported"}
)
#: Grounded state that means the capability exists behind the OWNER boundary.
_GOVERNED_STATE: str = "governed"

#: The EXISTING request-level adjudication (``atlas.evolution.development_gap``)
#: reconciled into this module's own closed tokens. The mapping is applied from
#: the real enum below, so a renamed value can never be silently mistranslated.
_BASE_SUPPORTED = "supported"
_BASE_MISSING_CAPABILITY = "missing_capability"
_BASE_MISSING_KNOWLEDGE = "missing_knowledge"
_BASE_UNCLEAR = "unclear"

#: The adjudication rule, stated once so callers can report it verbatim.
GAP_RULE: str = (
    "A capability gap is reported only when a request resolves to no existing "
    "capability AND is not a knowledge need, an ambiguity, a governance boundary "
    "or an execution failure. Unavailable/blocked capabilities are unavailability, "
    "not absence, and missing evidence yields 'unknown', never a gap."
)


class CapabilityGapKind(str, Enum):
    """The adjudicated nature of a request (closed set)."""

    SUPPORTED = "supported"
    TEMPORARILY_BLOCKED = "temporarily_blocked"
    MISSING_KNOWLEDGE = "missing_knowledge"
    AMBIGUOUS = "ambiguous"
    GOVERNED = "governed"
    EXECUTION_FAILURE = "execution_failure"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CapabilityGap:
    """One bounded, evidence-backed capability-gap diagnosis (immutable)."""

    kind: CapabilityGapKind
    request: str
    boundary: str = "none"
    capability: str = ""
    capability_state: str = ""
    matched: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    reason: str = ""
    evidence: tuple[str, ...] = ()

    @property
    def is_gap(self) -> bool:
        """True ONLY for a genuine capability absence."""
        return self.kind is CapabilityGapKind.UNSUPPORTED_CAPABILITY

    @property
    def is_supported(self) -> bool:
        """True when an existing capability can handle the request."""
        return self.kind is CapabilityGapKind.SUPPORTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "request": self.request,
            "boundary": self.boundary,
            "capability": self.capability,
            "capability_state": self.capability_state,
            "matched": list(self.matched),
            "requires": list(self.requires),
            "reason": self.reason,
            "evidence": list(self.evidence),
            "is_gap": self.is_gap,
            "is_supported": self.is_supported,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _value(value: Any, limit: int = 48) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return ""
    return _clean(raw, limit)


def _strings(values: Any, limit: int = _MAX_ITEMS) -> tuple[str, ...]:
    if not values:
        return ()
    try:
        items = list(values)
    except TypeError:
        return ()
    out: list[str] = []
    for item in items:
        text = _clean(item, 120)
        if text and text not in out:
            out.append(text)
    return tuple(out[:limit])


def capability_names(model: Any | None) -> tuple[str, ...]:
    """The EXISTING capability names from the unified model (fail-soft)."""
    entries = getattr(model, "entries", None)
    if not entries:
        return ()
    return tuple(
        _strings((getattr(e, "name", "") for e in entries), limit=256)
    )


def _entry_for(model: Any | None, name: str) -> Any | None:
    finder = getattr(model, "find", None)
    if callable(finder):
        try:
            found = finder(name)
        except Exception:
            found = None
        if found is not None:
            return found
    entries = getattr(model, "entries", None) or ()
    for entry in entries:
        if _clean(getattr(entry, "name", ""), 120) == name:
            return entry
    return None


def _state_of(model: Any | None, name: str) -> tuple[str, tuple[str, ...]]:
    """The grounded ``(state, requires)`` of ``name``, or ``("", ())``."""
    entry = _entry_for(model, name)
    if entry is None:
        return "", ()
    state = _value(getattr(entry, "state", ""))
    return state, _strings(getattr(entry, "requires", ()) or ())


def _need_kind(need: Any | None) -> tuple[str, str, str]:
    """The EXISTING Step 15 need's ``(kind, capability, capability_state)``."""
    if need is None:
        return "", "", ""
    if isinstance(need, str):
        return _clean(need, 48).lower(), "", ""
    if isinstance(need, dict):
        return (
            _clean(need.get("kind", ""), 48).lower(),
            _clean(need.get("capability", ""), 120),
            _clean(need.get("capability_state", ""), 48).lower(),
        )
    return (
        _value(getattr(need, "kind", "")),
        _clean(getattr(need, "capability", ""), 120),
        _value(getattr(need, "capability_state", "")),
    )


def _base_mapping() -> dict[str, str]:
    """Reconcile the EXISTING ``DevelopmentGapKind`` values into our tokens."""
    try:
        from atlas.evolution.development_gap import DevelopmentGapKind
    except Exception:  # pragma: no cover - defensive
        return {}
    return {
        DevelopmentGapKind.ALREADY_SUPPORTED.value: _BASE_SUPPORTED,
        DevelopmentGapKind.MISSING_CAPABILITY.value: _BASE_MISSING_CAPABILITY,
        DevelopmentGapKind.MISSING_KNOWLEDGE.value: _BASE_MISSING_KNOWLEDGE,
        DevelopmentGapKind.UNCLEAR.value: _BASE_UNCLEAR,
    }


def _base_kind(
    request: str,
    *,
    capability_model: Any | None,
    knowledge_retriever: Any | None,
    development_gap: Any | None,
) -> tuple[str, tuple[str, ...], str]:
    """The EXISTING request-level adjudication.

    Returns ``(token, matched, raw_existing_kind)`` where ``token`` is one of this
    module's ``_BASE_*`` constants (or ``""`` when no adjudication was available).
    """
    if development_gap is not None:
        raw = _value(getattr(development_gap, "kind", ""))
        matched = _strings(getattr(development_gap, "matched", ()) or ())
        return _base_mapping().get(raw, ""), matched, raw
    try:
        from atlas.evolution.development_gap import assess_development_gap
    except Exception:  # pragma: no cover - defensive
        return "", (), ""
    try:
        assessment = assess_development_gap(
            request,
            capability_names=capability_names(capability_model),
            knowledge_retriever=knowledge_retriever,
        )
    except Exception:  # fail-closed: no evidence, no diagnosis
        return "", (), ""
    raw = _value(getattr(assessment, "kind", ""))
    matched = _strings(getattr(assessment, "matched", ()) or ())
    return _base_mapping().get(raw, ""), matched, raw


def _gap(
    kind: CapabilityGapKind,
    request: str,
    *,
    boundary: str = "none",
    capability: str = "",
    capability_state: str = "",
    matched: tuple[str, ...] = (),
    requires: tuple[str, ...] = (),
    reason: str = "",
    evidence: tuple[str, ...] = (),
) -> CapabilityGap:
    return CapabilityGap(
        kind=kind,
        request=_clean(request),
        boundary=_clean(boundary, 40),
        capability=_clean(capability, 120),
        capability_state=_clean(capability_state, 48).lower(),
        matched=tuple(matched)[:_MAX_ITEMS],
        requires=tuple(requires)[:_MAX_ITEMS],
        reason=_clean(reason, _MAX_REASON_CHARS),
        evidence=tuple(evidence)[:_MAX_EVIDENCE],
    )


# ---------------------------------------------------------------------------
# Adjudication
# ---------------------------------------------------------------------------


def assess_capability_gap(
    request: Any,
    *,
    capability_model: Any | None = None,
    knowledge_retriever: Any | None = None,
    knowledge_need: Any | None = None,
    capability: str = "",
    capability_state: str = "",
    ambiguous: bool = False,
    execution_failed: bool = False,
    development_gap: Any | None = None,
) -> CapabilityGap:
    """Adjudicate a request into one bounded capability diagnosis (never raises).

    Every input is grounded evidence Atlas already holds: the EXISTING
    ``DevelopmentGapAssessment``, the EXISTING unified capability model and its
    per-capability state, the EXISTING Step 15 ``KnowledgeNeed``, and the
    caller-supplied grounded ambiguity / execution-failure outcomes.
    """
    text = _clean(request)
    evidence: list[str] = []

    if not text:
        return _gap(
            CapabilityGapKind.UNKNOWN,
            request,
            reason="empty request: nothing to adjudicate (fail-closed)",
            evidence=("request:empty",),
        )
    if capability_model is None:
        return _gap(
            CapabilityGapKind.UNKNOWN,
            request,
            reason=(
                "no capability model was available, so no capability boundary could "
                "be established (fail-closed)"
            ),
            evidence=("capability_model:absent",),
        )

    base_kind, matched, raw_base = _base_kind(
        text,
        capability_model=capability_model,
        knowledge_retriever=knowledge_retriever,
        development_gap=development_gap,
    )
    need_kind, need_capability, need_state = _need_kind(knowledge_need)
    # A caller may supply the grounded capability boundary directly (the same way
    # Step 15 accepts an explicit capability); it is never inferred from wording.
    if not need_capability and capability:
        need_capability = _clean(capability, 120)
        need_state = _value(capability_state) or _state_of(
            capability_model, need_capability
        )[0]
    if raw_base:
        evidence.append(f"development_gap:{raw_base}")
    if need_kind:
        evidence.append(f"knowledge_need:{need_kind}")

    # 1. Ambiguity is never a capability gap.
    if ambiguous or need_kind == CapabilityGapKind.AMBIGUOUS.value:
        return _gap(
            CapabilityGapKind.AMBIGUOUS,
            text,
            boundary="clarification",
            reason=(
                "the request is ambiguous; clarification is required before any "
                "capability boundary can be established"
            ),
            evidence=tuple(evidence),
        )

    # 2. A matched capability's grounded state decides unavailability vs absence.
    matched_states = [(name, *_state_of(capability_model, name)) for name in matched]
    blocked = next(
        ((n, s, r) for n, s, r in matched_states if s in _BLOCKED_STATES), None
    )
    governed = next(
        ((n, s, r) for n, s, r in matched_states if s == _GOVERNED_STATE), None
    )

    if governed is not None:
        name, state, requires = governed
        return _gap(
            CapabilityGapKind.GOVERNED,
            text,
            boundary="governance",
            capability=name,
            capability_state=state,
            matched=matched,
            requires=requires,
            reason=(
                f"'{name}' exists but is {state}: acting on it requires the existing "
                "OWNER approval boundary, so this is a governance boundary rather "
                "than a missing capability"
            ),
            evidence=tuple(evidence) + (f"capability:{name}={state}",),
        )

    if blocked is not None:
        name, state, requires = blocked
        return _gap(
            CapabilityGapKind.TEMPORARILY_BLOCKED,
            text,
            boundary="matched_capability",
            capability=name,
            capability_state=state,
            matched=matched,
            requires=requires,
            reason=(
                f"'{name}' exists but is currently {state}: this is temporary "
                "unavailability, not an absent capability"
            ),
            evidence=tuple(evidence) + (f"capability:{name}={state}",),
        )

    # 3. A failed execution of a MATCHED capability is never a capability gap.
    if execution_failed and matched:
        name = matched[0]
        state, requires = _state_of(capability_model, name)
        return _gap(
            CapabilityGapKind.EXECUTION_FAILURE,
            text,
            boundary="execution",
            capability=name,
            capability_state=state,
            matched=matched,
            requires=requires,
            reason=(
                f"'{name}' is present and the recorded outcome was an execution "
                "failure: a failed run is not a missing capability"
            ),
            evidence=tuple(evidence) + ("outcome:execution_failed",),
        )

    # 4. A matched, available capability means the request is supported.
    if base_kind == _BASE_SUPPORTED:
        name = matched[0] if matched else ""
        state, requires = _state_of(capability_model, name) if name else ("", ())
        extra = (f"capability:{name}={state or 'unknown'}",) if name else ()
        return _gap(
            CapabilityGapKind.SUPPORTED,
            text,
            boundary="matched_capability",
            capability=name,
            capability_state=state,
            matched=matched,
            requires=requires,
            reason=(
                "the request matches an existing, currently available capability"
                + (f" ('{name}')" if name else "")
            ),
            evidence=tuple(evidence) + extra,
        )

    # 5. An unavailable/blocked capability reported by the knowledge need.
    if need_capability and need_state in _BLOCKED_STATES:
        return _gap(
            CapabilityGapKind.TEMPORARILY_BLOCKED,
            text,
            boundary="matched_capability",
            capability=need_capability,
            capability_state=need_state,
            matched=matched,
            reason=(
                f"'{need_capability}' is {need_state}: the request is limited by "
                "temporary unavailability, not by an absent capability"
            ),
            evidence=tuple(evidence) + (f"capability:{need_capability}={need_state}",),
        )

    # 6. The EXISTING adjudicator says a capability is absent WHILE the subject is
    #    known from validated knowledge: the genuine, evidence-backed gap. This is
    #    the only way a gap is ever claimed — never from "Atlas could not answer".
    if base_kind == _BASE_MISSING_CAPABILITY:
        return _gap(
            CapabilityGapKind.UNSUPPORTED_CAPABILITY,
            text,
            boundary="unresolved_target",
            matched=matched,
            reason=(
                "no existing capability covers this request while its subject is "
                "known from validated knowledge: the capability is genuinely absent"
            ),
            evidence=tuple(evidence),
        )

    # 7. No capability AND no validated knowledge: the EXISTING authority decides
    #    this is a knowledge need (research before capability), never a gap.
    if base_kind == _BASE_MISSING_KNOWLEDGE:
        return _gap(
            CapabilityGapKind.MISSING_KNOWLEDGE,
            text,
            boundary="knowledge",
            capability=need_capability,
            capability_state=need_state,
            matched=matched,
            reason=(
                "no capability matched and no validated knowledge about the "
                "subject exists either: a knowledge need (research/retrieval), not "
                "an established capability gap"
            ),
            evidence=tuple(evidence),
        )

    # 8. Anything else (including the EXISTING adjudicator's 'unclear', or no
    #    adjudication at all) is insufficient evidence: never claim a gap.
    return _gap(
        CapabilityGapKind.UNKNOWN,
        text,
        matched=matched,
        reason=(
            "the available evidence does not establish a capability boundary "
            "(fail-closed): no gap is claimed"
        ),
        evidence=tuple(evidence) or ("evidence:insufficient",),
    )


class CapabilityGapDetector:
    """Convenience detector binding the EXISTING capability/knowledge sources."""

    def __init__(
        self,
        *,
        capability_model_provider: Any | None = None,
        knowledge_retriever: Any | None = None,
        knowledge_need_provider: Any | None = None,
    ) -> None:
        self._capability_model_provider = capability_model_provider
        self._knowledge_retriever = knowledge_retriever
        self._knowledge_need_provider = knowledge_need_provider

    def assess(
        self,
        request: Any,
        *,
        capability: str = "",
        ambiguous: bool = False,
        execution_failed: bool = False,
    ) -> CapabilityGap:
        """Adjudicate ``request`` (never raises, never writes)."""
        model: Any = None
        provider = self._capability_model_provider
        if provider is not None:
            try:
                model = provider()
            except Exception:  # fail-closed: no model, no diagnosis
                model = None
        need: Any = None
        need_provider = self._knowledge_need_provider
        if need_provider is not None:
            try:
                need = need_provider(request)
            except Exception:
                need = None
        return assess_capability_gap(
            request,
            capability_model=model,
            knowledge_retriever=self._knowledge_retriever,
            knowledge_need=need,
            capability=capability,
            ambiguous=ambiguous,
            execution_failed=execution_failed,
        )


def capability_gap_detector(
    *,
    capability_model_provider: Any | None = None,
    knowledge_retriever: Any | None = None,
    knowledge_need_provider: Any | None = None,
) -> CapabilityGapDetector:
    """Convenience constructor for :class:`CapabilityGapDetector`."""
    return CapabilityGapDetector(
        capability_model_provider=capability_model_provider,
        knowledge_retriever=knowledge_retriever,
        knowledge_need_provider=knowledge_need_provider,
    )


__all__ = [
    "CapabilityGap",
    "CapabilityGapDetector",
    "CapabilityGapKind",
    "GAP_RULE",
    "assess_capability_gap",
    "capability_gap_detector",
    "capability_names",
]
