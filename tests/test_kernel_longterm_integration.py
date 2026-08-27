"""Track C — Kernel runtime integration tests (Phase 19.6).

Verifies that Atlas.start() wires every Track C component: long-term
storage, episodic/procedural repositories, the additive recorder consumer,
governance (GOV-010), capability handlers, lifecycle metadata, and the
governed-sink ingest bridge.
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from atlas.evolution.autonomy.models import EvolutionRequestStatus
from atlas.evolution.governance.models import ScopeType
from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.kernel.atlas import Atlas
from atlas.storage.longterm_storage import LongTermSQLiteStorage


class TestLongTermKernelIntegration(unittest.TestCase):
    """Track C registrations after Atlas.start()."""

    def setUp(self) -> None:
        # Isolate long-term persistence from the shared atlas_data DB so
        # tests never observe episodes recorded by other tests/runs.
        self._tmp_db = tempfile.TemporaryDirectory()
        self._db_patcher = patch.object(
            LongTermSQLiteStorage,
            "DEFAULT_DB_PATH",
            Path(self._tmp_db.name) / "atlas_experience.db",
        )
        self._db_patcher.start()
        self.addCleanup(self._db_patcher.stop)
        self.addCleanup(self._tmp_db.cleanup)
        self.atlas = Atlas()

    def tearDown(self) -> None:
        if self.atlas.started:
            self.atlas.shutdown()

    def test_longterm_storage_initialized(self) -> None:
        self.atlas.start()
        storage = self.atlas._longterm_storage
        self.assertIsNotNone(storage)
        self.assertTrue(storage.is_available())

    def test_repositories_wired_with_storage(self) -> None:
        self.atlas.start()
        self.assertIsNotNone(self.atlas._episodic_repository)
        self.assertIsNotNone(self.atlas._procedural_repository)
        self.assertIs(
            self.atlas._episodic_repository._storage,
            self.atlas._longterm_storage,
        )
        self.assertIs(
            self.atlas._procedural_repository._storage,
            self.atlas._longterm_storage,
        )

    def test_longterm_capabilities_registered(self) -> None:
        self.atlas.start()
        registry = self.atlas._capability_registry
        self.assertTrue(registry.has("memory.episodic_query"))
        self.assertTrue(registry.has("memory.procedure_query"))
        self.assertTrue(registry.has("memory.consolidate"))

    def test_gov_010_registered(self) -> None:
        self.atlas.start()
        rule = self.atlas._constraint_registry.get_rule("GOV-010")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.scope, ScopeType.MEMORY)  # type: ignore[union-attr]

    def test_recorder_extractor_consolidator_wired(self) -> None:
        self.atlas.start()
        self.assertIsNotNone(self.atlas._longterm_recorder)
        self.assertIsNotNone(self.atlas._procedure_extractor)
        self.assertIsNotNone(self.atlas._longterm_consolidator)
        self.assertIsNotNone(self.atlas._longterm_ingest_bridge)
        # The longterm ingest bridge is wired (post-governed-sink) with the
        # kernel's single GovernanceIngestSink, so consolidation flows through
        # the governed evolution path rather than failing closed for lack of a
        # sink (ATLAS_STATE §19).
        self.assertIsNotNone(self.atlas._longterm_ingest_bridge._sink)
        self.assertIs(
            self.atlas._longterm_ingest_bridge._sink,
            self.atlas._governed_ingest_sink,
        )

    def test_component_metadata_registered(self) -> None:
        self.atlas.start()
        names = {c.name for c in self.atlas._component_registry.get_all()}
        self.assertIn("longterm", names)
        self.assertIn("longterm_evolution", names)

    def test_pipeline_completed_records_episode(self) -> None:
        self.atlas.start()
        experience = StructuredExperience(
            experience_id="EXP-INTEGRATION-00000001",
            timestamp=datetime.now(),
            duration_ms=25.0,
            pipeline_path=["reasoning", "tool_execution"],
            outcome=ExperienceOutcome.SUCCESS,
            user_input="integration test",
            tool_name="search",
            tool_success=True,
        )
        # The recorder is an additive consumer of ExperienceAccumulator
        # output; the pipeline.completed event is the trigger.
        self.atlas._experience_accumulator.repository.store_experience(experience)
        self.atlas._event_bus.publish("runtime.pipeline.completed", {})
        episodes = self.atlas._episodic_repository.get_episodes()
        self.assertEqual(len(episodes), 1)
        self.assertEqual(
            episodes[0].source_experience_id,
            experience.experience_id,
        )

    def test_consolidate_capability_governed_sink_routed(self) -> None:
        # memory.consolidate runs a consolidation pass, records the PENDING
        # audit record, and hands the governed request through the wired
        # LongTermIngestBridge. With the kernel's governed sink present the
        # handoff is accepted (success) and a DRAFTED EvolutionRequest is
        # persisted in the ScheduleStore — nothing bypasses governance and
        # no repository mutation happens directly in the handler.
        self.atlas.start()
        handler = self.atlas._capability_registry.get("memory.consolidate")
        self.assertIsNotNone(handler)
        result = handler({})  # type: ignore[operator]
        self.assertTrue(result.success)
        self.assertTrue(result.output["accepted"])
        request_id = result.output["request_id"]
        self.assertTrue(request_id)
        drafted = self.atlas._schedule_store.list_by_status(
            EvolutionRequestStatus.DRAFTED
        )
        self.assertIn(
            request_id,
            [req.request_id for req in drafted],
        )

    def test_shutdown_cleans_up(self) -> None:
        self.atlas.start()
        self.atlas.shutdown()
        self.assertIsNone(self.atlas._longterm_storage)
        self.assertIsNone(self.atlas._episodic_repository)
        self.assertIsNone(self.atlas._procedural_repository)
        self.assertIsNone(self.atlas._longterm_recorder)
        self.assertIsNone(self.atlas._procedure_extractor)
        self.assertIsNone(self.atlas._longterm_consolidator)
        self.assertIsNone(self.atlas._longterm_factory)
        self.assertIsNone(self.atlas._longterm_ingest_bridge)


if __name__ == "__main__":
    unittest.main()
