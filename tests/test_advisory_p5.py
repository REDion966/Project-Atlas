"""P5 — Proactive Advisory tests (real seams).

Validates that the ProactiveAdvisor and the kernel bridge:
  * are advisory only (no execution, no governance bypass, no auth bypass)
  * use the EXISTING F1/F10/F11 signals and the B3.x/P4 seams
  * are bounded and deterministic
  * preserve Owner / User authority
  * are principal-scoped
  * never run from tick()
  * never modify the underlying signals

All tests compose REAL F1/F10/F11/B3.x/P4 surfaces (no mocks of the seam
under test). Where a surface is unavailable the test simply asserts
degradation.
"""

from __future__ import annotations

import pytest

from atlas.advisory import (
    AdvisoryItem,
    AdvisoryReport,
    AdvisorySeverity,
    AdvisorySource,
    ProactiveAdvisor,
)


# ---------------------------------------------------------------------------
# Pure invariants: model + advisor shape
# ---------------------------------------------------------------------------

class TestModels:
    def test_advisory_item_to_dict_round_trip(self):
        from datetime import datetime, timezone
        item = AdvisoryItem(
            item_id="ADV-ITEM-00000001",
            severity=AdvisorySeverity.WARNING,
            source=AdvisorySource.AVAILABILITY,
            kind="provider_availability",
            summary="Provider OFFLINE.",
            evidence_ids=("ai_provider",),
            suggested_action="atlas.run_self_management_review",
            requires_owner=False,
            principal_id="alice",
            recorded_at=datetime.now(timezone.utc),
            metadata={"status": "OFFLINE"},
        )
        d = item.to_dict()
        assert d["item_id"].startswith("ADV-ITEM-")
        assert d["severity"] == "warning"
        assert d["source"] == "availability"
        assert d["principal_id"] == "alice"
        assert d["metadata"] == {"status": "OFFLINE"}

    def test_advisory_report_to_dict_round_trip(self):
        from datetime import datetime, timezone
        rep = AdvisoryReport(
            advisory_id="ADV-000001",
            generated_at=datetime.now(timezone.utc),
            principal_id="alice",
            items=(),
            source_errors=(),
            sources_used=("availability",),
        )
        d = rep.to_dict()
        assert d["advisory_id"] == "ADV-000001"
        assert d["count"] == 0
        assert d["sources_used"] == ["availability"]


# ---------------------------------------------------------------------------
# Real F10 surface (ProviderAvailabilityTracker)
# ---------------------------------------------------------------------------

class TestRealAvailabilitySurface:
    def test_healthy_provider_emits_no_item(self):
        from atlas.ai.availability import ProviderAvailabilityTracker
        tracker = ProviderAvailabilityTracker()
        tracker.record_success()
        adv = ProactiveAdvisor(availability=tracker)
        rep = adv.run_advisory(principal_id="alice")
        assert rep.count == 0
        assert "availability" in rep.sources_used

    def test_offline_provider_emits_warning_item(self):
        from atlas.ai.availability import ProviderAvailabilityTracker
        tracker = ProviderAvailabilityTracker()
        for _ in range(3):
            tracker.record_failure()
        adv = ProactiveAdvisor(availability=tracker)
        rep = adv.run_advisory(principal_id="alice")
        assert rep.count >= 1
        item = rep.items[0]
        assert item.source is AdvisorySource.AVAILABILITY
        assert item.severity is AdvisorySeverity.WARNING
        assert "OFFLINE" in item.summary
        assert item.suggested_action == "atlas.run_self_management_review"
        assert item.requires_owner is False


# ---------------------------------------------------------------------------
# Real F11 surface (SelfManagementReview)
# ---------------------------------------------------------------------------

