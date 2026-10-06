"""Live integration of architectural target resolution into the dev path.

The resolver itself is validated in ``test_architecture_target_resolution``.
These tests cover the INTEGRATION: that the target expression the EXISTING L3
language pipeline already produced reaches the resolver and then architecture
grounding, and that every safety property survives the wiring.

In particular they pin:

* an explicitly named component grounds the area it actually owns;
* an AMBIGUOUS target grounds NOTHING (no guessed architecture area);
* an UNRESOLVED target grounds NOTHING and falls back to the EXISTING raw-token
  behaviour rather than inventing an area;
* the raw-token fallback is unchanged when no target resolves;
* a stale carried-over ``current_subject`` can never override the target the user
  just named;
* nothing here contacts a model, approves, executes or promotes anything.
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, r"F:\Project Atlas")


@pytest.fixture(scope="module")
def atlas():
    from atlas.kernel.atlas import Atlas

    instance = Atlas()
    instance.start()
    try:
        _ = instance.repository_map
        yield instance
    finally:
        instance.shutdown()


def _ground(atlas, text):
    """Run the real production path and return (task_type, resolution, areas)."""
    spec = atlas._conversation._intake(text)
    surface = atlas._utterance_target_surface(spec)
    resolution = atlas._resolve_architectural_target(surface)
    result = atlas.capability_specification(text, target_surface=surface)
    return (
        getattr(spec.task_type, "value", None),
        surface,
        resolution,
        tuple(getattr(result, "affected_areas", ()) or ()),
    )


class TestLiveTargetReachesGrounding:
    def test_named_component_grounds_the_area_it_owns(self, atlas):
        task_type, surface, resolution, areas = _ground(
            atlas, "Improve the conversation service capability while preserving the contract."
        )
        assert task_type == "development_request"
        assert resolution is not None and resolution.is_resolved
        assert resolution.canonical_id == "conversation_service"
        assert any("conversation_service" in area for area in areas), areas

    def test_a_second_component_resolves_its_own_area(self, atlas):
        _t, _s, resolution, areas = _ground(
            atlas, "Improve the knowledge manager capability while preserving the contract."
        )
        assert resolution is not None and resolution.is_resolved
        assert resolution.canonical_id == "knowledge_manager"
        assert any("knowledge_manager" in area for area in areas), areas


class TestAmbiguitySurvivesIntegration:
    def test_ambiguous_target_grounds_nothing(self, atlas):
        task_type, _s, resolution, areas = _ground(
            atlas, "Improve research capability while preserving the contract."
        )
        assert task_type == "development_request"
        assert resolution is not None and resolution.is_ambiguous
        assert resolution.canonical_id == ""
        # Nothing may be guessed into an architecture area.
        assert areas == (), areas


class TestFailClosedSurvivesIntegration:
    def test_unresolved_target_does_not_fabricate(self, atlas):
        task_type, _s, resolution, areas = _ground(
            atlas,
            "Improve the zzz nonexistent widget capability while preserving the contract.",
        )
        assert task_type == "development_request"
        assert resolution is None or resolution.is_unresolved
        assert areas == (), areas


class TestRawTokenFallbackPreserved:
    def test_existing_token_behaviour_is_unchanged(self, atlas):
        """No such component exists, so resolution is UNRESOLVED and the EXISTING
        raw-token loop still produces exactly what it produced before."""
        _t, _s, resolution, areas = _ground(
            atlas,
            "Improve the development planner capability while preserving the contract.",
        )
        assert resolution is None or resolution.is_unresolved
        # The prior raw-token behaviour is preserved (not empty, not invented).
        assert areas == ("atlas.research.capability_handlers",), areas


class TestNoStaleStateContamination:
    def test_stale_current_subject_never_overrides_the_named_target(self, atlas):
        """Establish target A, switch topic, then name target B explicitly.

        The grounding must follow B. A stale ``current_subject`` left over from A
        must not redirect the architecture area.
        """
        atlas.chat("Investigate the conversation service.")
        stale = atlas._conversation.state_manager.state.current_subject

        task_type, _s, resolution, areas = _ground(
            atlas, "Improve the knowledge manager capability while preserving the contract."
        )
        assert task_type == "development_request"
        assert resolution is not None and resolution.is_resolved
        assert resolution.canonical_id == "knowledge_manager"
        assert any("knowledge_manager" in area for area in areas), areas
        if stale:
            # The carried-over subject must not appear as the chosen target.
            assert resolution.canonical_id != stale


class TestGovernanceUnchanged:
    def test_resolution_creates_no_approval_or_promotion(self, atlas):
        """Resolution must ADD no promotion review.

        Measured as a delta: the module-scoped kernel is shared with the other
        tests in this file, so an absolute count would reflect earlier tests
        rather than this resolution.
        """
        before = len(atlas.pending_promotion_reviews())
        _ground(
            atlas,
            "Improve the conversation service capability while preserving the contract.",
        )
        assert len(atlas.pending_promotion_reviews()) == before

    def test_model_assistance_stays_off(self, atlas):
        assert not bool(
            atlas._config.get("ai", "external_providers", default=False)
        )

    def test_blank_and_missing_target_surface_are_safe(self, atlas):
        assert atlas._utterance_target_surface(None) == ""
        assert atlas._resolve_architectural_target("") is None
        assert atlas._resolve_architectural_target(None) is None
