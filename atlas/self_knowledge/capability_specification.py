"""Atlas Self-Knowledge — Capability Specification & Development Design (Step 23).

A bounded, deterministic, model-free layer that turns a CONFIRMED Step 22
capability gap into a structured, reviewable capability specification: what the
capability is for, the operations it implies, what it depends on, which existing
architecture areas it touches, the constraints and governance boundary it must
respect, the verification it must satisfy, and — explicitly — which parts of the
design are established by evidence and which are still unresolved questions.

It is NOT an implementation engine. Nothing is generated, written, approved,
authorized, executed or promoted here, no repository is touched, and no model is
consulted: the output is a reviewable design artifact for a human and for the
later implementation step.

Reuse, not reinvention:

* the gap is the EXISTING Step 22 ``CapabilityGap`` (only a genuine
  ``unsupported_capability`` gap is accepted);
* the advisory design skeleton (mechanism, prerequisites, verification
  requirements, failure conditions) is the EXISTING
  ``atlas.evolution.capability_acquisition.AcquisitionStrategy``;
* the affected architecture areas and dependencies come from the EXISTING
  ``ArchitectureModel`` (its ``locate()``, component entries and their declared
  dependencies);
* the constraints include the architecture model's OWN stated scope boundaries,
  and the governance requirements are the EXISTING governance boundaries.

Design guarantees:

* **Grounded input only.** A specification is produced ONLY for a genuine,
  evidence-backed gap with a non-empty request; every other kind is REFUSED with
  a reason naming what the request actually is (supported capability, temporary
  unavailability, governance boundary, knowledge need, ambiguity, execution
  failure, insufficient evidence). Missing knowledge, temporary blocks and
  ambiguity are never treated as development targets.
* **Known vs unresolved.** ``known_facts`` carries exactly what the evidence
  establishes; ``unresolved_questions`` carries what the current architecture
  cannot justify; ``options`` records bounded alternative design choices instead
  of silently selecting one. Nothing is invented to fill a field.
* **Provenance preserved.** The originating gap's kind, boundary, capability,
  reason and evidence are carried verbatim.
* **Bounded, immutable, deterministic and fail-closed.** Every field is
  length-capped and every collection is capped; the objects are frozen; the same
  inputs always produce the same artifact; insufficient input refuses rather than
  guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from atlas.self_knowledge.capability_gap import CapabilityGapKind

#: Bounds (a malformed gap can never produce unbounded output).
_MAX_TEXT_CHARS: int = 300
_MAX_REASON_CHARS: int = 300
_MAX_ITEMS: int = 8
_MAX_EVIDENCE: int = 8
_MAX_TOKENS: int = 6

#: The specification rule, stated once so callers can report it verbatim.
SPECIFICATION_RULE: str = (
    "A capability specification is produced only for a confirmed genuine "
    "capability gap. It states what the evidence establishes, what remains "
    "unresolved, and which alternatives exist; it never generates an "
    "implementation, and it grants no authority."
)

#: The fixed governance invariants every specification must respect (the
#: codebase-wide boundaries, not new ones invented here).
_GOVERNANCE_INVARIANTS: tuple[str, ...] = (
    "any change requires the existing OWNER approval boundary",
    "development is sandbox-only; promotion stays OWNER-only",
)


class SpecificationStatus(str, Enum):
    """Outcome of a specification attempt (closed set)."""

    SPECIFIED = "specified"
    REFUSED = "refused"


#: Why a non-gap input is refused, per the EXISTING Step 22 kind.
_REFUSAL_REASONS: dict[str, str] = {
    CapabilityGapKind.SUPPORTED.value: (
        "an existing capability can handle this request, so no development "
        "design is needed"
    ),
    CapabilityGapKind.TEMPORARILY_BLOCKED.value: (
        "the capability exists but is temporarily unavailable or blocked; "
        "unavailability is not a design target"
    ),
    CapabilityGapKind.GOVERNED.value: (
        "the capability exists behind the existing governance boundary; "
        "authorization, not design, is what is required"
    ),
    CapabilityGapKind.MISSING_KNOWLEDGE.value: (
        "the gap is knowledge, not capability; bounded research precedes any "
        "design and no design is drafted here"
    ),
    CapabilityGapKind.AMBIGUOUS.value: (
        "the request is ambiguous; clarification precedes any design"
    ),
    CapabilityGapKind.EXECUTION_FAILURE.value: (
        "a recorded execution failure of an existing capability is not a "
        "capability absence, so no design is drafted"
    ),
    CapabilityGapKind.UNKNOWN.value: (
        "insufficient evidence to establish a capability boundary, so no design "
        "is drafted (fail-closed)"
    ),
}


@dataclass(frozen=True, slots=True)
class CapabilitySpecification:
    """A bounded, reviewable capability specification (immutable).

    ``status`` is ``specified`` only for a confirmed genuine gap; otherwise the
    artifact is a refusal carrying ``reason`` and the originating gap's evidence.
    """

    spec_id: str
    status: SpecificationStatus
    capability: str = ""
    request: str = ""
    purpose: str = ""
    operations: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    affected_areas: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    governance: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()
    mechanism: str = ""
    prerequisites: tuple[str, ...] = ()
    failure_conditions: tuple[str, ...] = ()
    known_facts: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    gap_kind: str = ""
    gap_boundary: str = ""
    gap_reason: str = ""
    evidence: tuple[str, ...] = ()
    reason: str = ""

    @property
    def is_specified(self) -> bool:
        """True only when a reviewable design was actually produced."""
        return self.status is SpecificationStatus.SPECIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "status": self.status.value,
            "capability": self.capability,
            "request": self.request,
            "purpose": self.purpose,
            "operations": list(self.operations),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "dependencies": list(self.dependencies),
            "affected_areas": list(self.affected_areas),
            "constraints": list(self.constraints),
            "governance": list(self.governance),
            "verification": list(self.verification),
            "mechanism": self.mechanism,
            "prerequisites": list(self.prerequisites),
            "failure_conditions": list(self.failure_conditions),
            "known_facts": list(self.known_facts),
            "unresolved_questions": list(self.unresolved_questions),
            "options": list(self.options),
            "gap_kind": self.gap_kind,
            "gap_boundary": self.gap_boundary,
            "gap_reason": self.gap_reason,
            "evidence": list(self.evidence),
            "reason": self.reason,
            "is_specified": self.is_specified,
            "specification_rule": SPECIFICATION_RULE,
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


def _strings(values: Any, limit: int = _MAX_ITEMS, width: int = 160) -> tuple[str, ...]:
    if not values:
        return ()
    try:
        items = list(values)
    except TypeError:
        return ()
    out: list[str] = []
    for item in items:
        text = _clean(item, width)
        if text and text not in out:
            out.append(text)
    return tuple(out[:limit])


def _tokens(text: str) -> tuple[str, ...]:
    """The EXISTING significant-token helper, with a bounded local fallback."""
    try:
        from atlas.research._text import significant_tokens

        tokens = tuple(sorted(significant_tokens(text)))
    except Exception:  # pragma: no cover - defensive
        tokens = tuple(
            sorted(
                {
                    token
                    for token in _clean(text, 400).lower().split()
                    if len(token) >= 3
                }
            )
        )
    return tuple(token for token in tokens if len(token) >= 3)[:_MAX_TOKENS]


def _slug(request: str) -> str:
    """A provisional capability name derived from the request's own vocabulary."""
    tokens = _tokens(request)
    return "_".join(tokens[:4]) if tokens else "unnamed_capability"