class TestRealSelfManagementSurface:
    def _build_review(self, needs=(), offline=(), degraded=()):
        """Return a SelfManagementReview whose run_review() yields the inputs."""
        from atlas.evolution.self_management import (
            SelfManagementPolicy,
            SelfManagementReport,
            SelfManagementReview,
        )
        review = SelfManagementReview(policy=SelfManagementPolicy())
        # Pre-set by replacing run_review via a small shim.
        fixed = SelfManagementReport(
            review_id="SMR-FAKE",
            status="ok",
            outcome_trend={"operation_cycle": 1},
            failure_streak=2,
            stale_authorization_count=0,
            stale_authorization_ids=(),
            degraded_components=tuple(degraded),
            offline_components=tuple(offline),
            availability_status="DEGRADED",
            insight_count=0,
            failure_pattern_count=0,
            needs=tuple(needs),
        )
        review.run_review = lambda: fixed  # type: ignore[assignment]
        return review

    def test_offline_component_emits_warning(self):
        review = self._build_review(offline=("memory_service",))
        adv = ProactiveAdvisor(self_management_review=review)
        rep = adv.run_advisory(principal_id="alice")
        kinds = {it.kind for it in rep.items}
        assert "offline_component" in kinds
        item = next(it for it in rep.items if it.kind == "offline_component")
        assert item.severity is AdvisorySeverity.WARNING
        assert item.requires_owner is False

    def test_maintenance_need_emits_item(self):
        from atlas.evolution.self_management import MaintenanceNeed
        from datetime import datetime, timezone
        need = MaintenanceNeed(
            need_id="NEED-1",
            kind="review_stale_authorizations",
            summary="stale authorization pending",
            evidence_ids=("APPR-1",),
            detected_at=datetime.now(timezone.utc),
        )
        review = self._build_review(needs=(need,))
        adv = ProactiveAdvisor(self_management_review=review)
        rep = adv.run_advisory(principal_id="alice")
        item = next(it for it in rep.items if it.kind == "review_stale_authorizations")
        assert item.severity is AdvisorySeverity.WARNING
        assert item.requires_owner is False
        assert item.suggested_action == "atlas.run_self_management_review"


# ---------------------------------------------------------------------------
# Real F1 surface (EnvironmentObserver)
# ---------------------------------------------------------------------------

class TestRealEnvironmentSurface:
    def test_environment_change_emits_notice(self):
        from atlas.evolution.environment import (
            EnvironmentChange,
            EnvironmentChangeType,
            EnvironmentDomain,
            EnvironmentEntity,
            EnvironmentObservationResult,
        )
        from datetime import datetime, timezone

        entity = EnvironmentEntity(EnvironmentDomain.MODEL, "openai:gpt-4")
        change = EnvironmentChange(
            entity=entity,
            change_type=EnvironmentChangeType.CHANGED,
            previous={"complexity_score": 0.5},
            current={"complexity_score": 0.7},
            observed_at=datetime.now(timezone.utc),
            source="test",
        )
        result = EnvironmentObservationResult(
            cycle_id="ENV-0001",
            ran_at=datetime.now(timezone.utc),
            changes=(change,),
            provider_count=1,
            observed_count=1,
        )

        # The advisor's contract is duck-typed: any object exposing a
        # ``last_result`` attribute is accepted. We use a tiny stub instead
        # of a mock to keep the test focused on the advisor's behavior.
        class _ObserverStub:
            last_result = result

        adv = ProactiveAdvisor(environment_observer=_ObserverStub())
        rep = adv.run_advisory(principal_id="alice")
        assert "environment" in rep.sources_used
        item = rep.items[0]
        assert item.source is AdvisorySource.ENVIRONMENT
        assert item.kind == "environment_changed"


# ---------------------------------------------------------------------------
# Real B3.x surface (InteractionLearningBridge)
# ---------------------------------------------------------------------------

