"""Atlas Evolution — Self-Development Capability Inventory (Phase 9.1 / 9.13).

A deterministic, read-only catalogue of the capabilities Atlas needs to execute
its governed development lifecycle. Each entry records OWNERSHIP — whether the
stage is Atlas-owned, governance/human-gated, or an optional external tool — and
availability (verified by importable-module presence, not assumption).

It executes nothing, asserts no authority, and never invokes a model. It exists
so Atlas can state, honestly, WHAT it can do itself and WHERE a human or
governance boundary applies.

The critical boundary it makes explicit:

    Atlas-owned execution  (plan / generate / apply / verify / diagnose / evidence)
    governed/human gate    (approve / promote / activate)
    optional external tool (model-assisted authoring — never required)

Pure logic: stdlib only. No AI, no network, no storage, no kernel, no execution.
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from enum import Enum
from typing import Any


class OwnershipKind(str, Enum):
    """Who performs a development-lifecycle stage."""

    ATLAS_OWNED = "atlas_owned"            # Atlas performs it itself, deterministically
    GOVERNED_ONLY = "governed_only"        # Atlas performs it, but only through governance
    HUMAN_DEPENDENT = "human_dependent"    # requires an explicit human decision
    EXTERNAL_OPTIONAL = "external_optional"  # optional external tool; never required
    MISSING = "missing"                    # not available


class Availability(str, Enum):
    """Whether the stage's component is actually present."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DevelopmentCapabilityEntry:
    """One development-lifecycle capability (immutable)."""

    key: str
    name: str
    ownership: OwnershipKind
    required: bool
    module: str
    symbol: str = ""
    availability: Availability = Availability.UNKNOWN
    limitation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "ownership": self.ownership.value,
            "required": self.required,
            "module": self.module,
            "symbol": self.symbol,
            "availability": self.availability.value,
            "limitation": self.limitation,
        }


#: The deterministic catalogue of the governed development lifecycle.
_CATALOGUE: tuple[tuple[str, str, OwnershipKind, bool, str, str, str], ...] = (
    (
        "goal_intake",
        "Development goal interpretation",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.conversation.development_intake",
        "",
        "",
    ),
    (
        "architecture_inspection",
        "Repository/architecture self-inspection",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.self_knowledge.architecture_model",
        "",
        "Facts absent from authoritative sources are reported as absent.",
    ),
    (
        "planning",
        "Development planning",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.development_planner",
        "DevelopmentPlanner",
        "",
    ),
    (
        "change_design",
        "Change design representation",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.development_cycle",
        "SuppliedChanges",
        "",
    ),
    (
        "change_generation",
        "Own change generation (deterministic)",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.development_scaffold_supplier",
        "ScaffoldChangeSupplier",
        "Bounded to the supported deterministic change classes (no arbitrary synthesis).",
    ),
    (
        "sandbox_implementation",
        "Sandbox implementation",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.self_development_loop",
        "SelfDevelopmentLoop",
        "",
    ),
    (
        "test_selection",
        "Relevant-test selection",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.development_test_selection",
        "select_relevant_tests",
        "",
    ),
    (
        "verification",
        "Self-verification",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.development_verification",
        "DevelopmentVerification",
        "",
    ),
    (
        "diagnosis",
        "Failure diagnosis",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.development_diagnostic",
        "DevelopmentDiagnostic",
        "",
    ),
    (
        "recovery",
        "Bounded recovery/revision",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.development_recovery",
        "DevelopmentRecovery",
        "Bounded by the iteration budget; fail-closed (NO_RECOVERY) on unclear evidence.",
    ),
    (
        "evidence",
        "Evidence/history",
        OwnershipKind.ATLAS_OWNED,
        True,
        "atlas.evolution.development_report",
        "DevelopmentReportBuilder",
        "",
    ),
    (
        "approval",
        "Human approval gate",
        OwnershipKind.GOVERNED_ONLY,
        True,
        "atlas.evolution.approval_manager",
        "ApprovalManager",
        "",
    ),
    (
        "promotion_review",
        "Promotion review",
        OwnershipKind.GOVERNED_ONLY,
        True,
        "atlas.evolution.promotion_gate",
        "PromotionGate",
        "APPROVED means ready for human promotion, never a repository change.",
    ),
    (
        "promotion",
        "OWNER promotion (production write)",
        OwnershipKind.HUMAN_DEPENDENT,
        True,
        "atlas.evolution.promotion_executor",
        "PromotionExecutor",
        "OWNER-only; the human-authorized production boundary.",
    ),
    (
        "activation",
        "Capability activation",
        OwnershipKind.GOVERNED_ONLY,
        True,
        "atlas.evolution.capability_activation",
        "CapabilityActivator",
        "Reachable only inside the OWNER-gated promotion lifecycle.",
    ),
    (
        "model_assisted_authoring",
        "Model-assisted authoring",
        OwnershipKind.EXTERNAL_OPTIONAL,
        False,
        "atlas.evolution.model_assisted_supplier",
        "ModelAssistedChangeSupplier",
        "Opt-in only; never required, never authoritative.",
    ),
)


