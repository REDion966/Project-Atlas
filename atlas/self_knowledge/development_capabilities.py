"""Atlas Self-Knowledge — Development Capability catalogue (Command 6).

The single bounded, deterministic, evidence-grounded source of truth for Atlas's
DEVELOPMENT capabilities: the governed self-development machinery built and
validated in Commands 1–5 (bounded specialist task → real local coding-model
inference → validated untrusted proposal → governed authoring → sandbox
verification → verification attribution → bounded specialist repair →
re-verification).

Why this exists
---------------
Atlas already models its conversational/operational abilities
(:mod:`atlas.self_knowledge.operational_capabilities`) and its registered
implementation surface (:mod:`atlas.self_knowledge.capability_model`), and it can
adjudicate a genuine capability gap (``capability_gap``). What it did NOT have was
one identity for the DEVELOPMENT capabilities themselves: which they are, whether
each is ACTIVE, PARTIAL or FUTURE, where each lives, what interface it exposes,
what governance applies, whether it is deterministic or externally assisted and
whether it is validated — with an evidence reference. Without that, a request to
develop Atlas could not be grounded in what Atlas already knows about its own
development machinery.

Representation only
-------------------
Deterministic, model-independent, standard library only — no I/O, no clock, no
model. It never registers, executes, authorizes or mutates anything and grants no
authority. Every entry is grounded in a real Atlas module/interface/test/document
(the ``evidence`` field), so a capability is never claimed merely because a name
exists; a FUTURE capability is declared as such rather than invented.

Scope boundary
--------------
This is a self-knowledge model, not an autonomy mechanism. It reports what exists
and where; it does not implement, approve, execute, verify or promote anything.
Self-knowledge cannot mutate Atlas, approve, promote, or bypass any governance
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from atlas.self_knowledge.operational_capabilities import (
    DEP_DETERMINISTIC,
    DEP_EXTERNAL_MODEL,
    OperationalCapability,
)

#: Bound on the catalogue (an explicit, bounded list — not a discovery scan).
MAX_DEVELOPMENT_CAPABILITIES: int = 32
#: Bound on the free-text fields.
_MAX_TEXT_CHARS: int = 600


class CapabilityStatus(str, Enum):
    """The declared status of a development capability (closed set)."""

    #: Implemented and validated end to end (real tests and/or real probes).
    ACTIVE = "active"
    #: Implemented in part / bounded (a known limitation remains).
    PARTIAL = "partial"
    #: A legitimate capability that is NOT yet implemented (declared honestly).
    FUTURE = "future"
    #: Declared, but currently unavailable because its wiring is absent.
    NOT_AVAILABLE = "not_available"


@dataclass(frozen=True, slots=True)
class DevelopmentCapability:
    """One bounded, evidence-grounded development capability (facts only)."""

    id: str
    name: str
    purpose: str
    status: str
    owner_module: str
    entry: str
    dependencies: tuple[str, ...] = ()
    governance: tuple[str, ...] = ()
    #: ``deterministic`` or ``external_model_dependent`` (the optional local model).
    dependency_class: str = DEP_DETERMINISTIC
    validated: bool = False
    evidence: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    #: Capability ids this one extends/participates in (extension relationships).
    extends: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "purpose": self.purpose,
            "status": self.status,
            "owner_module": self.owner_module,
            "entry": self.entry,
            "dependencies": list(self.dependencies),
            "governance": list(self.governance),
            "dependency_class": self.dependency_class,
            "validated": self.validated,
            "evidence": list(self.evidence),
            "aliases": list(self.aliases),
            "extends": list(self.extends),
            "limitations": list(self.limitations),
        }


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


#: The bounded development capability catalogue. Every entry names the REAL
#: Atlas module/interface/test/document that grounds it.
_CATALOGUE: tuple[DevelopmentCapability, ...] = (
    DevelopmentCapability(
        id="development.localization",
        name="Development target localization",
        purpose=(
            "Localize a natural-language development request to one repository "
            "target."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.development_localization",
        entry="DevelopmentLocalizer.localize",
        dependencies=("atlas.research.repository_map",),
        governance=(),
        validated=True,
        evidence=(
            "atlas.evolution.development_localization",
            "tests/test_development_localization.py",
        ),
        aliases=("localization", "target_localization"),
        extends=("development.planning",),
    ),
    DevelopmentCapability(
        id="development.planning",
        name="ChangePlan / verification expectations",
        purpose=(
            "Derive a bounded ChangePlan and its verification expectations from a "
            "localization."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.change_author_router",
        entry="plan_development_change",
        dependencies=("development.localization",),
        governance=(),
        validated=True,
        evidence=(
            "atlas.evolution.change_author_router",
            "tests/test_development_change_plan.py",
        ),
        aliases=("planning", "change_plan"),
        extends=("governed.authoring",),
    ),
    DevelopmentCapability(
        id="code.generate",
        name="Specialist code generation",
        purpose=(
            "Produce a bounded candidate implementation from a localized change "
            "request."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.specialist_development",
        entry="SpecialistDevelopmentAuthor.propose",
        dependencies=(
            "atlas.specialists.SpecialistRegistry",
            "atlas.specialist_providers.HttpCodeGenerationProvider",
            "atlas.specialist_transport.ollama_transport",
        ),
        governance=("owner_approval", "sandbox_execution", "provider_isolation"),
        dependency_class=DEP_EXTERNAL_MODEL,
        validated=True,
        evidence=(
            "atlas.evolution.specialist_development",
            "docs/COMMAND_3B_SPECIALIST_OWNER_ACCEPTANCE.md",
            "tests/test_specialist_development_author.py",
        ),
        aliases=("code_generate", "code_generation", "specialist", "specialist_model"),
        extends=("governed.authoring",),
        limitations=(
            "One bounded file per proposal; output is UNTRUSTED and requires "
            "OWNER approval and sandbox verification.",
        ),
    ),
    DevelopmentCapability(
        id="governed.authoring",
        name="Governed authoring bridge",
        purpose=(
            "Turn an untrusted specialist proposal into the existing bounded "
            "code-change representation."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.specialist_change_supplier",
        entry="SpecialistChangeSupplier.supply_changes",
        dependencies=(
            "atlas.evolution.development_scaffold_supplier.CompositeChangeSupplier",
        ),
        governance=("owner_approval", "sandbox_execution"),
        validated=True,
        evidence=(
            "atlas.evolution.specialist_change_supplier",
            "tests/test_specialist_change_supplier.py",
            "tests/test_governed_development_bridge.py",
        ),
        aliases=("authoring", "specialist_authoring"),
        extends=("development.verification",),
        limitations=("Exactly one authorized target change per proposal.",),
    ),
    DevelopmentCapability(
        id="development.verification",
        name="Bounded sandbox verification",
        purpose=(
            "Run the plan-selected focused test on the applied change inside a "
            "disposable sandbox."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.self_development_loop",
        entry="SandboxVerifier.run",
        dependencies=("atlas.evolution.autonomy.code_sandbox",),
        governance=("sandbox_execution", "fail_closed"),
        validated=True,
        evidence=(
            "atlas.evolution.self_development_loop",
            "tests/test_phase42_development_lifecycle.py",
        ),
        aliases=("verification", "sandbox_verification", "verify"),
        extends=("development.attribution",),
        limitations=(
            "Bounded by the SandboxVerifier test timeout; never writes to the "
            "live repository.",
        ),
    ),
    DevelopmentCapability(
        id="development.attribution",
        name="Verification attribution",
        purpose=(
            "Classify a verification result against its pre-change baseline "
            "(pass_to_fail / fail_to_fail / …)."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.verification_attribution",
        entry="classify_transition",
        dependencies=("development.verification",),
        governance=("fail_closed",),
        validated=True,
        evidence=(
            "atlas.evolution.verification_attribution",
            "docs/COMMAND_4_EVIDENCE_DRIVEN_EVOLUTION.md",
            "tests/test_verification_attribution.py",
        ),
        aliases=("attribution", "verification_attribution"),
        extends=("code.repair",),
    ),
    DevelopmentCapability(
        id="code.repair",
        name="Bounded specialist repair",
        purpose=(
            "Author ONE corrective change to the same authorized target after an "
            "attributable failure, then re-verify."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.development_repair",
        entry="RepairChangeSupplier",
        dependencies=("code.generate", "development.attribution"),
        governance=("owner_approval", "sandbox_execution", "provider_isolation"),
        dependency_class=DEP_EXTERNAL_MODEL,
        validated=True,
        evidence=(
            "atlas.evolution.development_repair",
            "docs/COMMAND_3_FINAL_CODING_SPECIALIST_ACCEPTANCE.md",
            "tests/test_specialist_repair.py",
        ),
        aliases=("repair", "code_repair", "specialist_repair"),
        extends=("development.verification",),
        limitations=(
            "Repairs only an ATTRIBUTABLE failure (a regression), within the "
            "existing bounded iteration budget; never expands scope.",
        ),
    ),
    DevelopmentCapability(
        id="governance.approval",
        name="OWNER approval boundary",
        purpose=(
            "Require an explicit OWNER decision before any governed change "
            "executes."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.approval_manager",
        entry="ApprovalManager.create_approval_request",
        dependencies=(),
        governance=("owner_approval",),
        validated=True,
        evidence=(
            "atlas.evolution.approval_manager",
            "tests/test_approval_manager.py",
        ),
        aliases=("approval", "owner_approval"),
        extends=("development.execution",),
    ),
    DevelopmentCapability(
        id="development.execution",
        name="Governed sandbox execution",
        purpose=(
            "Apply an approved change inside a disposable sandbox and verify it; "
            "never promote automatically."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.self_development_loop",
        entry="SelfDevelopmentLoop.run",
        dependencies=("governance.approval",),
        governance=("owner_approval", "sandbox_execution", "no_auto_promotion"),
        validated=True,
        evidence=(
            "atlas.evolution.self_development_loop",
            "docs/COMMAND_3B_SPECIALIST_OWNER_ACCEPTANCE.md",
        ),
        aliases=("execution", "governed_execution"),
        extends=("governance.promotion",),
    ),
    DevelopmentCapability(
        id="governance.promotion",
        name="Promotion boundary",
        purpose="Keep promotion a separate, explicit OWNER step; never automatic.",
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.evolution.promotion_gate",
        entry="PromotionGate",
        dependencies=(),
        governance=("no_auto_promotion",),
        validated=True,
        evidence=("atlas.evolution.promotion_gate", "tests/test_promotion_gate.py"),
        aliases=("promotion", "promotion_boundary"),
    ),
    DevelopmentCapability(
        id="development.extension",
        name="Governed capability extension",
        purpose=(
            "Describe how a capability is extended through the existing governed "
            "development architecture."
        ),
        status=CapabilityStatus.ACTIVE.value,
        owner_module="atlas.self_knowledge.development_capabilities",
        entry="DevelopmentCapabilityModel.extension_of",
        dependencies=(
            "development.planning",
            "governed.authoring",
            "development.execution",
        ),
        governance=("owner_approval", "sandbox_execution", "no_auto_promotion"),
        validated=True,
        evidence=(
            "atlas.self_knowledge.development_capabilities",
            "docs/COMMAND_5_DEVELOPMENT_CAPABILITY_CLOSURE.md",
        ),
        aliases=("extension", "capability_extension"),
    ),
    DevelopmentCapability(
        id="code.multifile",
        name="Multi-file authoring",
        purpose="Author a bounded change spanning more than one authorized target.",
        status=CapabilityStatus.FUTURE.value,
        owner_module="atlas.evolution.specialist_change_supplier",
        entry="(not implemented)",
        dependencies=("code.generate",),
        governance=("owner_approval", "sandbox_execution"),
        dependency_class=DEP_EXTERNAL_MODEL,
        validated=False,
        evidence=("docs/COMMAND_5_DEVELOPMENT_CAPABILITY_CLOSURE.md",),
        aliases=("multifile", "multi_file_authoring"),
        limitations=(
            "NOT YET JUSTIFIED: the one-file specialist contract is an intentional "
            "bounded safety restriction; no current real evidence proves it blocks "
            "the governed development objective.",
        ),
    ),
    DevelopmentCapability(
        id="development.autonomous",
        name="Autonomous self-development",
        purpose=(
            "Let Atlas plan and evolve itself end to end without a human in the "
            "loop."
        ),
        status=CapabilityStatus.FUTURE.value,
        owner_module="(future)",
        entry="(not implemented)",
        dependencies=("development.extension",),
        governance=("owner_approval", "sandbox_execution", "no_auto_promotion"),
        validated=False,
        evidence=("docs/COMMAND_5_DEVELOPMENT_CAPABILITY_CLOSURE.md",),
        aliases=("autonomous_self_development", "self_development"),
        limitations=(
            "NOT IMPLEMENTED. Atlas provides the self-knowledge foundation and the "
            "governed development loop, but it does not autonomously modify itself.",
        ),
    ),
)


def all_development_capabilities() -> tuple[DevelopmentCapability, ...]:
    """Return the bounded development capability catalogue (frozen order)."""
    return _CATALOGUE[:MAX_DEVELOPMENT_CAPABILITIES]


def find_development_capability(name: Any) -> DevelopmentCapability | None:
    """Resolve ``name`` to a development capability, or ``None`` (fail-closed)."""
    text = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    for capability in all_development_capabilities():
        keys = {capability.id.lower(), *capability.aliases}
        keys.add(capability.name.lower().replace("-", "_").replace(" ", "_"))
        if text in keys or text in {k.replace(".", "_") for k in keys}:
            return capability
    return None


class DevelopmentCapabilityModel:
    """Deterministic, read-only, evidence-backed view of Atlas's development
    capabilities.

    Query results are structured, deterministic and bounded; an unknown capability
    yields ``None``/``""``/``()`` — a capability is never invented (fail-closed).
    The model cannot mutate Atlas, approve, promote or bypass any boundary.
    """

    def __init__(
        self,
        *,
        specialist_enabled: bool = True,
        repair_wired: bool = True,
        governed_wired: bool = True,
    ) -> None:
        self._specialist_enabled = bool(specialist_enabled)
        self._repair_wired = bool(repair_wired)
        self._governed_wired = bool(governed_wired)
        self._by_id = {c.id: c for c in all_development_capabilities()}

    # -- provenance grounding ------------------------------------------------

    def _effective_status(self, capability: DevelopmentCapability) -> str:
        """The capability's status GROUNDED in the current wiring (never invented)."""
        if capability.status == CapabilityStatus.FUTURE.value:
            return CapabilityStatus.FUTURE.value
        if self._requires_specialist(capability) and not self._specialist_enabled:
            return CapabilityStatus.NOT_AVAILABLE.value
        if self._requires_repair(capability) and not self._repair_wired:
            return CapabilityStatus.NOT_AVAILABLE.value
        if capability.governance and not self._governed_wired:
            return CapabilityStatus.NOT_AVAILABLE.value
        return capability.status

    @staticmethod
    def _requires_specialist(capability: DevelopmentCapability) -> bool:
        return capability.dependency_class == DEP_EXTERNAL_MODEL

    @staticmethod
    def _requires_repair(capability: DevelopmentCapability) -> bool:
        return capability.id == "code.repair"

    # -- queries -------------------------------------------------------------

    def capabilities(self) -> tuple[DevelopmentCapability, ...]:
        """Every development capability in deterministic id order (bounded)."""
        return tuple(self._by_id[cid] for cid in sorted(self._by_id))

    def capability(self, name: Any) -> DevelopmentCapability | None:
        """The resolved capability, or ``None`` (fail-closed)."""
        return find_development_capability(name)

    def status_of(self, name: Any) -> str:
        """The GROUNDED status of ``name``, or ``""`` when unknown."""
        capability = self.capability(name)
        return self._effective_status(capability) if capability else ""

    def module_of(self, name: Any) -> str:
        """The owning module of ``name`` (where it lives), or ``""``."""
        capability = self.capability(name)
        return capability.owner_module if capability else ""

    def entry_of(self, name: Any) -> str:
        """The public entry/interface of ``name``, or ``""``."""
        capability = self.capability(name)
        return capability.entry if capability else ""

    def governance_of(self, name: Any) -> tuple[str, ...]:
        """The governance boundaries of ``name`` (``()`` when none/unknown)."""
        capability = self.capability(name)
        return capability.governance if capability else ()

    def dependencies_of(self, name: Any) -> tuple[str, ...]:
        """The declared dependencies of ``name`` (``()`` when none/unknown)."""
        capability = self.capability(name)
        return capability.dependencies if capability else ()

    def evidence_of(self, name: Any) -> tuple[str, ...]:
        """The evidence references of ``name`` (``()`` when unknown)."""
        capability = self.capability(name)
        return capability.evidence if capability else ()

    def validated(self, name: Any) -> bool:
        """True only when ``name`` is validated AND currently available."""
        capability = self.capability(name)
        if capability is None:
            return False
        return bool(capability.validated) and (
            self._effective_status(capability)
            in (CapabilityStatus.ACTIVE.value, CapabilityStatus.PARTIAL.value)
        )

    def extendable(self, name: Any) -> bool:
        """True when ``name`` is an ACTIVE capability that can be extended."""
        return self.status_of(name) in (
            CapabilityStatus.ACTIVE.value,
            CapabilityStatus.PARTIAL.value,
        )

    def extension_of(self, name: Any) -> str:
        """The capability-extension boundary for ``name`` (closed token).

        ``existing``  — Atlas already provides this capability (ACTIVE/PARTIAL);
        ``future``    — a legitimate capability that is NOT yet implemented;
        ``unavailable`` — declared but currently unwired;
        ``unknown``   — no such capability is declared (fail-closed).
        """
        capability = self.capability(name)
        if capability is None:
            return "unknown"
        status = self._effective_status(capability)
        if status == CapabilityStatus.FUTURE.value:
            return "future"
        if status == CapabilityStatus.NOT_AVAILABLE.value:
            return "unavailable"
        return "existing"

    def unavailable(self) -> tuple[DevelopmentCapability, ...]:
        """Declared capabilities that are currently UNAVAILABLE or FUTURE."""
        return tuple(
            capability
            for capability in self.capabilities()
            if self._effective_status(capability)
            in (CapabilityStatus.NOT_AVAILABLE.value, CapabilityStatus.FUTURE.value)
        )

    def boundary(self, name: Any) -> dict[str, Any]:
        """The bounded development boundary for one capability (structured).

        The authoritative information bridge for development planning: whether the
        capability exists, its status, where it lives, its interface, its
        governance and its dependencies. Unknown → ``{"found": False, ...}``.
        """
        capability = self.capability(name)
        if capability is None:
            return {"found": False, "query": _clean(name, 120)}
        payload = capability.to_dict()
        payload["found"] = True
        payload["effective_status"] = self._effective_status(capability)
        payload["extension"] = self.extension_of(name)
        return payload

    # -- projections ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self._by_id),
            "specialist_enabled": self._specialist_enabled,
            "repair_wired": self._repair_wired,
            "governed_wired": self._governed_wired,
            "capabilities": [
                {**c.to_dict(), "effective_status": self._effective_status(c)}
                for c in self.capabilities()
            ],
        }

    def to_operational_capabilities(self) -> tuple[OperationalCapability, ...]:
        """Project the development capabilities into the operational catalogue.

        Mergeable into the EXISTING unified capability model, so the EXISTING
        conversation self-knowledge surface answers about them with no new
        conversation code. Availability is GROUNDED in the current wiring.
        """
        projected: list[OperationalCapability] = []
        for capability in self.capabilities():
            status = self._effective_status(capability)
            projected.append(
                OperationalCapability(
                    id=capability.id,
                    name=capability.name,
                    description=capability.purpose,
                    category="development",
                    operations=(capability.entry,),
                    aliases=capability.aliases,
                    evidence=capability.evidence,
                    limitations=capability.limitations,
                    dependency=capability.dependency_class,
                    governed=bool(capability.governance),
                    available=status
                    in (CapabilityStatus.ACTIVE.value, CapabilityStatus.PARTIAL.value),
                    requires=tuple(
                        key
                        for key in capability.extends
                        if key in self._by_id
                    ),
                )
            )
        return tuple(projected)


def build_development_capability_model(
    *,
    specialist_enabled: bool = True,
    repair_wired: bool = True,
    governed_wired: bool = True,
) -> DevelopmentCapabilityModel:
    """Build the read-only development capability model (grounded in wiring)."""
    return DevelopmentCapabilityModel(
        specialist_enabled=specialist_enabled,
        repair_wired=repair_wired,
        governed_wired=governed_wired,
    )


__all__ = [
    "CapabilityStatus",
    "DevelopmentCapability",
    "DevelopmentCapabilityModel",
    "MAX_DEVELOPMENT_CAPABILITIES",
    "all_development_capabilities",
    "build_development_capability_model",
    "find_development_capability",
]
