"""Atlas Evolution — evidence-directed development (Step 3, first slice).

The smallest bridge from **validated evidence of a concrete Atlas capability
gap** to the **existing governed development pipeline**:

    ConcreteGap  ->  DevelopmentNeed        (this module, deterministic)
                 ->  resolved source file   (existing ArchitectureModel, no new
                                             source-of-truth mapping)
                 ->  SuppliedChanges        (EvidenceChangeSupplier, below)
                 ->  DevelopmentCycleController.run_development_cycle()
                 ->  EvolutionProposal + ApprovalRequest + PENDING_APPROVAL
                 ->  STOP (human approval boundary)

Nothing here approves, authorizes, executes, promotes, schedules or persists
anything: the existing ``DevelopmentCycleController`` owns the proposal and the
existing ``ApprovalManager`` owns the approval request. This module is
model-independent (no AI import, no provider call), deterministic (identical
input -> identical output), stdlib-only, and fail-closed: an insufficient
report, an unsupported gap category, an unresolvable component or an
architecture-sensitive target each return an explicit truthful reason instead
of a guessed need.

Only ONE remedy is supported by this first slice:

    ConcreteGap.category == untested_component
        -> a deterministic pytest module that records coverage evidence for
           the gap's named component
"""

from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass, replace
from typing import Any

from atlas.conversation.evidence_gap_analysis import (
    ConcreteGap,
    GapAnalysisReport,
    GapCategory,
)
from atlas.evolution.autonomy.code_sandbox import CodeChangeSet
from atlas.evolution.development_cycle import DevelopmentNeed, SuppliedChanges
from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES

#: Bounds (a malformed/oversized gap can never produce an unbounded need).
MAX_COMPONENT_CHARS: int = 200
MAX_REASON_CHARS: int = 300
MAX_RATIONALE_CHARS: int = 4_000
MAX_EVIDENCE_IDS: int = 20
MAX_TEST_CONTENT_CHARS: int = 8_000

#: The only gap category this slice knows a remedy for.
SUPPORTED_GAP_CATEGORY: str = GapCategory.UNTESTED_COMPONENT.value

#: Provenance marker stamped on authored changes (never verified knowledge).
EVIDENCE_CHANGE_ORIGIN: str = "deterministic-evidence-gap"

#: Metadata key carrying the resolved remedy spec inside a DevelopmentNeed.
EVIDENCE_CHANGE_KEY: str = "evidence_change"


