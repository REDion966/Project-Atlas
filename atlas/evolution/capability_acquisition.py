"""Atlas Evolution — Capability Acquisition (Phase 8.1–8.2, 8.6).

A bounded, deterministic, model-independent layer that turns a *missing
capability* into a structured acquisition need, classifies it, and selects among
the acquisition mechanisms Atlas ALREADY supports — and validates that an
acquired capability is really present and routable after governed
internalization.

It adds NO executor, planner, registry, knowledge store, or approval path. It is
an ADVISORY strategy layer over the existing architecture:

    capability gap (assess_development_gap)
      -> acquisition need (this module)
      -> acquisition strategy (this module)
      -> existing governed development path
         (DevelopmentPlanner -> SelfDevelopmentLoop sandbox -> DevelopmentVerification
          -> PromotionGate -> CapabilityActivator)

Authorization is never asserted here. A strategy carries the authorization /
validation / failure requirements; the existing governance path enforces them.
Ambiguous or unauthorized needs fail closed (mechanism ``NONE``).

Pure logic: stdlib only. No AI, no network, no storage, no kernel, no execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

_MAX_TEXT_CHARS: int = 400
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class AcquisitionNeedKind(str, Enum):
    """Deterministic classification of an acquisition need (never guessed)."""

    ALREADY_AVAILABLE = "already_available"
    MISSING_CAPABILITY = "missing_capability"
    MISSING_IMPLEMENTATION = "missing_implementation"
    MISSING_KNOWLEDGE = "missing_knowledge"
    UNAVAILABLE_DEPENDENCY = "unavailable_dependency"
    INCOMPATIBLE_DEPENDENCY = "incompatible_dependency"
    UNAUTHORIZED = "unauthorized"
    AMBIGUOUS = "ambiguous"


class AcquisitionMechanism(str, Enum):
    """An acquisition mechanism Atlas genuinely supports."""

    EXISTING_CAPABILITY = "existing_capability"   # already registered capability
    EXISTING_TOOL = "existing_tool"               # already registered tool
    INTERNAL_DEVELOPMENT = "internal_development"  # governed dev path (know-how present)
    RESEARCHED_INTERNALIZATION = "researched_internalization"  # research, then dev
    NONE = "none"                                 # fail closed: cannot acquire


@dataclass(frozen=True, slots=True)
class AcquisitionNeed:
    """Structured description of what is missing and under what constraints.

    The caller populates the facts (it does not infer them from vague text):
    declared dependencies, which of them are reachable, which are incompatible,
    whether design/knowledge exists, and whether acquisition is authorized.
    """

    request: str
    target_capability: str = ""
    required_dependencies: tuple[str, ...] = ()
    available_dependencies: tuple[str, ...] = ()
    incompatible_dependencies: tuple[str, ...] = ()
    knowledge_available: bool | None = None
    authorized: bool = True
    evidence: tuple[str, ...] = ()
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "target_capability": self.target_capability,
            "required_dependencies": list(self.required_dependencies),
            "available_dependencies": list(self.available_dependencies),
            "incompatible_dependencies": list(self.incompatible_dependencies),
            "knowledge_available": self.knowledge_available,
            "authorized": self.authorized,
            "evidence": list(self.evidence),
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class AcquisitionStrategy:
    """Deterministic acquisition strategy (an ADVISORY recommendation)."""

    target_capability: str
    mechanism: AcquisitionMechanism
    kind: AcquisitionNeedKind
    prerequisites: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    authorization_required: bool = True
    validation_required: tuple[str, ...] = ()
    expected_resulting_capability: str = ""
    failure_conditions: tuple[str, ...] = ()
    rationale: str = ""

    @property
    def acquirable(self) -> bool:
        """True only when a concrete, non-blocked mechanism was selected."""
        return self.mechanism is not AcquisitionMechanism.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_capability": self.target_capability,
            "mechanism": self.mechanism.value,
            "kind": self.kind.value,
            "prerequisites": list(self.prerequisites),
            "dependencies": list(self.dependencies),
            "authorization_required": self.authorization_required,
            "validation_required": list(self.validation_required),
            "expected_resulting_capability": self.expected_resulting_capability,
            "failure_conditions": list(self.failure_conditions),
            "rationale": self.rationale,
            "acquirable": self.acquirable,
        }


@dataclass(frozen=True, slots=True)
class AcquisitionValidation:
    """Read-only post-internalization validation result (Phase 8.6)."""

    capability: str
    registered: bool
    routable: bool
    in_model: bool
    ok: bool
    failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "registered": self.registered,
            "routable": self.routable,
            "in_model": self.in_model,
            "ok": self.ok,
            "failures": list(self.failures),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    text = value if isinstance(value, str) else ""
    return " ".join(text.split())[:limit]


def _tokens(text: Any) -> set[str]:
    value = text if isinstance(text, str) else ""
    return set(_TOKEN_RE.findall(value.lower()))


def _matches(target: str, names: Iterable[str]) -> bool:
    target_tokens = _tokens(target)
    if not target_tokens:
        return False
    for name in names or ():
        if not isinstance(name, str) or not name:
            continue
        # A dotted/dashed capability name matches token-wise.
        name_tokens = _tokens(name.replace(".", " ").replace("_", " ").replace("-", " "))
        if name_tokens and name_tokens <= target_tokens:
            return True
    return False


# ---------------------------------------------------------------------------
# 8.1 — Need classification
# ---------------------------------------------------------------------------


def classify_acquisition_need(
    need: AcquisitionNeed,
    *,
    capability_names: Iterable[str] = (),
    tool_names: Iterable[str] = (),
) -> AcquisitionNeedKind:
    """Classify an acquisition need deterministically (fail-closed precedence).

    Order: ambiguous -> already available -> unauthorized -> incompatible
    dependency -> unavailable dependency -> missing implementation (know-how
    present) -> missing knowledge -> missing capability (undetermined).
    """
    if not isinstance(need, AcquisitionNeed):
        return AcquisitionNeedKind.AMBIGUOUS
    if not need.request.strip() or not _tokens(need.request):
        return AcquisitionNeedKind.AMBIGUOUS
    if not need.target_capability.strip():
        return AcquisitionNeedKind.AMBIGUOUS

    if _matches(need.target_capability, capability_names) or _matches(
        need.target_capability, tool_names
    ):
        return AcquisitionNeedKind.ALREADY_AVAILABLE

    if not need.authorized:
        return AcquisitionNeedKind.UNAUTHORIZED
    if tuple(need.incompatible_dependencies):
        return AcquisitionNeedKind.INCOMPATIBLE_DEPENDENCY
    missing = set(map(str, need.required_dependencies)) - set(
        map(str, need.available_dependencies)
    )
    if missing:
        return AcquisitionNeedKind.UNAVAILABLE_DEPENDENCY

    if need.knowledge_available is True:
        return AcquisitionNeedKind.MISSING_IMPLEMENTATION
    if need.knowledge_available is False:
        return AcquisitionNeedKind.MISSING_KNOWLEDGE
    return AcquisitionNeedKind.MISSING_CAPABILITY


# ---------------------------------------------------------------------------
# 8.2 — Strategy determination
# ---------------------------------------------------------------------------

_DEPENDENCY_FAILURES: tuple[str, ...] = (
    "a required dependency is unavailable",
    "dependency must be made available or the need re-scoped",
)
_INCOMPATIBLE_FAILURES: tuple[str, ...] = (
    "a required dependency is incompatible",
    "resolve incompatibility before acquisition",
)
_UNAUTHORIZED_FAILURES: tuple[str, ...] = (
    "acquisition is not authorized",
    "OWNER/authorized approval is required before any acquisition",
)
_AMBIGUOUS_FAILURES: tuple[str, ...] = (
    "acquisition requirement is ambiguous",
    "a bounded target capability is required (clarification needed)",
)


def _development_strategy(
    need: AcquisitionNeed, kind: AcquisitionNeedKind, mechanism: AcquisitionMechanism
) -> AcquisitionStrategy:
    prerequisites = ["authorized development scope", "sandbox available"]
    if mechanism is AcquisitionMechanism.RESEARCHED_INTERNALIZATION:
        prerequisites = ["bounded research evidence", *prerequisites]
    return AcquisitionStrategy(
        target_capability=_bounded(need.target_capability, 200),
        mechanism=mechanism,
        kind=kind,
        prerequisites=tuple(prerequisites),
        dependencies=tuple(sorted(set(map(str, need.required_dependencies)))),
        authorization_required=True,
        validation_required=(
            "DevelopmentVerification",
            "relevant tests selected and executed in the sandbox",
            "capability registry contract validated on activation",
        ),
        expected_resulting_capability=_bounded(need.target_capability, 200),
        failure_conditions=(
            "authorization missing",
            "sandbox violation",
            "implementation/test failure",
            "verification failure",
            "activation contract invalid",
        ),
        rationale=(
            "internal governed development is the authorized mechanism for a "
            f"{kind.value} need"
        ),
    )


def determine_acquisition_strategy(
    need: AcquisitionNeed,
    *,
    capability_names: Iterable[str] = (),
    tool_names: Iterable[str] = (),
) -> AcquisitionStrategy:
    """Select the smallest already-authorized acquisition mechanism (or NONE).

    Never asserts authority: the strategy records the authorization/validation
    requirements that the existing governance path must satisfy.
    """
    kind = classify_acquisition_need(
        need, capability_names=capability_names, tool_names=tool_names
    )
    target = _bounded(need.target_capability, 200)

    if kind is AcquisitionNeedKind.AMBIGUOUS:
        return AcquisitionStrategy(
            target_capability=target,
            mechanism=AcquisitionMechanism.NONE,
            kind=kind,
            authorization_required=True,
            failure_conditions=_AMBIGUOUS_FAILURES,
            rationale="ambiguous acquisition requirements must not execute",
        )

    if kind is AcquisitionNeedKind.ALREADY_AVAILABLE:
        mechanism = (
            AcquisitionMechanism.EXISTING_TOOL
            if _matches(need.target_capability, tool_names)
            else AcquisitionMechanism.EXISTING_CAPABILITY
        )
        return AcquisitionStrategy(
            target_capability=target,
            mechanism=mechanism,
            kind=kind,
            prerequisites=(),
            authorization_required=False,
            validation_required=(),
            expected_resulting_capability=target,
            failure_conditions=(),
            rationale="the capability is already registered; no acquisition needed",
        )

    if kind is AcquisitionNeedKind.UNAUTHORIZED:
        return AcquisitionStrategy(
            target_capability=target,
            mechanism=AcquisitionMechanism.NONE,
            kind=kind,
            authorization_required=True,
            failure_conditions=_UNAUTHORIZED_FAILURES,
            rationale="unauthorized acquisition fails closed",
        )

    if kind is AcquisitionNeedKind.INCOMPATIBLE_DEPENDENCY:
        return AcquisitionStrategy(
            target_capability=target,
            mechanism=AcquisitionMechanism.NONE,
            kind=kind,
            dependencies=tuple(sorted(need.incompatible_dependencies)),
            failure_conditions=_INCOMPATIBLE_FAILURES,
            rationale="an incompatible dependency blocks acquisition",
        )

    if kind is AcquisitionNeedKind.UNAVAILABLE_DEPENDENCY:
        return AcquisitionStrategy(
            target_capability=target,
            mechanism=AcquisitionMechanism.NONE,
            kind=kind,
            dependencies=tuple(sorted(need.required_dependencies)),
            failure_conditions=_DEPENDENCY_FAILURES,
            rationale="an unavailable dependency blocks acquisition",
        )

    if kind is AcquisitionNeedKind.MISSING_IMPLEMENTATION:
        return _development_strategy(
            need, kind, AcquisitionMechanism.INTERNAL_DEVELOPMENT
        )

    # MISSING_KNOWLEDGE or MISSING_CAPABILITY: research first, then internal dev.
    return _development_strategy(
        need, kind, AcquisitionMechanism.RESEARCHED_INTERNALIZATION
    )


# ---------------------------------------------------------------------------
# 8.6 — Post-internalization validation (read-only, reuses existing surfaces)
# ---------------------------------------------------------------------------


def validate_internalized_capability(
    capability: str,
    *,
    capability_registry: Any = None,
    capability_model: Any = None,
) -> AcquisitionValidation:
    """Validate that an acquired capability is really present and routable.

    Read-only. Duck-typed on the existing ``CapabilityRegistry`` (``has``) and
    ``CapabilityModel`` (``entries``). A missing registry fails closed (not
    registered / not routable).
    """
    name = capability if isinstance(capability, str) else ""
    failures: list[str] = []

    registered = False
    if capability_registry is not None and callable(
        getattr(capability_registry, "has", None)
    ):
        try:
            registered = bool(capability_registry.has(name))
        except Exception:
            registered = False
    if not name:
        failures.append("no capability name supplied")
    if not registered:
        failures.append("capability is not registered")

    # A capability is routable only when a handler is registered for it.
    routable = registered

    in_model = True  # not checked when no model is supplied
    entries = getattr(capability_model, "entries", None)
    if entries is not None:
        in_model = any(
            getattr(e, "name", None) == name for e in entries
        )
        if not in_model:
            failures.append("capability is absent from the capability model")

    ok = bool(name) and registered and routable and in_model
    return AcquisitionValidation(
        capability=name,
        registered=registered,
        routable=routable,
        in_model=in_model,
        ok=ok,
        failures=tuple(failures),
    )
