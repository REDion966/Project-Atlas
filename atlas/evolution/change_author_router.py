"""Atlas Evolution — change planning and author routing (STEP 2E/2I).

Adapts the useful architect/editor separation (change REASONING separated from
change AUTHORING) to Atlas's existing contracts. It introduces no second
reasoning system: a :class:`ChangePlan` is a bounded, deterministic DESCRIPTION
of what kind of authoring a ``DevelopmentNeed`` calls for, derived only from
evidence the need already carries.

The :class:`ChangeAuthorRouter` then selects the deterministic author that
matches that route, and consults the optional specialist-model seam LAST, only
when it is explicitly enabled. Routing decides WHO authors — never whether a
change is allowed: every produced change still becomes a ``CodeChangeSet`` and
passes the unchanged validation, sandbox, verification, approval and promotion
boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable

from atlas.evolution.development_cycle import (
    ChangeSupplier,
    DevelopmentNeed,
    DeterministicChangeSupplier,
    SuppliedChanges,
)

#: Bounded planning vocabulary.
MAX_CONSTRAINTS: int = 8
MAX_CONSTRAINT_CHARS: int = 80
MAX_EVIDENCE_CHARS: int = 200

#: Preservation/constraint cues recognized in the need's OWN words. Bounded and
#: closed: it detects that a constraint was STATED, never what it means.
CONSTRAINT_CUES: tuple[str, ...] = (
    "preserve",
    "preserving",
    "without breaking",
    "don't break",
    "do not break",
    "backward compatible",
    "backwards compatible",
    "compatibility",
    "existing interface",
    "public interface",
    "unchanged",
    "no behaviour change",
    "no behavior change",
    "safely",
)


class AuthorRoute(str, Enum):
    """Which EXISTING authoring mechanism a need calls for."""

    #: Caller supplied the exact full-file content (the E5 convention).
    EXPLICIT_PATCH = "explicit_patch"
    #: A localized, AST-anchored edit of an existing module.
    STRUCTURAL = "structural"
    #: A deterministic new-capability scaffold.
    SCAFFOLD = "scaffold"
    #: The evidence/remedy author (e.g. a missing-test remedy).
    EVIDENCE = "evidence"
    #: The OPTIONAL specialist coding provider (never authoritative).
    SPECIALIST_MODEL = "specialist_model"
    #: No author can serve this need with the available evidence.
    UNAVAILABLE = "unavailable"


#: Routing priority. Deterministic routes are tried before the optional model.
ROUTE_PRIORITY: tuple[AuthorRoute, ...] = (
    AuthorRoute.EXPLICIT_PATCH,
    AuthorRoute.STRUCTURAL,
    AuthorRoute.SCAFFOLD,
    AuthorRoute.EVIDENCE,
    AuthorRoute.SPECIALIST_MODEL,
)

#: Metadata key -> route (mirrors the EXISTING disjoint supplier conventions).
_METADATA_ROUTES: tuple[tuple[str, AuthorRoute], ...] = (
    ("code_changes", AuthorRoute.EXPLICIT_PATCH),
    ("structural", AuthorRoute.STRUCTURAL),
    ("scaffold", AuthorRoute.SCAFFOLD),
    ("evidence_change", AuthorRoute.EVIDENCE),
)

#: Bounded verification expectations (never the whole test suite).
MAX_VERIFICATION_TESTS: int = 8


@dataclass(frozen=True, slots=True)
class ChangePlan:
    """A bounded, deterministic plan for one ``DevelopmentNeed``.

    A plan is an EVIDENCE-BACKED SPECIFICATION of the bounded work the request
    describes. It is NOT permission to modify code, NOT a generated patch, and
    NOT an approval.
    """

    target: str = ""
    route: AuthorRoute = AuthorRoute.UNAVAILABLE
    reason: str = ""
    constraints: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    risk: str = "low"
    #: True when the selected route is a DETERMINISTIC author (no model needed).
    deterministic: bool = True
    #: --- localization evidence (STEP: resolved localization -> bounded plan) --
    #: The target's kind (``module`` / ``package`` / ``symbol``), empty when the
    #: plan has no localized target.
    target_kind: str = ""
    #: The QUALIFIED symbol the localization resolved, when one was justified.
    symbol: str = ""
    #: The localization status the plan was derived from (``resolved`` /
    #: ``ambiguous`` / ``unresolved``) — preserved so a non-resolved plan is
    #: never mistaken for an authoritative one.
    localization_status: str = ""
    #: Why the localization selected this target (deterministic reason strings).
    provenance: tuple[str, ...] = ()
    #: Bounded relevant repository context: modules, symbols, tests, dependencies,
    #: dependents. Never the whole repository.
    context: dict[str, Any] = field(default_factory=dict)
    #: Bounded verification expectations — the deterministic evidence a LATER
    #: authored change will be judged by. Never an instruction to execute, never
    #: an approval, and never a patch.
    verification: "VerificationExpectation | None" = None

    @property
    def actionable(self) -> bool:
        return self.route is not AuthorRoute.UNAVAILABLE

    @property
    def localized(self) -> bool:
        """True only for a plan derived from a RESOLVED localization."""
        return self.localization_status == "resolved" and bool(self.target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "target_kind": self.target_kind,
            "symbol": self.symbol,
            "route": self.route.value,
            "reason": self.reason,
            "constraints": list(self.constraints),
            "evidence": list(self.evidence),
            "provenance": list(self.provenance),
            "context": dict(self.context),
            "verification": self.verification.to_dict() if self.verification else None,
            "localization_status": self.localization_status,
            "risk": self.risk,
            "deterministic": self.deterministic,
            "actionable": self.actionable,
            "localized": self.localized,
        }


def stated_constraints(need: Any) -> tuple[str, ...]:
    """Preservation constraints the need ACTUALLY states (bounded, no inference).

    Only cues present in the need's own text are reported, so the planner never
    invents a constraint the request did not make.
    """
    parts: list[str] = []
    for value in (
        getattr(need, "title", ""),
        getattr(need, "summary", ""),
        getattr(need, "rationale", ""),
        getattr(need, "expected_benefit", ""),
    ):
        text = str(value or "").strip().lower()
        if text:
            parts.append(text)
    haystack = " ".join(parts)
    if not haystack:
        return ()
    found: list[str] = []
    for cue in CONSTRAINT_CUES:
        if cue in haystack and cue not in found:
            found.append(cue)
    return tuple(cue[:MAX_CONSTRAINT_CHARS] for cue in found[:MAX_CONSTRAINTS])


def _declared_target(need: Any) -> str:
    for value in getattr(need, "target_components", ()) or ():
        text = str(value or "").strip()
        if text:
            return text[:MAX_EVIDENCE_CHARS]
    return ""


def plan_change(need: Any, *, specialist_available: bool = False) -> ChangePlan:
    """Derive the bounded :class:`ChangePlan` for ``need`` (deterministic).

    The route is decided by EVIDENCE the need already carries — the disjoint
    metadata conventions and, last, the optional specialist seam. Nothing is
    invented; a need with no usable evidence plans ``UNAVAILABLE`` so the caller
    fails closed instead of guessing.
    """
    if not isinstance(need, DevelopmentNeed):
        return ChangePlan(route=AuthorRoute.UNAVAILABLE, reason="not a DevelopmentNeed")

    metadata = need.metadata if isinstance(getattr(need, "metadata", None), dict) else {}
    target = _declared_target(need)
    constraints = stated_constraints(need)

    route = AuthorRoute.UNAVAILABLE
    reason = "no authoring evidence is available for this need"
    for key, candidate in _METADATA_ROUTES:
        if metadata.get(key) is not None:
            route = candidate
            reason = f"the need supplies the existing {key!r} authoring evidence"
            break
    if route is AuthorRoute.UNAVAILABLE and specialist_available:
        route = AuthorRoute.SPECIALIST_MODEL
        reason = (
            "no deterministic authoring evidence; the OPTIONAL specialist seam is "
            "enabled (advisory output, still validated by Atlas)"
        )

    evidence: list[str] = []
    if metadata.get("code_changes"):
        evidence.append("explicit code_changes")
    if metadata.get("structural"):
        evidence.append("structural edit spec")
    if metadata.get("scaffold"):
        evidence.append("scaffold spec")
    if metadata.get("evidence_change"):
        evidence.append("evidence-gap remedy")
    if specialist_available:
        evidence.append("specialist provider enabled")

    risk = "low"
    if route is AuthorRoute.SPECIALIST_MODEL:
        risk = "medium"
    if constraints:
        evidence.append(f"constraints stated: {len(constraints)}")

    return ChangePlan(
        target=target,
        route=route,
        reason=reason[:MAX_EVIDENCE_CHARS],
        constraints=constraints,
        evidence=tuple(evidence[:MAX_CONSTRAINTS]),
        risk=risk,
        deterministic=route is not AuthorRoute.SPECIALIST_MODEL,
    )


@dataclass(frozen=True, slots=True)
class VerificationExpectation:
    """Deterministic evidence a LATER authored change will be judged by.

    This is NOT authorization, NOT approval, NOT a patch, and NOT an instruction
    to execute. Nothing runs because this object exists: ``executed`` and
    ``authorized`` are always False, and the expectations only say which existing
    repository tests the change must not break.
    """

    verification_target: str = ""
    tests: tuple[str, ...] = ()
    expectation: str = ""
    #: ``not_executed`` — planning never runs anything.
    baseline: str = "not_executed"
    provenance: tuple[str, ...] = ()
    deterministic: bool = True
    executed: bool = False
    authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_target": self.verification_target,
            "tests": list(self.tests),
            "expectation": self.expectation,
            "baseline": self.baseline,
            "provenance": list(self.provenance),
            "deterministic": self.deterministic,
            "executed": self.executed,
            "authorized": self.authorized,
        }


def verification_expectations(
    target: str,
    tests: Iterable[str] = (),
    *,
    provenance: Iterable[str] = (),
) -> VerificationExpectation:
    """Bounded, deterministic verification expectations for ``target``.

    The tests are the ones the repository ALREADY relates to the target (the
    import-derived test relation the map computes) — no test is invented and no
    behavioural requirement is claimed that repository evidence does not state.
    The expectation is the standard preservation discipline: those existing tests
    must still pass afterwards. Absent evidence, goals are declared unavailable
    rather than guessed.
    """
    bounded = tuple(sorted({str(item) for item in tests if str(item).strip()}))
    bounded = bounded[:MAX_VERIFICATION_TESTS]
    if bounded:
        expectation = (
            "the selected existing tests must continue to pass after the change"
        )
        reasons = tuple(provenance) or ("import-derived repository test relation",)
    else:
        expectation = (
            "no repository-derived test target was found; verification "
            "expectations are unavailable"
        )
        reasons = ("no repository-derived test relation",)
    return VerificationExpectation(
        verification_target=str(target or ""),
        tests=bounded,
        expectation=expectation,
        provenance=reasons,
    )


def plan_development_change(
    need: Any,
    localization: Any = None,
    *,
    specialist_available: bool = False,
) -> ChangePlan:
    """Derive a bounded :class:`ChangePlan` from a RESOLVED localization.

    The plan carries only EVIDENCE: the localized target, its kind, the resolved
    symbol where one was justified, the constraints the request actually states,
    the bounded relevant context and the localization's own provenance.

    It authorizes nothing. The authoring route is still derived from the need's
    EXISTING metadata evidence exactly as before, so a resolved localization can
    never by itself make a plan actionable — planning and authorization stay
    separate.

    A localization that is not RESOLVED yields a plan with NO target and no
    authoritative scope: ambiguity and unresolved targets are preserved, never
    resolved by preference.
    """
    base = plan_change(need, specialist_available=specialist_available)
    status = str(getattr(getattr(localization, "status", None), "value", "") or "")
    target = str(getattr(localization, "target", "") or "") if localization is not None else ""
    if localization is None or status != "resolved" or not target:
        reason = (
            "the target could not be localized with evidence ("
            + (status or "unresolved")
            + "); no authoritative scope is claimed"
        )
        return replace(
            base,
            localization_status=status or "unresolved",
            reason=reason[:MAX_EVIDENCE_CHARS],
            evidence=(*base.evidence, "localization is not resolved")[:MAX_CONSTRAINTS],
        )

    context = getattr(localization, "context", None)
    symbol = getattr(localization, "symbol", None)
    bounded = {
        "modules": list(getattr(context, "modules", ()) or ()),
        "symbols": [
            str(getattr(item, "qualified", "") or "")
            for item in (getattr(context, "symbols", ()) or ())
        ],
        "tests": list(getattr(context, "tests", ()) or ()),
        "dependencies": list(getattr(context, "dependencies", ()) or ()),
        "dependents": list(getattr(context, "dependents", ()) or ()),
    }
    return replace(
        base,
        target=target,
        target_kind=str(getattr(localization, "target_kind", "") or ""),
        symbol=str(getattr(symbol, "qualified", "") or "") if symbol is not None else "",
        localization_status="resolved",
        provenance=tuple(
            str(item) for item in (getattr(localization, "evidence", ()) or ())
        ),
        context=bounded,
        verification=verification_expectations(
            target, getattr(context, "tests", ()) or ()
        ),
    )


class ChangeAuthorRouter:
    """Deterministic-first router over the EXISTING change-author mechanisms.

    Each deterministic route delegates to the supplier that already owns that
    change class, so this class adds NO new authoring semantics and no new
    terminal states:

    ==================  ==================================================
    route               delegate
    ==================  ==================================================
    ``explicit_patch``  :class:`DeterministicChangeSupplier` (E5 convention)
    ``structural``      :class:`StructuralChangeSupplier` (AST-anchored edit)
    ``scaffold``        :class:`ScaffoldChangeSupplier`
    ``evidence``        :class:`EvidenceChangeSupplier`
    ``specialist_model`` the OPTIONAL injected provider seam
    ==================  ==================================================

    The specialist is consulted LAST and only when it was explicitly injected,
    so deterministic authoring always wins. Routing grants no authority: the
    returned ``SuppliedChanges`` is still a DRAFT that must pass path safety,
    the sandbox, verification, approval and promotion.
    """

    def __init__(
        self,
        *,
        specialist: Any | None = None,
        repository_root: Any | None = None,
    ) -> None:
        from atlas.evolution.development_scaffold_supplier import (
            ScaffoldChangeSupplier,
        )
        from atlas.evolution.evidence_development import EvidenceChangeSupplier
        from atlas.evolution.structural_editor import StructuralChangeSupplier

        self._specialist = specialist
        self._authors: dict[AuthorRoute, ChangeSupplier] = {
            AuthorRoute.EXPLICIT_PATCH: DeterministicChangeSupplier(),
            AuthorRoute.STRUCTURAL: StructuralChangeSupplier(repository_root),
            AuthorRoute.SCAFFOLD: ScaffoldChangeSupplier(),
            AuthorRoute.EVIDENCE: EvidenceChangeSupplier(),
        }

    @property
    def specialist_enabled(self) -> bool:
        """Whether an OPTIONAL specialist authoring provider is wired."""
        return self._specialist is not None

    def routes(self) -> tuple[AuthorRoute, ...]:
        """The routes this router can currently serve, in priority order."""
        available = [route for route in ROUTE_PRIORITY if route in self._authors]
        if self.specialist_enabled:
            available.append(AuthorRoute.SPECIALIST_MODEL)
        return tuple(available)

    def plan(self, need: Any) -> ChangePlan:
        """The bounded plan for ``need`` (deterministic)."""
        return plan_change(need, specialist_available=self.specialist_enabled)

    def author(self, need: Any) -> SuppliedChanges | None:
        """Route ``need`` to the matching author and return its draft, or ``None``.

        Deterministic routes are attempted in priority order and the first
        non-``None`` draft wins; the optional specialist is consulted only when
        NO deterministic route produced a draft. A ``ValueError`` raised by a
        supplier is allowed to propagate: the existing controller turns it into
        the fail-closed ``supplier`` stage failure.
        """
        if not isinstance(need, DevelopmentNeed):
            return None
        plan = self.plan(need)
        for route in ROUTE_PRIORITY:
            author = self._authors.get(route)
            if author is None:
                continue
            supplied = author.supply_changes(need)
            if supplied is not None:
                return supplied
        if self._specialist is not None:
            supplied = self._specialist.supply_changes(need)
            if supplied is not None:
                return supplied
        return None

    def author_for(self, need: Any, route: AuthorRoute) -> SuppliedChanges | None:
        """Author using ONE explicit route (deterministic; ``None`` when absent).

        Exposed so a caller that has already planned can dispatch deterministically
        without re-deriving, and so tests can assert route isolation.
        """
        if not isinstance(need, DevelopmentNeed):
            return None
        if route is AuthorRoute.SPECIALIST_MODEL:
            return (
                self._specialist.supply_changes(need)
                if self._specialist is not None
                else None
            )
        author = self._authors.get(route)
        return author.supply_changes(need) if author is not None else None


__all__ = [
    "AuthorRoute",
    "CONSTRAINT_CUES",
    "ChangeAuthorRouter",
    "ChangePlan",
    "ROUTE_PRIORITY",
    "plan_change",
    "stated_constraints",
]
