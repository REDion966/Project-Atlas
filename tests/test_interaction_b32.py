"""P3/B3.2 — Interaction → learning integration tests.

Proves the B3.2 flow end-to-end with REAL seams:
  SessionContext → B3.1 InteractionRecorder → InteractionRepository
  → InteractionLearningBridge → existing LearningMemory (LearningInsight)
  → principal-scoped planning-context provider

Covers: preference/correction learning integration, principal isolation,
provenance + session attribution preservation, repeated/bounded handling,
empty/no-record behavior, fail-closed invalid input, existing-learning
compatibility, no authority escalation, no execution/governance bypass,
and backward compatibility.
"""

from __future__ import annotations

import pytest

from atlas.authority.service import AuthorityService
from atlas.interaction import (
    InteractionLearningBridge,
    InteractionRecorder,
    InteractionRepository,
)
from atlas.learning_engine.learning_memory import LearningMemory
from atlas.learning_engine.models import (
    LearningCategory,
    LearningInsight,
)
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


def _make_ctx(owner=False, user_id="alice", user_name="Alice"):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if owner:
        session = manager.create_session("owner")
    else:
        authority.add_user(user_name, principal_id=user_id)
        session = manager.create_session(user_id)
    return SessionContext.from_session(session)


def _recorder_and_bridge():
    repo = InteractionRepository()
    recorder = InteractionRecorder(repository=repo)
    memory = LearningMemory()
    bridge = InteractionLearningBridge(repository=repo, learning_memory=memory)
    return repo, recorder, memory, bridge


# ---------------------------------------------------------------------------
# Preference → learning integration
# ---------------------------------------------------------------------------

class TestPreferenceLearningIntegration:
    def test_preference_flows_into_learning_memory(self):
        ctx = _make_ctx(owner=False)
        repo, recorder, memory, bridge = _recorder_and_bridge()
        recorder.record_preference(ctx, "response_length", "concise")

        written = bridge.flush_to_learning()
        assert written == 1
        insights = memory.get_insights(10)
        assert len(insights) == 1
        i = insights[0]
        assert i.title.startswith("Preference:")
        assert i.description == "concise"
        # Provenance preserved in metadata.
        assert i.metadata["principal_id"] == "alice"
        assert i.metadata["authority"] == "user"
        assert i.metadata["session_id"] == ctx.session_id

    def test_preference_metadata_roundtrip(self):
        ctx = _make_ctx(owner=False)
        repo, recorder, memory, bridge = _recorder_and_bridge()
        pref = recorder.record_preference(ctx, "tone", "casual")
        bridge.flush_to_learning()
        insights = memory.get_insights(10)
        assert insights[0].metadata["record_id"] == pref.record_id
        assert insights[0].metadata["source_record_kind"] == "preference"


# ---------------------------------------------------------------------------
# Correction → learning integration
# ---------------------------------------------------------------------------

class TestCorrectionLearningIntegration:
    def test_correction_flows_into_learning_memory(self):
        ctx = _make_ctx(owner=False)
        repo, recorder, memory, bridge = _recorder_and_bridge()
        recorder.record_correction(
            ctx,
            target="memory recall",
            description="returned the wrong episode",
            correction="use the 2026 episode",
        )

        written = bridge.flush_to_learning()
        assert written == 1
        insights = memory.get_insights(10)
        assert len(insights) == 1
        i = insights[0]
        assert i.title.startswith("Correction:")
        assert "wrong episode" in i.description
        assert i.metadata["principal_id"] == "alice"
        assert i.metadata["authority"] == "user"


# ---------------------------------------------------------------------------
# Principal / session isolation
# ---------------------------------------------------------------------------

class TestIsolation:
    def test_planning_context_is_principal_scoped(self):
        ctx_alice = _make_ctx(owner=False, user_id="alice")
        ctx_bob = _make_ctx(owner=False, user_id="bob", user_name="Bob")
        repo, recorder, memory, bridge = _recorder_and_bridge()
        recorder.record_preference(ctx_alice, "tone", "casual")
        recorder.record_preference(ctx_bob, "tone", "formal")

        ctx_alice_provider = bridge.planning_context_provider("alice")
        ctx_bob_provider = bridge.planning_context_provider("bob")
        alice_ctx = ctx_alice_provider()
        bob_ctx = ctx_bob_provider()

        # No cross-principal bleed.
        assert [p["value"] for p in alice_ctx["preferences"]] == ["casual"]
        assert [p["value"] for p in bob_ctx["preferences"]] == ["formal"]

    def test_provenance_preserved_per_principal(self):
        ctx = _make_ctx(owner=False)
        repo, recorder, memory, bridge = _recorder_and_bridge()
        recorder.record_preference(ctx, "k", "v")
        provider = bridge.planning_context_provider("alice")
        ctx_out = provider()
        assert ctx_out["principal_id"] == "alice"
        assert ctx_out["preferences"][0]["provenance"]["principal_id"] == "alice"


# ---------------------------------------------------------------------------
# Repeated / bounded behavior
# ---------------------------------------------------------------------------