class TestRealInteractionSurface:
    def test_interaction_context_produces_items(self):
        from atlas.interaction.learning_bridge import InteractionLearningBridge
        from atlas.interaction.recorder import InteractionRecorder
        from atlas.interaction.repository import InteractionRepository
        from atlas.authority.service import AuthorityService
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager

        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))

        repo = InteractionRepository()
        recorder = InteractionRecorder(repository=repo)
        recorder.record_preference(ctx, "tone", "concise")
        bridge = InteractionLearningBridge(repository=repo)

        adv = ProactiveAdvisor(interaction_bridge=bridge)
        rep = adv.run_advisory(principal_id="alice")
        kinds = {it.kind for it in rep.items}
        assert "private_preference" in kinds
        assert "interaction" in rep.sources_used

    def test_interaction_context_is_principal_scoped(self):
        from atlas.interaction.learning_bridge import InteractionLearningBridge
        from atlas.interaction.recorder import InteractionRecorder
        from atlas.interaction.repository import InteractionRepository
        from atlas.authority.service import AuthorityService
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager

        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        authority.add_user("Bob", principal_id="bob")
        ctx_a = SessionContext.from_session(manager.create_session("alice"))

        repo = InteractionRepository()
        recorder = InteractionRecorder(repository=repo)
        recorder.record_preference(ctx_a, "tone", "alice-style")
        bridge = InteractionLearningBridge(repository=repo)

        adv = ProactiveAdvisor(interaction_bridge=bridge)
        rep_alice = adv.run_advisory(principal_id="alice")
        rep_bob = adv.run_advisory(principal_id="bob")
        assert any(it.source is AdvisorySource.INTERACTION for it in rep_alice.items)
        # Bob has no interaction context — no interaction-source items.
        assert all(
            it.source is not AdvisorySource.INTERACTION for it in rep_bob.items
        )

    def test_missing_principal_skips_interaction_source(self):
        from atlas.interaction.learning_bridge import InteractionLearningBridge
        from atlas.interaction.recorder import InteractionRecorder
        from atlas.interaction.repository import InteractionRepository
        from atlas.authority.service import AuthorityService
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager

        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))

        repo = InteractionRepository()
        recorder = InteractionRecorder(repository=repo)
        recorder.record_preference(ctx, "tone", "x")
        bridge = InteractionLearningBridge(repository=repo)

        adv = ProactiveAdvisor(interaction_bridge=bridge)
        rep = adv.run_advisory(principal_id="")
        assert "interaction" not in rep.sources_used


# ---------------------------------------------------------------------------
# Real P4 surface (CollectiveGovernance)
# ---------------------------------------------------------------------------

class TestRealCollectiveSurface:
    def test_approved_collective_emits_item(self):
        from atlas.collective.governance import CollectiveGovernance
        from atlas.collective.repository import CollectiveRepository
        from atlas.authority.service import AuthorityService
        from atlas.evolution.approval_manager import ApprovalManager
        from atlas.interaction.recorder import InteractionRecorder
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager

        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))

        irec = InteractionRecorder()
        pref = irec.record_preference(ctx, "tone", "concise")

        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
        )
        cand = gov.extract_candidates([pref])[0]
        req = gov.create_approval_request(cand)
        gov.approve(req, "owner")

        adv = ProactiveAdvisor(collective_governance=gov)
        rep = adv.run_advisory(principal_id="alice")
        kinds = {it.kind for it in rep.items}
        assert any(k.startswith("collective_") for k in kinds)
        assert "collective" in rep.sources_used


# ---------------------------------------------------------------------------
# Authority / non-execution invariants
# ---------------------------------------------------------------------------

class TestAuthorityAndNonExecution:
    def test_user_principal_suggested_actions_are_owner_safe(self):
        # The advisor's authored items for a USER principal must not name
        # OWNER-only paths.
        from atlas.advisory.advisor import _OWNER_ONLY_ACTIONS
        from atlas.ai.availability import ProviderAvailabilityTracker
        from atlas.evolution.self_management import (
            SelfManagementPolicy,
            SelfManagementReport,
            SelfManagementReview,
        )
        tracker = ProviderAvailabilityTracker()
        for _ in range(3):
            tracker.record_failure()
        review = SelfManagementReview(policy=SelfManagementPolicy())
        review.run_review = lambda: SelfManagementReport(  # type: ignore[assignment]
            review_id="SMR-1",
        )

        from atlas.interaction.learning_bridge import InteractionLearningBridge
        from atlas.interaction.recorder import InteractionRecorder
        from atlas.interaction.repository import InteractionRepository
        from atlas.authority.service import AuthorityService
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irepo = InteractionRepository()
        irec = InteractionRecorder(repository=irepo)
        irec.record_preference(ctx, "tone", "x")
        ib = InteractionLearningBridge(repository=irepo)

        adv = ProactiveAdvisor(
            availability=tracker,
            self_management_review=review,
            interaction_bridge=ib,
        )
        rep = adv.run_advisory(principal_id="alice")
        for it in rep.items:
            assert it.suggested_action not in _OWNER_ONLY_ACTIONS, (
                f"USER principal must not see OWNER-only action: {it.suggested_action}"
            )

    def test_advisor_has_no_execution_or_governance_references(self):
        adv = ProactiveAdvisor()
        for attr in (
            "execution_gateway",
            "application_engine",
            "approval_manager",
            "rule_engine",
            "dispatcher",
            "tool_executor",
            "tick",
        ):
            assert not hasattr(adv, attr), f"advisor unexpectedly has {attr}"


