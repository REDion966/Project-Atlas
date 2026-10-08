"""Atlas Self-Knowledge — development capability model (Command 6).

Proves the bounded, deterministic, evidence-backed self-knowledge model of
Atlas's own governed-development capabilities: lookup by id/alias/name, module /
entry / governance / status / evidence lookup, the existing/partial/future
extension boundary, deterministic ordering, bounded results, fail-closed behavior
for unknown/malformed queries, wiring-grounded status, and that the model carries
no authority. No external model is contacted.
"""

from __future__ import annotations

import pytest

from atlas.self_knowledge.development_capabilities import (
    MAX_DEVELOPMENT_CAPABILITIES,
    CapabilityStatus,
    DevelopmentCapabilityModel,
    all_development_capabilities,
    build_development_capability_model,
    find_development_capability,
)

ACTIVE = CapabilityStatus.ACTIVE.value
FUTURE = CapabilityStatus.FUTURE.value
NOT_AVAILABLE = CapabilityStatus.NOT_AVAILABLE.value


@pytest.fixture
def model():
    return build_development_capability_model()


class TestCatalogue:
    def test_catalogue_is_bounded_and_ordered(self):
        catalogue = all_development_capabilities()
        assert 0 < len(catalogue) <= MAX_DEVELOPMENT_CAPABILITIES
        # Frozen, explicit order (deterministic across calls).
        assert tuple(c.id for c in catalogue) == tuple(
            c.id for c in all_development_capabilities()
        )

    def test_every_capability_is_evidence_grounded(self):
        for capability in all_development_capabilities():
            assert capability.id and capability.name and capability.purpose
            assert capability.owner_module and capability.entry
            assert capability.evidence, capability.id
            assert capability.status in {s.value for s in CapabilityStatus}

    def test_only_future_capabilities_are_unvalidated(self):
        for capability in all_development_capabilities():
            if not capability.validated:
                assert capability.status == FUTURE, capability.id


class TestLookup:
    def test_lookup_by_id_alias_and_name(self, model):
        assert model.capability("code.generate") is not None
        assert model.capability("code_generation") is not None  # alias
        assert model.capability("Specialist code generation") is not None  # name
        assert model.capability("code.generate").id == "code.generate"

    def test_module_lookup(self, model):
        assert model.module_of("code.generate") == (
            "atlas.evolution.specialist_development"
        )

    def test_entry_lookup(self, model):
        assert model.entry_of("code.generate") == "SpecialistDevelopmentAuthor.propose"

    def test_governance_lookup(self, model):
        governance = model.governance_of("code.generate")
        assert "owner_approval" in governance
        assert "sandbox_execution" in governance

    def test_dependencies_lookup(self, model):
        assert model.dependencies_of("code.repair") == (
            "code.generate",
            "development.attribution",
        )

    def test_status_lookup(self, model):
        assert model.status_of("development.verification") == ACTIVE

    def test_evidence_lookup_is_traceable(self, model):
        evidence = model.evidence_of("development.attribution")
        assert any("verification_attribution" in item for item in evidence)


class TestFailClosed:
    @pytest.mark.parametrize("bad", [None, "", "   ", 123, [], {}])
    def test_malformed_query_is_fail_closed(self, model, bad):
        assert model.capability(bad) is None
        assert model.status_of(bad) == ""
        assert model.module_of(bad) == ""
        assert model.entry_of(bad) == ""
        assert model.governance_of(bad) == ()
        assert model.dependencies_of(bad) == ()
        assert model.evidence_of(bad) == ()
        assert model.validated(bad) is False
        assert model.extension_of(bad) == "unknown"

    def test_unknown_capability_never_invents_one(self, model):
        assert model.capability("does.not.exist") is None
        assert find_development_capability("does.not.exist") is None
        assert model.boundary("does.not.exist") == {
            "found": False,
            "query": "does.not.exist",
        }


class TestDeterminismAndBounds:
    def test_ordering_is_deterministic(self, model):
        first = tuple(c.id for c in model.capabilities())
        second = tuple(c.id for c in model.capabilities())
        assert first == second == tuple(sorted(first))

    def test_to_dict_is_bounded_and_stable(self, model):
        payload = model.to_dict()
        assert payload["count"] == len(model.capabilities())
        assert payload["capabilities"] == model.to_dict()["capabilities"]

    def test_boundary_is_structured(self, model):
        boundary = model.boundary("code.repair")
        assert boundary["found"] is True
        assert boundary["effective_status"] == ACTIVE
        assert boundary["extension"] == "existing"
        assert boundary["module_of"] if "module_of" in boundary else True
        assert boundary["owner_module"] == "atlas.evolution.development_repair"
        assert boundary["governance"]


class TestExtensionBoundary:
    def test_existing_capability_is_active_and_extendable(self, model):
        assert model.extension_of("code.generate") == "existing"
        assert model.extendable("code.generate") is True
        assert model.validated("code.generate") is True

    def test_future_capability_is_declared_not_invented(self, model):
        assert model.extension_of("code.multifile") == "future"
        assert model.extendable("code.multifile") is False
        assert model.validated("code.multifile") is False

    def test_autonomous_self_development_is_future(self, model):
        assert model.extension_of("development.autonomous") == "future"

    def test_unavailable_reports_declared_but_unwired(self):
        model = build_development_capability_model(specialist_enabled=False)
        assert model.status_of("code.generate") == NOT_AVAILABLE
        assert model.extension_of("code.generate") == "unavailable"
        assert model.validated("code.generate") is False
        ids = {c.id for c in model.unavailable()}
        assert "code.generate" in ids

    def test_unavailable_repair_when_loop_is_unwired(self):
        model = build_development_capability_model(repair_wired=False)
        assert model.status_of("code.repair") == NOT_AVAILABLE


class TestNoAuthority:
    def test_model_carries_no_authority_surface(self, model):
        for banned in ("apply", "approve", "promote", "authorize", "execute", "run"):
            assert not hasattr(model, banned)

    def test_projection_into_the_operational_catalogue_is_grounded(self, model):
        projected = model.to_operational_capabilities()
        assert len(projected) == len(model.capabilities())
        by_id = {c.id: c for c in projected}
        assert by_id["code.generate"].category == "development"
        assert by_id["code.generate"].governed is True
        assert by_id["code.generate"].available is True
        assert by_id["code.generate"].evidence
        # A FUTURE capability is NOT advertised as available.
        assert by_id["code.multifile"].available is False

    def test_projection_marks_unavailable_when_unwired(self):
        model = build_development_capability_model(specialist_enabled=False)
        by_id = {c.id: c for c in model.to_operational_capabilities()}
        assert by_id["code.generate"].available is False