def _refuse(gap: Any, kind: str, reason: str, *, evidence: tuple[str, ...] = ()) -> CapabilitySpecification:
    request = _clean(getattr(gap, "request", ""))
    capability = _clean(getattr(gap, "capability", ""), 120)
    return CapabilitySpecification(
        spec_id=f"spec:{_clean(getattr(gap, 'request', ''), 60) or 'none'}:refused",
        status=SpecificationStatus.REFUSED,
        capability=capability,
        request=request,
        gap_kind=kind,
        gap_boundary=_clean(getattr(gap, "boundary", ""), 40),
        gap_reason=_clean(getattr(gap, "reason", ""), _MAX_REASON_CHARS),
        evidence=tuple(evidence)[:_MAX_EVIDENCE],
        reason=_clean(reason, _MAX_REASON_CHARS),
    )


def _architecture_grounding(
    tokens: tuple[str, ...], architecture_model: Any
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """``(affected_areas, dependencies, candidate packages)`` from the model.

    Uses the EXISTING ``ArchitectureModel.locate()`` and component entries; an
    unresolved token contributes nothing (never guessed).
    """
    if architecture_model is None or not tokens:
        return (), (), ()
    locate = getattr(architecture_model, "locate", None)
    if not callable(locate):
        return (), (), ()
    components = {
        _clean(getattr(entry, "name", ""), 120): entry
        for entry in (getattr(architecture_model, "components", ()) or ())
    }
    areas: list[str] = []
    dependencies: list[str] = []
    packages: list[str] = []
    for token in tokens:
        try:
            result = locate(token)
        except Exception:  # fail-soft: an unlocatable token is left unresolved
            continue
        if not getattr(result, "found", False):
            continue
        for pkg in getattr(result, "packages", ()) or ():
            text = _clean(pkg, 160)
            if text and text not in packages:
                packages.append(text)
        for module in getattr(result, "module_paths", ()) or ():
            text = _clean(module, 200)
            if text and text not in areas:
                areas.append(text)
        if not getattr(result, "module_paths", ()) and getattr(result, "module", ""):
            areas.append(_clean(result.module, 200))
        for name in getattr(result, "components", ()) or ():
            entry = components.get(_clean(name, 120))
            if entry is None:
                continue
            for dep in getattr(entry, "declared_dependencies", ()) or ():
                text = _clean(dep, 120)
                if text and text not in dependencies:
                    dependencies.append(text)
    return (
        tuple(areas[:_MAX_ITEMS]),
        tuple(dependencies[:_MAX_ITEMS]),
        tuple(packages[:_MAX_ITEMS]),
    )


def _advisory(mechanism_source: Any) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """The EXISTING advisory design skeleton: mechanism, prereqs, verification."""
    if mechanism_source is None:
        return "", (), ()
    return (
        _value(getattr(mechanism_source, "mechanism", "")),
        _strings(getattr(mechanism_source, "prerequisites", ()) or ()),
        _strings(getattr(mechanism_source, "validation_required", ()) or ()),
    )


def _strategy_for(gap: Any, capability_model: Any | None) -> Any | None:
    """The EXISTING advisory acquisition strategy for this gap (fail-soft)."""
    try:
        from atlas.evolution.capability_acquisition import (
            AcquisitionNeed,
            determine_acquisition_strategy,
        )
    except Exception:  # pragma: no cover - defensive
        return None
    names = tuple(
        _clean(getattr(entry, "name", ""), 120)
        for entry in (getattr(capability_model, "entries", ()) or ())
    )
    try:
        return determine_acquisition_strategy(
            AcquisitionNeed(
                request=_clean(getattr(gap, "request", "")),
                target_capability=_clean(getattr(gap, "capability", ""), 120)
                or _slug(_clean(getattr(gap, "request", ""))),
                knowledge_available=True,
                authorized=True,
            ),
            capability_names=tuple(name for name in names if name),
        )
    except Exception:  # fail-soft: no advisory skeleton, no invention
        return None


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_capability_specification(
    gap: Any,
    *,
    capability_model: Any | None = None,
    architecture_model: Any | None = None,
) -> CapabilitySpecification:
    """Turn a confirmed GENUINE capability gap into a bounded specification.

    Pure, deterministic and fail-closed: anything that is not a genuine,
    evidence-backed capability gap is REFUSED with a reason, and a design field
    the architecture cannot justify is reported as unresolved rather than filled.
    """
    if gap is None or not isinstance(getattr(gap, "kind", None), CapabilityGapKind):
        return _refuse(
            gap,
            "",
            "no grounded capability gap was supplied, so no design is drafted "
            "(fail-closed)",
        )

    kind = _value(getattr(gap, "kind", ""))
    evidence = _strings(getattr(gap, "evidence", ()) or (), limit=_MAX_EVIDENCE, width=200)
    request = _clean(getattr(gap, "request", ""))

    if kind != CapabilityGapKind.UNSUPPORTED_CAPABILITY.value:
        return _refuse(
            gap,
            kind,
            _REFUSAL_REASONS.get(kind, "the supplied diagnosis is not a capability gap"),
            evidence=evidence,
        )
    if not request:
        return _refuse(
            gap,
            kind,
            "the gap carries no request, so no design can be drafted (fail-closed)",
            evidence=evidence,
        )

    tokens = _tokens(request)
    areas, dependencies, packages = _architecture_grounding(tokens, architecture_model)
    strategy = _strategy_for(gap, capability_model)
    mechanism, prerequisites, verification = _advisory(strategy)
    capability = _clean(getattr(gap, "capability", ""), 120) or _slug(request)

    # Constraints: the architecture model's OWN stated scope boundaries, plus the
    # specification's own (granting nothing).
    constraints: list[str] = []
    knowledge_boundary = getattr(architecture_model, "knowledge_boundary", None)
    for unknown in getattr(knowledge_boundary, "unknown", ()) or ():
        text = _clean(unknown, 200)
        if text and text not in constraints:
            constraints.append(text)
    constraints.append(
        "this specification is a reviewable design only: it generates no "
        "implementation and grants no authority"
    )

    # Governance: the EXISTING governance boundaries plus the fixed invariants.
    governance: list[str] = []
    for boundary in getattr(architecture_model, "governance", ()) or ():
        name = _clean(getattr(boundary, "capability", ""), 120)
        governing = _clean(getattr(boundary, "governing", ""), 60)
        if name and governing:
            text = f"{name}: {governing}"
            if text not in governance:
                governance.append(text)
    governance.extend(_GOVERNANCE_INVARIANTS)

    known: list[str] = []
    if kind == CapabilityGapKind.UNSUPPORTED_CAPABILITY.value:
        known.append(
            "no existing capability covers this request while its subject is "
            "known from validated knowledge"
        )
    if mechanism:
        known.append(f"the existing advisory layer selects the mechanism '{mechanism}'")
    if areas:
        known.append(
            f"{len(areas)} existing architecture area(s) resolve to this request's "
            "vocabulary"
        )
    else:
        known.append(
            "no existing architecture area resolves to this request's vocabulary"
        )
    if constraints:
        known.append(
            f"{len(constraints)} architecture scope boundary(ies) constrain the design"
        )
    known.append(
        f"operations are taken from the request's own vocabulary "
        f"({', '.join(tokens) if tokens else 'none'})"
    )

    unresolved: list[str] = []
    if not areas:
        unresolved.append(
            "the owning architecture area is unresolved: no existing component, "
            "module or package matches the request"
        )
    if not dependencies:
        unresolved.append(
            "required dependencies are unresolved because no affected architecture "
            "area could be located"
        )
    unresolved.append(
        "the exact operation signature (name, arguments, return) is not yet agreed"
    )
    unresolved.append("the capability's inputs and outputs are not yet established")
    unresolved.append(
        "no stable capability id is agreed for this capability"
    )
    if architecture_model is None:
        unresolved.append(
            "no architecture model was available, so the design could not be "
            "grounded in existing components"
        )

    # Alternatives: when the evidence admits more than one host, LIST them rather
    # than silently selecting one.
    options: list[str] = []
    if len(packages) >= 2:
        options = list(packages)
        unresolved.append(
            "more than one candidate host area exists; the alternatives are listed "
            "in 'options' instead of one being chosen"
        )
    elif packages:
        options = [packages[0]]

    # inputs/outputs stay empty: the current architecture cannot justify them.

    return CapabilitySpecification(
        spec_id=f"spec:{capability or 'unnamed'}:{len(evidence)}",
        status=SpecificationStatus.SPECIFIED,
        capability=_clean(capability, 120),
        request=request,
        purpose=request,
        operations=tokens,
        inputs=(),
        outputs=(),
        dependencies=dependencies,
        affected_areas=areas,
        constraints=tuple(constraints[:_MAX_ITEMS]),
        governance=tuple(governance[:_MAX_ITEMS]),
        verification=verification,
        mechanism=mechanism,
        prerequisites=prerequisites,
        failure_conditions=_strings(
            getattr(strategy, "failure_conditions", ()) or ()
        ),
        known_facts=tuple(known[:_MAX_ITEMS]),
        unresolved_questions=tuple(unresolved[:_MAX_ITEMS]),
        options=tuple(options[:_MAX_ITEMS]),
        gap_kind=kind,
        gap_boundary=_clean(getattr(gap, "boundary", ""), 40),
        gap_reason=_clean(getattr(gap, "reason", ""), _MAX_REASON_CHARS),
        evidence=evidence,
    )


def capability_specification(  # convenience alias, mirroring the module name
    gap: Any,
    *,
    capability_model: Any | None = None,
    architecture_model: Any | None = None,
) -> CapabilitySpecification:
    """Convenience alias for :func:`build_capability_specification`."""
    return build_capability_specification(
        gap, capability_model=capability_model, architecture_model=architecture_model
    )


__all__ = [
    "CapabilitySpecification",
    "SPECIFICATION_RULE",
    "SpecificationStatus",
    "build_capability_specification",
    "capability_specification",
]