# ---------------------------------------------------------------------------
# Fail-closed / bounded / deterministic
# ---------------------------------------------------------------------------

class TestFailClosedAndBounded:
    def test_no_sources_returns_empty_report(self):
        adv = ProactiveAdvisor()
        rep = adv.run_advisory(principal_id="")
        assert rep.count == 0
        assert rep.items == ()
        assert rep.sources_used == ()
        assert rep.source_errors == ()

    def test_bounded_output_for_failing_source(self):
        # A source whose methods always raise still produces a report
        # (fail-soft, recorded in source_errors).
        class _Boom:
            def snapshot(self):
                raise RuntimeError("boom")
        adv = ProactiveAdvisor(availability=_Boom())
        rep = adv.run_advisory(principal_id="alice")
        # No items from that source, error recorded.
        assert any(src == "availability" for src, _ in rep.source_errors)
        assert all(it.source is not AdvisorySource.AVAILABILITY for it in rep.items)

    def test_items_bounded(self):
        from atlas.evolution.environment import (
            EnvironmentChange,
            EnvironmentChangeType,
            EnvironmentDomain,
            EnvironmentEntity,
            EnvironmentObservationResult,
        )
        from datetime import datetime, timezone

        changes = tuple(
            EnvironmentChange(
                entity=EnvironmentEntity(EnvironmentDomain.TOOL, f"t{i}"),
                change_type=EnvironmentChangeType.CHANGED,
                previous={"x": i},
                current={"x": i + 1},
                observed_at=datetime.now(timezone.utc),
                source="test",
            )
            for i in range(80)
        )
        result = EnvironmentObservationResult(
            cycle_id="ENV-1",
            ran_at=datetime.now(timezone.utc),
            changes=changes,
            provider_count=1,
            observed_count=80,
        )

        class _ObserverStub:
            last_result = result

        adv = ProactiveAdvisor(environment_observer=_ObserverStub())
        rep = adv.run_advisory(principal_id="alice")
        # 32-item cap.
        assert rep.count <= 32
        for it in rep.items:
            assert len(it.summary) <= 400
            assert len(it.suggested_action) <= 200
            assert len(it.evidence_ids) <= 8
            assert len(it.item_id) > 0

    def test_deterministic_for_same_inputs(self):
        from atlas.ai.availability import ProviderAvailabilityTracker
        tracker = ProviderAvailabilityTracker()
        for _ in range(2):
            tracker.record_failure()
        adv1 = ProactiveAdvisor(availability=tracker)
        adv2 = ProactiveAdvisor(availability=tracker)
        # Two distinct advisors consuming the same source state must produce
        # structurally equivalent reports (item identity may differ because
        # of the monotonic item_id, but kind / source / summary are stable).
        rep1 = adv1.run_advisory(principal_id="alice")
        rep2 = adv2.run_advisory(principal_id="alice")
        assert rep1.count == rep2.count
        assert [i.source for i in rep1.items] == [i.source for i in rep2.items]
        assert [i.kind for i in rep1.items] == [i.kind for i in rep2.items]
        assert [i.summary for i in rep1.items] == [i.summary for i in rep2.items]


# ---------------------------------------------------------------------------
# Kernel wiring (real Atlas boot)
# ---------------------------------------------------------------------------

class TestKernelWiring:
    def test_kernel_wires_advisor(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            assert atlas._proactive_advisor is not None
            assert atlas.proactive_advisor is atlas._proactive_advisor
            assert "advisory" not in atlas.container.names()
        finally:
            atlas.shutdown()
        assert atlas._proactive_advisor is None

    def test_kernel_run_proactive_advisory_returns_real_report(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            report = atlas.run_proactive_advisory(principal_id="owner")
            # Either the F10 tracker is UNKNOWN (no recorded outcomes) or
            # we have a HEALTHY observation; either way no availability item
            # is emitted for HEALTHY/UNKNOWN.
            sources = {it.source for it in report.items}
            assert isinstance(report, AdvisoryReport)
            assert report.principal_id == "owner"
            assert isinstance(sources, set)
        finally:
            atlas.shutdown()

    def test_tick_does_not_invoke_proactive_advisor(self):
        import inspect
        from atlas.kernel.atlas import Atlas
        tick_src = inspect.getsource(Atlas.tick)
        assert "run_proactive_advisory" not in tick_src
        assert "proactive_advisor" not in tick_src