def _availability(module: str, symbol: str) -> Availability:
    """Deterministic presence check for a component (no import side effects)."""
    if not module:
        return Availability.UNKNOWN
    try:
        spec = importlib.util.find_spec(module)
    except Exception:
        return Availability.UNKNOWN
    if spec is None:
        return Availability.UNAVAILABLE
    if not symbol:
        return Availability.AVAILABLE
    try:
        loaded = importlib.import_module(module)
    except Exception:
        return Availability.UNKNOWN
    return (
        Availability.AVAILABLE
        if hasattr(loaded, symbol)
        else Availability.UNAVAILABLE
    )


@dataclass(frozen=True, slots=True)
class SelfDevelopmentInventory:
    """Deterministic, read-only inventory of Atlas's development capabilities."""

    entries: tuple[DevelopmentCapabilityEntry, ...]

    def by_key(self, key: str) -> DevelopmentCapabilityEntry | None:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None

    def external_optional(self) -> tuple[str, ...]:
        """Keys of optional external tools (must never be ``required``)."""
        return tuple(
            e.key for e in self.entries if e.ownership is OwnershipKind.EXTERNAL_OPTIONAL
        )

    def external_dependencies(self) -> tuple[str, ...]:
        """Required capabilities that are externally dependent (should be empty)."""
        return tuple(
            e.key
            for e in self.entries
            if e.required and e.ownership is OwnershipKind.EXTERNAL_OPTIONAL
        )

    def missing_required(self) -> tuple[str, ...]:
        """Required capabilities that are missing/unavailable."""
        return tuple(
            e.key
            for e in self.entries
            if e.required
            and (
                e.ownership is OwnershipKind.MISSING
                or e.availability is Availability.UNAVAILABLE
            )
        )

    def atlas_owned(self) -> tuple[str, ...]:
        return tuple(
            e.key for e in self.entries if e.ownership is OwnershipKind.ATLAS_OWNED
        )

    def governed_or_human(self) -> tuple[str, ...]:
        return tuple(
            e.key
            for e in self.entries
            if e.ownership
            in (OwnershipKind.GOVERNED_ONLY, OwnershipKind.HUMAN_DEPENDENT)
        )

    @property
    def self_sufficient(self) -> bool:
        """True when every required capability is Atlas-owned/governed/human-gated
        and present — i.e. no required capability is externally dependent."""
        return not self.external_dependencies() and not self.missing_required()

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self.entries),
            "atlas_owned": self.atlas_owned(),
            "governed_or_human": self.governed_or_human(),
            "external_optional": self.external_optional(),
            "external_dependencies": self.external_dependencies(),
            "missing_required": self.missing_required(),
            "self_sufficient": self.self_sufficient,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "entries": [e.to_dict() for e in self.entries],
        }


def build_inventory() -> SelfDevelopmentInventory:
    """Build the deterministic self-development capability inventory."""
    entries = tuple(
        DevelopmentCapabilityEntry(
            key=key,
            name=name,
            ownership=ownership,
            required=required,
            module=module,
            symbol=symbol,
            availability=_availability(module, symbol),
            limitation=limitation,
        )
        for (key, name, ownership, required, module, symbol, limitation) in _CATALOGUE
    )
    return SelfDevelopmentInventory(entries=entries)
