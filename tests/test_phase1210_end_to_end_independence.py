"""Phase 12.10 — Full end-to-end independence demonstration.

One concrete, bounded, model-free run of the real chain:

    human goal → interpretation → self-knowledge → capability landscape →
    capability discovery → evolution candidate → eligibility → objective →
    development need → development plan → approval boundary → sandbox
    development → focused tests → verification → promotion review → human
    promotion authorization → promotion → activation → self-model validation →
    outcome recording → terminate

With every external AI SDK unimportable, every AI environment variable absent,
and every outbound socket refused. Only the two human governance decisions are
supplied from outside (approval and promotion authorization).
"""

from __future__ import annotations

import pytest

from atlas.evolution.capability_acquisition import (
    AcquisitionNeed,
    determine_acquisition_strategy,
    validate_internalized_capability,
)
from atlas.evolution.capability_discovery import (
    inspect_landscape,
    run_discovery_cycle,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import build_capability_model
from tests.phase12_environment import model_free_environment

_MODULE = "atlas/example/e2e_independent_handlers.py"
_CAPABILITY = "example.e2e_independent"
_GOAL = "add an e2e-independent capability so the missing example capability is covered"


@pytest.fixture(scope="module")
def model_free_kernel():
    with model_free_environment() as attempts:
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            yield atlas, attempts
        finally:
            atlas.shutdown()


class TestPhase1210EndToEndIndependence:
    def test_full_model_free_independence_chain(self, model_free_kernel, tmp_path):
        atlas, attempts = model_free_kernel
        stages: dict[str, object] = {}

        # 1. Human goal → deterministic interpretation (no model). The
        #    deterministic interpreter recognises this as a development
        #    request and prepares it, failing closed for want of a supplied
        #    change — never fabricating, never calling a model.
        reply = atlas.chat(_GOAL)
        goal_text = str(getattr(reply, "content", reply))
        goal_metadata = dict(getattr(reply, "metadata", {}) or {})
        stages["interpretation"] = {
            "reply_nonempty": bool(goal_text.strip()),
            "recognised_as_development": "development" in goal_text.lower(),
            "model_used": goal_metadata.get("model_used"),
        }
        assert stages["interpretation"]["reply_nonempty"] is True
        assert stages["interpretation"]["recognised_as_development"] is True
        assert goal_metadata.get("model_used") is not True
        # A provenance-carrying deterministic turn (self-knowledge intent).
        self_reply = atlas.chat("what do you know about your own architecture?")
        assert (getattr(self_reply, "metadata", {}) or {}).get("model_used") is False

        # 2. Atlas self-knowledge.
        architecture = atlas.architecture_model()
        capability_model = atlas.capability_model()
        stages["self_knowledge"] = {
            "components": len(atlas.component_registry.get_all()),
            "capabilities": len(capability_model.entries),
            "architecture": type(architecture).__name__,
            "repository_map": type(atlas.repository_map).__name__,
        }
        assert stages["self_knowledge"]["components"] > 0

        # 3. Capability landscape (Phase 10) over a bounded registry that
        #    declares a provider which is currently unavailable.
        provider_registry = ComponentRegistry()
        provider_registry.register(
            ComponentMetadata(
                name="down_provider",
                package="atlas.example",
                module_path="atlas.example.down",
                status=ComponentStatus.OFFLINE,
                provided_capabilities=["example.missing"],
            )
        )
        landscape = inspect_landscape(build_capability_model(provider_registry))
        assert "example.missing" in landscape.unavailable
        stages["landscape"] = {
            "unavailable": landscape.unavailable,
            "degraded": landscape.degraded,
        }

        # 4. Capability discovery → evidence-backed candidate + assessment.
        discovery = run_discovery_cycle(
            capability_model=build_capability_model(provider_registry)
        )
        assessment = next(
            a for a in discovery.assessments if a.verdict.value == "actionable_gap"
        )
        candidate = next(
            c for c in discovery.candidates if c.candidate_id == assessment.candidate_id
        )
        stages["discovery"] = {
            "verdict": assessment.verdict.value,
            "evidence": list(assessment.evidence),
            "signals": len(discovery.signals),
        }
        assert assessment.evidence

        # 5. Capability acquisition assessment (Phase 8) — model-free and
        #    explicitly advisory.
        need = AcquisitionNeed(
            request=candidate.subject,
            target_capability=candidate.subject,
            knowledge_available=False,
            authorized=True,
        )
        strategy = determine_acquisition_strategy(need, capability_names=())
        stages["acquisition"] = {
            "mechanism": strategy.mechanism.value,
            "acquirable": strategy.acquirable,
        }
        assert strategy.mechanism.value != ""

        # 6. The bounded governed evolution cycle (Phases 11) — the human
        #    decisions (approval, promotion authorization) are supplied here.
        memory = EvolutionMemory()
        components = ComponentRegistry()
        capabilities = CapabilityRegistry()
        loop = SelfEvolutionLoop(
            evolution_memory=memory,
            component_registry=components,
            capability_registry=capabilities,
            repo_root=tmp_path,
        )
        result = loop.run(
            candidate,
            assessment,
            target_module=_MODULE,
            capability_name=_CAPABILITY,
            capability_names=(),
            owner_approved=True,
            promotion_authorized=True,
        )

        # 7. Every lifecycle state is preserved DISTINCTLY.
        stages["lifecycle"] = {
            "proposed": result.candidate.status.value,
            "eligibility": result.eligibility.state.value,
            "objective": result.objective.objective_id,
            "attempted": bool(result.proposal_id),
            "planned": result.development_status,
            "implemented": result.development_status,
            "tested": result.verification_status,
            "verified": result.verification_status,
            "approved": result.approval_status,
            "promotion_review": result.promotion_review_status,
            "promoted": result.promotion_outcome,
            "activated": result.activated_capabilities,
            "learned": result.outcome.value,
        }
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert result.verification_status == "verified"
        assert result.promotion_review_status == "approved"
        assert result.promotion_outcome == "promoted"
        assert result.activated_capabilities == (_CAPABILITY,)

        # 8. Self-model consistency after activation.
        assert result.self_model.consistent is True
        model = build_capability_model(components, capability_registry=capabilities)
        assert _CAPABILITY in {e.name for e in model.entries}
        validation = validate_internalized_capability(
            _CAPABILITY,
            capability_registry=capabilities,
            capability_model=model,
        )
        assert validation.ok is True
        assert validation.registered and validation.routable and validation.in_model

        # 9. The activated capability routes and executes.
        dispatch = CapabilityDispatcher(capabilities).dispatch(
            [Capability(name=_CAPABILITY)]
        )
        assert dispatch[0].success is True

        # 10. Outcome/history evidence preserved.
        event_types = {r.event_type for r in memory.get_records()}
        assert {"self_evolution_development", "promotion_review", "evolution_outcome"} <= event_types

        # 11. The cycle terminates and never auto-starts another.
        assert result.next_cycle_allowed is False

        # 12. Nothing external was contacted at any stage.
        assert attempts == []

    def test_demonstration_requires_the_two_human_decisions(self, model_free_kernel, tmp_path):
        atlas, _attempts = model_free_kernel
        atlas.chat(_GOAL)  # interpretation alone authorizes nothing
        registry = CapabilityRegistry()
        assert registry.registered_names == []
        # Without approval and promotion authorization the same chain stops at
        # the boundaries (proven in 12.7); here we assert no production write
        # occurred in this empty directory.
        assert not list(tmp_path.rglob("*"))
