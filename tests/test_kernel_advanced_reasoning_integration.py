"""Track D — Kernel runtime integration tests (Batch 2).

Verifies that Atlas.start() wires every Track D component: advanced-reasoning
storage, the dual-write repository, the provider adapters, the private
service (NOT registered in the ServiceContainer), the trace recorder as an
additive pipeline consumer, GOV-011, capability handlers, lifecycle metadata,
and shutdown cleanup.
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from atlas.evolution.governance.models import ScopeType
from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.kernel.atlas import Atlas
from atlas.storage.advanced_reasoning_storage import AdvancedReasoningSQLiteStorage


class TestAdvancedReasoningKernelIntegration(unittest.TestCase):
    """Track D registrations after Atlas.start()."""

    def setUp(self) -> None:
        # Isolate advanced-reasoning persistence from the shared atlas_data
        # DB so tests never observe traces recorded by other tests/runs.
        self._tmp_db = tempfile.TemporaryDirectory()
        self._db_patcher = patch.object(
            AdvancedReasoningSQLiteStorage,
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

    def test_storage_initialized(self) -> None:
        self.atlas.start()
        storage = self.atlas._advanced_reasoning_storage
        self.assertIsNotNone(storage)
        self.assertTrue(storage.is_available())

    def test_repository_wired_with_storage(self) -> None:
        self.atlas.start()
        repository = self.atlas._advanced_reasoning_repository
        self.assertIsNotNone(repository)
        self.assertIs(repository._storage, self.atlas._advanced_reasoning_storage)

    def test_service_private_not_in_container(self) -> None:
        self.atlas.start()
        self.assertIsNotNone(self.atlas._advanced_reasoning_service)
        self.assertNotIn("advanced_reasoning", self.atlas._container._services)

    def test_provider_adapters_wired(self) -> None:
        self.atlas.start()
        self.assertIsNotNone(self.atlas._advanced_reasoning_evidence_provider)
        self.assertIsNotNone(self.atlas._advanced_reasoning_causal_provider)

    def test_reasoning_capabilities_registered(self) -> None:
        self.atlas.start()
        registry = self.atlas._capability_registry
        for name in (
            "reasoning.trace",
            "reasoning.causal",
            "reasoning.counterfactual",
            "reasoning.hypotheses",
            "reasoning.verify",
            "reasoning.meta",
            "reasoning.ingest",
        ):
            self.assertTrue(registry.has(name))

    def test_gov_011_registered(self) -> None:
        self.atlas.start()
        rule = self.atlas._constraint_registry.get_rule("GOV-011")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.scope, ScopeType.KNOWLEDGE)

    def test_recorder_wired(self) -> None:
        self.atlas.start()
        self.assertIsNotNone(self.atlas._advanced_reasoning_recorder)
        self.assertIsNone(self.atlas._advanced_reasoning_ingest_bridge._sink)

    def test_component_metadata_registered(self) -> None:
        self.atlas.start()
        names = {c.name for c in self.atlas._component_registry.get_all()}
        self.assertIn("advanced_reasoning", names)
        self.assertIn("advanced_reasoning_evolution", names)

    def test_pipeline_completed_records_trace(self) -> None:
        self.atlas.start()
        experience = StructuredExperience(
            experience_id="EXP-AR-00000001",
            timestamp=datetime.now(),
            duration_ms=25.0,
            pipeline_path=["reasoning", "tool_execution"],
            outcome=ExperienceOutcome.SUCCESS,
            user_input="advanced reasoning integration test",
            tool_name="search",
            tool_success=True,
        )
        self.atlas._experience_accumulator.repository.store_experience(experience)
        self.atlas._event_bus.publish("runtime.pipeline.completed", {})
        recorder = self.atlas._advanced_reasoning_recorder
        self.assertIsNotNone(recorder)
        traces = recorder.recent(10)  # type: ignore[union-attr]
        self.assertEqual(len(traces), 1)
        self.assertEqual(
            traces[0].metadata["experience_id"],
            experience.experience_id,
        )

    def test_ingest_capability_fails_closed(self) -> None:
        self.atlas.start()
        handler = self.atlas._capability_registry.get("reasoning.ingest")
        self.assertIsNotNone(handler)
        result = handler({})  # type: ignore[operator]
        self.assertFalse(result.success)

    def test_shutdown_cleans_up(self) -> None:
        self.atlas.start()
        self.atlas.shutdown()
        self.assertIsNone(self.atlas._advanced_reasoning_storage)
        self.assertIsNone(self.atlas._advanced_reasoning_repository)
        self.assertIsNone(self.atlas._advanced_reasoning_service)
        self.assertIsNone(self.atlas._advanced_reasoning_factory)
        self.assertIsNone(self.atlas._advanced_reasoning_recorder)
        self.assertIsNone(self.atlas._advanced_reasoning_ingest_bridge)
        self.assertIsNone(self.atlas._advanced_reasoning_evidence_provider)
        self.assertIsNone(self.atlas._advanced_reasoning_causal_provider)


if __name__ == "__main__":
    unittest.main()