class TestRepeatedAndBounded:
    def test_repeated_preferences_all_integrated(self):
        ctx = _make_ctx(owner=False)
        repo, recorder, memory, bridge = _recorder_and_bridge()
        for i in range(5):
            recorder.record_preference(ctx, f"key{i}", f"value{i}")
        written = bridge.flush_to_learning()
        assert written == 5
        assert memory.insight_count == 5

    def test_empty_no_records_flush_is_noop(self):
        repo, recorder, memory, bridge = _recorder_and_bridge()
        assert bridge.flush_to_learning() == 0
        assert memory.insight_count == 0


# ---------------------------------------------------------------------------
# Fail-closed behavior
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_missing_session_not_captured_not_integrated(self):
        repo, recorder, memory, bridge = _recorder_and_bridge()
        assert recorder.record_preference(None, "k", "v") is None
        assert recorder.record_correction(None, "t", "d", "c") is None
        assert bridge.flush_to_learning() == 0
        assert memory.insight_count == 0

    def test_planning_context_provider_fail_closed_on_empty_principal(self):
        repo, recorder, memory, bridge = _recorder_and_bridge()
        assert bridge.planning_context_provider("") is None
        assert bridge.planning_context_provider(None) is None

    def test_bridge_requires_valid_repository(self):
        with pytest.raises(ValueError):
            InteractionLearningBridge(repository=None, learning_memory=None)

    def test_missing_learning_memory_degrades_gracefully(self):
        ctx = _make_ctx(owner=False)
        repo = InteractionRepository()
        recorder = InteractionRecorder(repository=repo)
        recorder.record_preference(ctx, "k", "v")
        bridge = InteractionLearningBridge(repository=repo, learning_memory=None)
        assert bridge.flush_to_learning() == 0  # no-op, never raises


# ---------------------------------------------------------------------------
# No authority escalation / no execution bypass
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_user_record_never_elevates_authority(self):
        ctx = _make_ctx(owner=False)
        repo, recorder, memory, bridge = _recorder_and_bridge()
        pref = recorder.record_preference(ctx, "priority", "critical")
        recorder.record_correction(ctx, "t", "d", "c")
        bridge.flush_to_learning()
        # The stored insight authority is the originating USER authority.
        for i in memory.get_insights(10):
            assert i.metadata["authority"] == "user"
        # The record itself is immutable and stays attributed to alice.
        assert pref.principal_id == "alice"

    def test_bridge_has_no_execution_or_governance_references(self):
        repo, recorder, memory, bridge = _recorder_and_bridge()
        for attr in (
            "execution_gateway",
            "application_engine",
            "approval_manager",
            "rule_engine",
            "dispatcher",
            "tool_executor",
        ):
            assert not hasattr(bridge, attr)


# ---------------------------------------------------------------------------
# Existing learning compatibility / backward compatibility
# ---------------------------------------------------------------------------

class TestCompatibility:
    def test_flush_coexists_with_existing_learning_memory(self):
        ctx = _make_ctx(owner=False)
        repo, recorder, memory, bridge = _recorder_and_bridge()
        # Existing learning insight pre-stored.
        memory.store_insights(
            [
                LearningInsight(
                    insight_id="LRN-EXISTING-1",
                    category=LearningCategory.OPTIMIZATION,
                    title="Existing",
                    description="pre-existing insight",
                )
            ]
        )
        recorder.record_preference(ctx, "k", "v")
        bridge.flush_to_learning()
        assert memory.insight_count == 2
        # Existing insight untouched.
        existing = [i for i in memory.get_insights(10) if i.insight_id == "LRN-EXISTING-1"]
        assert len(existing) == 1
        assert existing[0].description == "pre-existing insight"

    def test_kernel_wires_interaction_seams(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            assert atlas._interaction_repository is not None
            assert atlas._interaction_recorder is not None
            assert atlas._interaction_learning_bridge is not None
            # Not registered in the container (exact-set-tested elsewhere).
            assert "interaction" not in atlas.container.names()
            # The provider is advisory and bound to the kernel session.
            provider = atlas._interaction_context_provider
            assert provider is not None
            ctx = provider()
            assert isinstance(ctx, dict)
        finally:
            atlas.shutdown()
        assert atlas._interaction_learning_bridge is None

    def test_kernel_end_to_end_capture_and_integration(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            atlas.authority_service.add_user("Carol", principal_id="carol")
            ctx = atlas.start_user_session("carol")
            # Real recorder + real LearningMemory via the bridge.
            atlas._interaction_recorder.record_preference(ctx, "tone", "helpful")
            atlas._interaction_recorder.record_correction(
                ctx, "search", "wrong result", "prefer semantic search"
            )
            before = atlas._learning_engine.memory.insight_count
            written = atlas._interaction_learning_bridge.flush_to_learning()
            assert written == 2
            after = atlas._learning_engine.memory.insight_count
            # The bridge wrote exactly the two new records; the memory may
            # already hold restored insights from the shared SQLite DB, so
            # compare the delta rather than an absolute count.
            assert after - before >= 2
            # The newly written insights carry the new records' provenance.
            insights = atlas._learning_engine.memory.get_insights(20)
            new_prefs = [
                i for i in insights
                if i.title.startswith("Preference:")
                and i.metadata.get("principal_id") == "carol"
            ]
            new_corrs = [
                i for i in insights
                if i.title.startswith("Correction:")
                and i.metadata.get("principal_id") == "carol"
            ]
            assert new_prefs, "expected a carol preference insight"
            assert new_corrs, "expected a carol correction insight"
            assert new_corrs[0].metadata["authority"] == "user"
        finally:
            atlas.shutdown()
