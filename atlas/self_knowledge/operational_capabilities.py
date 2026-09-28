"""Atlas Self-Knowledge — Operational Capability catalogue (Step 12).

The single bounded, deterministic source of truth for Atlas's OPERATIONAL
(conversational) capabilities: the things Atlas can actually be asked to do and
answer through the existing conversation pipeline (investigate, research, plan,
approve, multi-step, clarify, …).

Why this exists
---------------
Atlas already models its *registered* implementation surface — the reasoning
capability handlers, component-provided capabilities and tools — in
:mod:`atlas.self_knowledge.capability_model`. What it did NOT have was one
identity for the operational abilities the conversation layer genuinely
supports: those were scattered across a hard-coded help string, the
self-knowledge topics and the implicit routes. As a result a capability question
about them ("is investigation available?", "explain investigate") could not be
answered from the canonical model at all, while the conversational inventory and
the model disagreed about what exists.

This module is representation only:

* deterministic, model-independent, stdlib only — no I/O, no clock, no model;
* it never registers, executes, authorizes or mutates anything, and grants no
  authority;
* every entry is grounded in an EXISTING route/handler/module of Atlas (the
  ``evidence`` field names the real backing implementation), so a capability is
  never claimed merely because a name exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

#: Bound on the catalogue (a bounded, explicit list — not a discovery scan).
MAX_OPERATIONAL_CAPABILITIES: int = 32

#: Dependency labels (mirror ``atlas.self_knowledge.capability_model``).
DEP_DETERMINISTIC: str = "deterministic"
DEP_EXTERNAL_MODEL: str = "external_model_dependent"


@dataclass(frozen=True, slots=True)
class OperationalCapability:
    """One bounded, evidence-grounded operational capability (facts only)."""

    id: str
    name: str
    description: str
    category: str
    operations: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    dependency: str = DEP_DETERMINISTIC
    governed: bool = False
    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "operations": list(self.operations),
            "aliases": list(self.aliases),
            "evidence": list(self.evidence),
            "limitations": list(self.limitations),
            "dependency": self.dependency,
            "governed": self.governed,
            "available": self.available,
        }


#: The bounded operational capability catalogue. Every entry names the EXISTING
#: route/handler/module that implements it in ``evidence``.
_OPERATIONAL_CAPABILITIES: tuple[OperationalCapability, ...] = (
    OperationalCapability(
        id="greeting",
        name="Greeting",
        description="Respond deterministically to a greeting.",
        category="conversation",
        operations=("greet",),
        evidence=("atlas.conversation.builtin_response",),
    ),
    OperationalCapability(
        id="help",
        name="Help / supported commands",
        description="Explain what Atlas can be asked to do.",
        category="conversation",
        operations=("help",),
        aliases=("commands",),
        evidence=("atlas.conversation.builtin_response",),
    ),
    OperationalCapability(
        id="identity",
        name="Identity",
        description="State what Atlas is and how it operates.",
        category="self_knowledge",
        operations=("identity",),
        evidence=("atlas.conversation.builtin_response",),
    ),
    OperationalCapability(
        id="status",
        name="Runtime status",
        description="Report bounded runtime status (mode, registries, service count).",
        category="self_knowledge",
        operations=("status",),
        evidence=("atlas.conversation.builtin_response",),
    ),
    OperationalCapability(
        id="capabilities",
        name="Capability inventory",
        description="List the capabilities Atlas is confirmed to have.",
        category="self_knowledge",
        operations=("list_capabilities",),
        evidence=(
            "atlas.conversation.builtin_response",
            "atlas.self_knowledge.capability_model",
        ),
    ),
    OperationalCapability(
        id="capability_detail",
        name="Capability detail",
        description="Explain one capability or tool from the unified capability model.",
        category="self_knowledge",
        operations=("explain_capability",),
        evidence=(
            "atlas.conversation.builtin_response",
            "atlas.self_knowledge.capability_model",
        ),
    ),
    OperationalCapability(
        id="self_knowledge",
        name="Self-knowledge",
        description="Answer bounded questions about Atlas's own mechanisms.",
        category="self_knowledge",
        operations=("explain_self",),
        evidence=(
            "atlas.conversation.builtin_response",
            "atlas.self_knowledge.architecture_model",
        ),
    ),
    OperationalCapability(
        id="architecture",
        name="Architecture self-understanding",
        description="Explain Atlas's components and their relationships.",
        category="self_knowledge",
        operations=("describe_architecture", "relationship"),
        evidence=("atlas.self_knowledge.architecture_model",),
    ),
    OperationalCapability(
        id="recall",
        name="Memory / knowledge recall",
        description="Recall a remembered topic or a validated knowledge answer.",
        category="memory",
        operations=("recall_topic", "recall_knowledge"),
        evidence=(
            "atlas.conversation.builtin_response",
            "atlas.memory.service.memory_manager_service",
        ),
    ),
    OperationalCapability(
        id="investigate",
        name="Investigation",
        description="Run a read-only investigation of a subject in the repository.",
        category="investigation",
        operations=("investigate",),
        aliases=("investigation", "investigate"),
        evidence=("atlas.conversation.investigation",),
        limitations=("Read-only: it inspects and reports; it never modifies anything.",),
    ),
    OperationalCapability(
        id="repository_impact",
        name="Repository impact analysis",
        description="Report a module's dependencies/dependents and change impact.",
        category="investigation",
        operations=("impact_analysis",),
        aliases=("impact", "repository_impact"),
        evidence=("atlas.conversation.repository_impact",),
        limitations=("Read-only analysis of the cached repository map.",),
    ),
    OperationalCapability(
        id="research",
        name="Research / knowledge retrieval",
        description="Answer an information request from validated knowledge (local-first).",
        category="knowledge",
        operations=("research", "retrieve_knowledge"),
        aliases=("knowledge", "knowledge_retrieval", "research"),
        evidence=(
            "atlas.research.knowledge_decision",
            "atlas.research.validated_retrieval",
        ),
        limitations=(
            "Local-first: it reports its own sufficiency and never fabricates an "
            "answer; external acquisition stays deny-by-default.",
        ),
    ),
    OperationalCapability(
        id="knowledge_acquisition",
        name="Governed external acquisition",
        description="Acquire external knowledge through the governed D2 boundary.",
        category="knowledge",
        operations=("governed_acquisition",),
        evidence=("atlas.research.acquisition",),
        limitations=("Deny-by-default: requires an authorized source and the D2 boundary.",),
        governed=True,
    ),
    OperationalCapability(
        id="goal_orchestration",
        name="Goal-centred orchestration",
        description="Sequence a bounded multi-stage goal over read-only steps.",
        category="orchestration",
        operations=("multi_stage_goal", "resume_plan"),
        aliases=("orchestration", "goal", "goal_execution"),
        evidence=(
            "atlas.orchestration.executor",
            "atlas.orchestration.goal_plan",
        ),
    ),
    OperationalCapability(
        id="multi_step",
        name="Multi-intent / multi-step understanding",
        description="Read the distinct ordered steps of one request and route them.",
        category="conversation",
        operations=("multi_intent", "multi_step"),
        aliases=("multi_intent",),
        evidence=("atlas.conversation.multi_step",),
    ),
    OperationalCapability(
        id="clarify",
        name="Ambiguity clarification",
        description="Ask a bounded clarification when the context is genuinely ambiguous.",
        category="conversation",
        operations=("clarify",),
        aliases=("clarification",),
        evidence=("atlas.conversation.clarification",),
    ),
    OperationalCapability(
        id="reference",
        name="Context & reference understanding",
        description="Resolve follow-up references against the retained conversation state.",
        category="conversation",
        operations=("resolve_reference", "topic_return"),
        aliases=("reference", "follow_up"),
        evidence=(
            "atlas.conversation.reference_resolution",
            "atlas.conversation.world_state",
        ),
    ),
    OperationalCapability(
        id="plan",
        name="Development proposal preparation",
        description="Prepare a governed development proposal from an investigation.",
        category="development",
        operations=("prepare_development_proposal",),
        aliases=("planning", "development", "development_proposal"),
        evidence=("atlas.conversation.investigation",),
        limitations=("A proposal is evidence-only and requires explicit OWNER approval.",),
        governed=True,
    ),
    OperationalCapability(
        id="approve",
        name="Approval / rejection",
        description="Record an OWNER approval or rejection of a pending request.",
        category="governance",
        operations=("approve", "reject"),
        aliases=("approval",),
        evidence=("atlas.evolution.approval_manager",),
        limitations=("Explicit OWNER decision only; approval by itself never executes.",),
        governed=True,
    ),
    OperationalCapability(
        id="execute",
        name="Governed execution",
        description="Carry out an already-approved plan inside the sandbox.",
        category="governance",
        operations=("execute_approved",),
        aliases=("execution",),
        evidence=("atlas.evolution",),
        limitations=("Sandbox-only; it never writes to the live repository.",),
        governed=True,
    ),
    OperationalCapability(
        id="verify",
        name="Verification",
        description="Verify an already-completed development result.",
        category="governance",
        operations=("verify",),
        aliases=("verification",),
        evidence=("atlas.evolution",),
        governed=True,
    ),
    OperationalCapability(
        id="report",
        name="Lifecycle report",
        description="Report the final state of the development lifecycle.",
        category="governance",
        operations=("report",),
        evidence=("atlas.evolution",),
        governed=True,
    ),
    OperationalCapability(
        id="open_conversation",
        name="Open-ended conversation",
        description="Answer a genuinely open turn through the optional model provider seam.",
        category="conversation",
        operations=("open_conversation",),
        aliases=("open_ended_conversation",),
        evidence=("atlas.conversation.conversation_service", "atlas.ai"),
        limitations=(
            "Requires an optional external AI model; unavailable without one, and "
            "model output is text only and carries no authority.",
        ),
        dependency=DEP_EXTERNAL_MODEL,
    ),
)


def all_operational_capabilities() -> tuple[OperationalCapability, ...]:
    """Return the bounded operational capability catalogue (frozen order)."""
    return _OPERATIONAL_CAPABILITIES[:MAX_OPERATIONAL_CAPABILITIES]


def project_operational_capabilities(
    *,
    external_provider: bool = False,
    governed_wired: bool = True,
) -> tuple[OperationalCapability, ...]:
    """Return the catalogue with each entry's availability GROUNDED in wiring.

    Only actual, current evidence changes an entry's availability:

      * a capability whose backing route is deterministic and wired is
        ``available``;
      * the optional model-backed open conversation is ``available`` only when an
        external provider is actually configured (otherwise it is truthfully
        ``unavailable``);
      * a governed capability is ``unavailable`` when its governed boundary is
        not wired, and ``available`` (still approval-gated) when it is.
    """
    projected: list[OperationalCapability] = []
    for capability in all_operational_capabilities():
        available = capability.available
        if capability.dependency == DEP_EXTERNAL_MODEL:
            available = bool(external_provider)
        elif capability.governed:
            available = bool(governed_wired)
        projected.append(
            OperationalCapability(
                id=capability.id,
                name=capability.name,
                description=capability.description,
                category=capability.category,
                operations=capability.operations,
                aliases=capability.aliases,
                evidence=capability.evidence,
                limitations=capability.limitations,
                dependency=capability.dependency,
                governed=capability.governed,
                available=available,
            )
        )
    return tuple(projected)


def find_operational_capability(
    name: Any,
    capabilities: "tuple[OperationalCapability, ...] | None" = None,
) -> Optional[OperationalCapability]:
    """Return the operational capability ``name`` resolves to, or ``None``.

    Resolution is deterministic and exact-ish: the id, an alias, or a
    normalized name match. An unknown name returns ``None`` (fail closed) — a
    capability is never invented.
    """
    text = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    catalogue = capabilities if capabilities is not None else all_operational_capabilities()
    for capability in catalogue:
        keys = {capability.id, *capability.aliases}
        keys.add(capability.name.lower().replace("-", "_").replace(" ", "_"))
        if text in keys:
            return capability
    return None