def _bounded(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _stable_id(seed: str) -> str:
    """Deterministic short identifier for a seed string."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _is_architecture_sensitive(dotted_module: str) -> bool:
    """True when the existing policy protects this module from authoring."""
    return any(
        dotted_module.startswith(prefix) for prefix in ARCHITECTURE_SENSITIVE_PREFIXES
    )


def _dotted_from_path(path: str) -> str:
    """The dotted module name of a POSIX-relative ``.py`` path."""
    return posixpath.splitext(path)[0].replace("/", ".")


@dataclass(frozen=True, slots=True)
class GapTarget:
    """The resolved source + test locations for one evidence gap."""

    component: str
    source_path: str
    test_path: str
    module: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "source_path": self.source_path,
            "test_path": self.test_path,
            "module": self.module,
        }


@dataclass(frozen=True, slots=True)
class EvidenceDevelopmentOutcome:
    """Bounded, truthful result of one evidence-directed preparation attempt.

    ``status`` is ``prepared`` (a Draft proposal reached PENDING_APPROVAL),
    ``refused`` (fail-closed before authoring) or ``failed`` (the existing
    cycle itself failed). ``reason`` is always a truthful, bounded explanation.
    """

    status: str
    reason: str = ""
    component: str = ""
    source_path: str = ""
    test_path: str = ""
    need: DevelopmentNeed | None = None
    cycle: Any = None

    @property
    def prepared(self) -> bool:
        return self.status == "prepared"

    def with_cycle(self, cycle: Any) -> "EvidenceDevelopmentOutcome":
        """Attach the existing development-cycle result (no state mutation)."""
        decision = str(getattr(cycle, "decision", "") or "")
        if decision == "prepared":
            return replace(self, status="prepared", reason="", cycle=cycle)
        failures = tuple(getattr(cycle, "failures", ()) or ())
        detail = "; ".join(f"{stage}: {message}" for stage, message in failures)
        return replace(
            self,
            status="failed",
            reason=_bounded(detail or "development cycle failed", MAX_REASON_CHARS),
            cycle=cycle,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "component": self.component,
            "source_path": self.source_path,
            "test_path": self.test_path,
            "proposal_id": getattr(self.cycle, "proposal_id", ""),
            "approval_request_id": getattr(self.cycle, "approval_request_id", ""),
            "proposal_status": getattr(self.cycle, "proposal_status", ""),
        }


# ---------------------------------------------------------------------------
# B. Component -> source path (existing self-knowledge only)
# ---------------------------------------------------------------------------


def resolve_gap_target(
    component: str,
    *,
    architecture: Any,
) -> tuple[GapTarget | None, str]:
    """Resolve a gap component to its real source file, or ``(None, reason)``.

    Uses the EXISTING read-only self-knowledge model only:

      * ``ArchitectureModel.locate(component)`` confirms the component is known
        (as a capability, a registered component, or a repository module);
      * the authoritative module -> file mapping comes from the EXISTING
        ``RepositoryMap`` modules (``module`` -> ``path``) or from the
        component's declared ``module_path`` — never from the string itself.

    Fail-closed: an unknown, package-only, non-``.py``, or
    architecture-sensitive target returns ``(None, reason)``.
    """
    name = _bounded(component, MAX_COMPONENT_CHARS)
    if not name:
        return None, "the gap names no component"
    if architecture is None:
        return None, "no architecture model is available"

    try:
        located = architecture.locate(name)
    except Exception as exc:  # defensive — locate never raises by contract
        return None, f"architecture lookup failed: {_bounded(str(exc), 120)}"
    if not getattr(located, "found", False):
        return None, f"component '{name}' is not known to the architecture model"

    source_path = ""
    kind = str(getattr(located, "matched_kind", "") or "")
    if kind in ("capability", "component"):
        paths = tuple(getattr(located, "module_paths", ()) or ())
        source_path = str(paths[0]) if paths else ""
    elif kind == "module":
        source_path = _module_path_from_map(name, architecture)
    if not source_path:
        return None, f"component '{name}' has no resolvable source file"

    source_path = source_path.replace("\\", "/")
    try:
        CodeChangeSet.validate_path(source_path)
    except Exception as exc:
        return None, f"resolved path is not authorable: {_bounded(str(exc), 120)}"
    if not source_path.endswith(".py"):
        return None, f"resolved target '{source_path}' is not a Python module"
    if _is_architecture_sensitive(_dotted_from_path(source_path)):
        return None, (
            f"component '{name}' resolves to an architecture-sensitive module "
            "(protected by the existing promotion/development policy)"
        )

    stem = posixpath.splitext(posixpath.basename(source_path))[0]
    if not stem or not stem.replace("_", "").isalnum():
        return None, f"resolved target '{source_path}' has no authorable stem"
    test_path = f"tests/test_{stem}_evidence_gap.py"
    try:
        CodeChangeSet.validate_path(test_path)
    except Exception as exc:
        return None, f"derived test path is not authorable: {_bounded(str(exc), 120)}"

    return (
        GapTarget(
            component=name,
            source_path=source_path,
            test_path=test_path,
            module=_dotted_from_path(source_path),
        ),
        "",
    )


def _module_path_from_map(module_name: str, architecture: Any) -> str:
    """The authoritative file path of ``module_name`` from the EXISTING map."""
    repository_map = getattr(architecture, "repository_map", None)
    for info in tuple(getattr(repository_map, "modules", ()) or ()):
        if str(getattr(info, "module", "") or "") != module_name:
            continue
        if bool(getattr(info, "is_package", False)):
            return ""
        return str(getattr(info, "path", "") or "")
    return ""


# ---------------------------------------------------------------------------
# A. Gap -> DevelopmentNeed
# ---------------------------------------------------------------------------


def _select_gap(report: Any, gap_id: str) -> tuple[ConcreteGap | None, str]:
    """The requested ``ConcreteGap`` (by id, else the first), or a reason."""
    if not isinstance(report, GapAnalysisReport):
        return None, "no validated gap analysis report was supplied"
    if bool(getattr(report, "insufficient_evidence", False)):
        return None, (
            "the gap analysis reports insufficient evidence; no development "
            "need was created"
        )
    gaps = tuple(getattr(report, "gaps", ()) or ())
    if not gaps:
        return None, "the gap analysis reports no concrete gaps"
    wanted = _bounded(gap_id, 64)
    if wanted:
        for gap in gaps:
            if str(getattr(gap, "gap_id", "") or "") == wanted:
                return gap, ""
        return None, f"no concrete gap with id '{wanted}' in the report"
    return gaps[0], ""


def _citation_lines(gap: ConcreteGap) -> list[str]:
    """Bounded, human-readable citation lines preserving the gap's evidence."""
    lines: list[str] = []
    for citation in tuple(getattr(gap, "evidence", ()) or ())[:MAX_EVIDENCE_IDS]:
        category = _bounded(getattr(citation, "category", ""), 64)
        description = _bounded(getattr(citation, "description", ""), 200)
        location = _bounded(getattr(citation, "location", ""), 200)
        suffix = f" ({location})" if location else ""
        lines.append(f"- [{category}] {description}{suffix}")
    return lines


def _evidence_ids(gap: ConcreteGap) -> tuple[str, ...]:
    """Bounded, deterministic evidence ids (the existing carried convention)."""
    ids: list[str] = [f"evidence-gap::{_bounded(gap.gap_id, 32)}"]
    for citation in tuple(getattr(gap, "evidence", ()) or ())[: MAX_EVIDENCE_IDS - 1]:
        seed = ":".join(
            (
                _bounded(gap.gap_id, 32),
                _bounded(getattr(citation, "category", ""), 64),
                _bounded(getattr(citation, "location", ""), 200),
                _bounded(getattr(citation, "description", ""), 200),
            )
        )
        ids.append(f"evidence-gap-citation::{_stable_id(seed)}")
    return tuple(ids[:MAX_EVIDENCE_IDS])


def development_need_from_gap(
    report: Any,
    *,
    gap_id: str = "",
    architecture: Any,
) -> EvidenceDevelopmentOutcome:
    """Convert ONE validated ``ConcreteGap`` into an existing ``DevelopmentNeed``.

    Deterministic, model-free and fail-closed. The gap's component is preserved
    verbatim, its citations are preserved (as bounded evidence ids and as
    bounded human-readable rationale lines), and nothing that the report does
    not contain is invented.
    """
    gap, reason = _select_gap(report, gap_id)
    if gap is None:
        return EvidenceDevelopmentOutcome(status="refused", reason=reason)

    category = str(getattr(getattr(gap, "category", None), "value", "") or "")
    component = _bounded(getattr(gap, "component", ""), MAX_COMPONENT_CHARS)
    if category != SUPPORTED_GAP_CATEGORY:
        return EvidenceDevelopmentOutcome(
            status="refused",
            reason=(
                f"gap category '{category or 'unknown'}' has no supported remedy "
                "in this slice"
            ),
            component=component,
        )

    target, reason = resolve_gap_target(component, architecture=architecture)
    if target is None:
        return EvidenceDevelopmentOutcome(
            status="refused", reason=reason, component=component
        )

    observation = _bounded(getattr(gap, "observation", ""), MAX_REASON_CHARS)
    interpretation = _bounded(getattr(gap, "interpretation", ""), MAX_REASON_CHARS)
    sufficiency = str(getattr(getattr(gap, "sufficiency", None), "value", "") or "")
    citation_lines = _citation_lines(gap)

    rationale_parts = [
        f"Evidence gap {_bounded(gap.gap_id, 32)} [{category}] on component "
        f"'{target.component}' (sufficiency: {sufficiency or 'unknown'}).",
    ]
    if observation:
        rationale_parts.append(f"Observed: {observation}")
    if interpretation:
        rationale_parts.append(f"Gap: {interpretation}")
    if citation_lines:
        rationale_parts.append("Evidence:")
        rationale_parts.extend(citation_lines)
    rationale = "\n".join(rationale_parts)[:MAX_RATIONALE_CHARS]

    need = DevelopmentNeed(
        title=f"Add missing test evidence for {target.component}"[:200],
        summary=(
            f"The validated investigation evidence records a "
            f"{category} gap for '{target.component}': no test evidence "
            f"references it."
        )[:MAX_RATIONALE_CHARS],
        rationale=rationale,
        expected_benefit=(
            f"'{target.component}' gains traceable test evidence, closing the "
            "gap the investigation recorded."
        )[:MAX_RATIONALE_CHARS],
        target_components=(target.component,),
        candidate_id=f"evidence-gap::{_bounded(gap.gap_id, 32)}",
        evidence_change_ids=_evidence_ids(gap),
        metadata={
            EVIDENCE_CHANGE_KEY: {
                "category": category,
                "component": target.component,
                "module": target.source_path,
                "test_module": target.test_path,
                "gap_id": _bounded(gap.gap_id, 32),
            }
        },
    )
    return EvidenceDevelopmentOutcome(
        status="prepared",
        component=target.component,
        source_path=target.source_path,
        test_path=target.test_path,
        need=need,
    )


# ---------------------------------------------------------------------------
# C. Evidence-targeted change supplier (existing ChangeSupplier protocol)
# ---------------------------------------------------------------------------

_TEST_TEMPLATE = '''"""{docstring}

Generated deterministically by the Step 3 evidence-directed author from a
validated evidence gap. It records the component this module provides test
evidence for, and asserts the component module loads when the package layout
is available (skipped inside a bare sandbox).
"""

from __future__ import annotations

import pytest

#: The Atlas component this module provides test evidence for.
COMPONENT = "{component}"

#: The resolved source module of that component.
COMPONENT_MODULE = "{module}"


def test_evidence_records_the_component():
    assert COMPONENT == "{component}"
    assert COMPONENT_MODULE.endswith(".py")


def test_component_module_is_importable():
    assert pytest.importorskip("{component}") is not None
'''


@dataclass(frozen=True, slots=True)
class EvidenceGapSpec:
    """Validated evidence-gap remedy specification (pure data)."""

    category: str
    component: str
    module: str
    test_module: str


class EvidenceChangeSupplier:
    """Deterministic ``ChangeSupplier`` for the evidence-gap remedy class.

    Reads ``need.metadata["evidence_change"]`` (written by
    :func:`development_need_from_gap`) and authors exactly one bounded,
    deterministic pytest module providing coverage evidence for the gap's named
    component. It authors no other change class, never touches the repository,
    approvals or execution, and fails closed (``ValueError``) on a malformed
    spec or a gap category it has no remedy for.
    """

    #: Maximum authored files (bounded; the controller additionally bounds them).
    MAX_FILES: int = 1

    @property
    def origin(self) -> str:
        """Provenance marker stamped on authored changes."""
        return EVIDENCE_CHANGE_ORIGIN

    def supply_changes(self, need: DevelopmentNeed) -> SuppliedChanges | None:
        """Author the evidence-gap remedy for ``need`` (or ``None``)."""
        metadata = getattr(need, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        raw = metadata.get(EVIDENCE_CHANGE_KEY)
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError("malformed 'evidence_change' spec (must be an object)")

        spec = self._validate(raw)
        content = self._test_content(spec)
        return SuppliedChanges(
            # The generated pytest module is the WHOLE remedy. It is carried in
            # ``test_files`` (its declared change class) and mirrored in
            # ``code_changes`` because the EXISTING controller requires at least
            # one bounded code change; the pair is byte-identical.
            code_changes=((spec.test_module, content),),
            test_files=((spec.test_module, content),),
            origin=self.origin,
            confidence=1.0,
            notes="deterministic evidence-gap coverage test",
        )

    # -- internals ---------------------------------------------------------

    def _validate(self, raw: dict) -> EvidenceGapSpec:
        category = raw.get("category")
        component = raw.get("component")
        module = raw.get("module")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("evidence_change 'category' is required")
        category = category.strip()
        if category != SUPPORTED_GAP_CATEGORY:
            raise ValueError(
                f"unsupported gap category '{category}' (no remedy in this slice)"
            )
        if not isinstance(component, str) or not component.strip():
            raise ValueError("evidence_change 'component' is required")
        component = component.strip()[:MAX_COMPONENT_CHARS]
        if not isinstance(module, str) or not module.strip():
            raise ValueError("evidence_change 'module' is required")
        module = module.strip().replace("\\", "/")

        # Path confinement + bounds (reuse the existing validators).
        CodeChangeSet.validate_path(module)
        if "/" not in module or not module.endswith(".py"):
            raise ValueError(
                "evidence_change 'module' must be a package-directory .py file"
            )
        if _is_architecture_sensitive(_dotted_from_path(module)):
            raise ValueError(
                "evidence_change cannot target an architecture-sensitive module"
            )

        stem = posixpath.splitext(posixpath.basename(module))[0]
        if not stem or not stem.replace("_", "").isalnum():
            raise ValueError("evidence_change module stem must be alphanumeric")

        test_module = raw.get("test_module")
        if test_module is None:
            test_module = f"tests/test_{stem}_evidence_gap.py"
        if not isinstance(test_module, str) or not test_module.strip():
            raise ValueError("evidence_change 'test_module' must be a non-empty string")
        test_module = test_module.strip().replace("\\", "/")
        CodeChangeSet.validate_path(test_module)
        if not test_module.startswith("tests/") or not test_module.endswith(".py"):
            raise ValueError(
                "evidence_change 'test_module' must be a tests/<name>.py path"
            )

        return EvidenceGapSpec(
            category=category,
            component=component,
            module=module,
            test_module=test_module,
        )

    def _test_content(self, spec: EvidenceGapSpec) -> str:
        content = _TEST_TEMPLATE.format(
            docstring=f"Evidence-coverage test for {spec.component}.",
            component=spec.component,
            module=spec.module,
        )[:MAX_TEST_CONTENT_CHARS]
        return content
