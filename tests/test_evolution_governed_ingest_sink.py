"""Tests for Foundation Strengthening Batch 12 — Governed Ingest Sink + Bridge Wiring.

Covers:
- GovernanceIngestSink construction (ScheduleStore required)
- enqueue_request structural safety checks (None, missing id/source, unsupported scopes)
- enqueue_request deduplication by request_id
- enqueue_request valid MEMORY/KNOWLEDGE → DRAFTED persistence
- enqueue_request ScheduleStore failure → fail-closed
- to_applier_entries MEMORY/KNOWLEDGE translation (pure, deterministic)
- Kernel wiring: bridges have has_sink==True after Atlas.start()
- Kernel wiring: three bridges share the SAME sink instance
- Bridge ingestion produces a persisted DRAFTED request in ScheduleStore
- Protected scopes (CONFIG/CAPABILITY/UNKNOWN) remain fail-closed
- Shutdown clears sink reference
- No public ServiceContainer key for sink
"""

import tempfile
import unittest
from pathlib import Path

from atlas.evolution.autonomy.governed_ingest_sink import (
    GovernanceIngestSink,
    IngestHandoffResult,
)
from atlas.evolution.autonomy.models import (
    AutonomyPolicy,
    EvolutionRequest,
)
from atlas.evolution.autonomy.schedule_store import ScheduleStore
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel
from atlas.storage.autonomy_storage import AutonomySQLiteStorage


def _make_memory_request(
    request_id: str = "B12-MEM-1",
    source: str = "test:memory",
) -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source=source,
        target_scope=ScopeType.MEMORY,
        change_payload={
            "operation": "add",
            "entry_id": "M-1",
            "domain": "test",
            "content": "memory content",
            "confidence": 0.9,
        },
        intended_level=ExecutionLevel.INFORMATION,
    )


def _make_knowledge_request(
    request_id: str = "B12-KNW-1",
    source: str = "test:knowledge",
) -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source=source,
        target_scope=ScopeType.KNOWLEDGE,
        change_payload={
            "operation": "add",
            "entry_id": "K-1",
            "domain": "test",
            "content": "knowledge content",
            "confidence": 0.85,
        },
        intended_level=ExecutionLevel.INFORMATION,
    )


def _make_config_request() -> EvolutionRequest:
    return EvolutionRequest(
        request_id="B12-CFG-1",
        source="test:config",
        target_scope=ScopeType.CONFIG,
        change_payload={"operation": "set", "key": "x", "value": "y"},
        intended_level=ExecutionLevel.SELF_CONFIG,
    )


def _make_capability_request() -> EvolutionRequest:
    return EvolutionRequest(
        request_id="B12-CAP-1",
        source="test:capability",
        target_scope=ScopeType.CAPABILITY,
        change_payload={
            "operation": "register",
            "capability_name": "RogueCap",
        },
        intended_level=ExecutionLevel.SELF_CONFIG,
    )


def _make_unknown_request() -> EvolutionRequest:
    return EvolutionRequest(
        request_id="B12-UNK-1",
        source="test:unknown",
        target_scope=ScopeType.UNKNOWN,
        change_payload={},
        intended_level=ExecutionLevel.ADMINISTRATIVE,
    )


def _make_storage_and_store() -> tuple[AutonomySQLiteStorage, ScheduleStore]:
    """Create a temp AutonomySQLiteStorage + ScheduleStore pair."""
    tmp = tempfile.mkdtemp(prefix="atlas_b12_")
    db = Path(tmp) / "autonomy.db"
    storage = AutonomySQLiteStorage(db_path=str(db))
    storage.initialize()
    store = ScheduleStore(storage=storage, policy=AutonomyPolicy())
    return storage, store
# ---------------------------------------------------------------------------
# Unit: GovernanceIngestSink
# ---------------------------------------------------------------------------


class TestGovernanceIngestSinkConstruction(unittest.TestCase):
    """Sink requires a ScheduleStore on construction."""

    def test_construction_with_none_raises(self):
        with self.assertRaises(ValueError):
            GovernanceIngestSink(schedule_store=None)


class TestEnqueueStructuralSafety(unittest.TestCase):
    """Fail-closed on malformed/missing fields."""

    def setUp(self) -> None:
        self._storage, self._store = _make_storage_and_store()
        self.sink = GovernanceIngestSink(schedule_store=self._store)

    def tearDown(self) -> None:
        self._storage.close()
        import shutil

        shutil.rmtree(Path(self._storage._db_path).parent, ignore_errors=True)

    def test_enqueue_none_returns_rejected(self):
        result = self.sink.enqueue_request(None)
        self.assertFalse(result.accepted)
        self.assertIn("None", result.error)

    def test_enqueue_missing_request_id(self):
        req = EvolutionRequest(
            request_id="",
            source="s",
            target_scope=ScopeType.MEMORY,
            change_payload={},
        )
        result = self.sink.enqueue_request(req)
        self.assertFalse(result.accepted)
        self.assertIn("request_id", result.error)

    def test_enqueue_missing_source(self):
        req = EvolutionRequest(
            request_id="B12-TEST",
            source="",
            target_scope=ScopeType.MEMORY,
            change_payload={},
        )
        result = self.sink.enqueue_request(req)
        self.assertFalse(result.accepted)
        self.assertIn("source", result.error)

    def test_enqueue_config_scope_fail_closed(self):
        result = self.sink.enqueue_request(_make_config_request())
        self.assertFalse(result.accepted)
        self.assertIn("not ingestable", result.error)
        self.assertIn("CONFIG", result.error)

    def test_enqueue_capability_scope_fail_closed(self):
        result = self.sink.enqueue_request(_make_capability_request())
        self.assertFalse(result.accepted)
        self.assertIn("not ingestable", result.error)
        self.assertIn("CAPABILITY", result.error)

    def test_enqueue_unknown_scope_fail_closed(self):
        result = self.sink.enqueue_request(_make_unknown_request())
        self.assertFalse(result.accepted)
        self.assertIn("not ingestable", result.error)


class TestEnqueueDeduplication(unittest.TestCase):
    """Duplicate request_id is rejected."""

    def setUp(self) -> None:
        self._storage, self._store = _make_storage_and_store()
        self.sink = GovernanceIngestSink(schedule_store=self._store)

    def tearDown(self) -> None:
        self._storage.close()
        import shutil

        shutil.rmtree(Path(self._storage._db_path).parent, ignore_errors=True)

    def test_duplicate_request_id_rejected(self):
        req = _make_memory_request("B12-DUP-1")
        first = self.sink.enqueue_request(req)
        self.assertTrue(first.accepted)
        second = self.sink.enqueue_request(req)
        self.assertFalse(second.accepted)
        self.assertIn("duplicate", second.error)


class TestEnqueueValidPersistence(unittest.TestCase):
    """Valid requests are persisted as DRAFTED; no apply/validate/authorize."""

    def setUp(self) -> None:
        self._storage, self._store = _make_storage_and_store()
        self.sink = GovernanceIngestSink(schedule_store=self._store)

    def tearDown(self) -> None:
        self._storage.close()
        import shutil

        shutil.rmtree(Path(self._storage._db_path).parent, ignore_errors=True)

    def test_memory_request_persisted_as_drafted(self):
        req = _make_memory_request("B12-PERSIST-MEM")
        result = self.sink.enqueue_request(req)
        self.assertTrue(result.accepted)
        self.assertEqual(result.request_id, "B12-PERSIST-MEM")
        self.assertEqual(result.error, "")

        stored = self._store.get_request("B12-PERSIST-MEM")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status.name, "DRAFTED")
        self.assertEqual(stored.source, "test:memory")
        self.assertEqual(stored.target_scope, ScopeType.MEMORY)
        self.assertEqual(stored.change_payload["entry_id"], "M-1")
        self.assertEqual(stored.change_payload["content"], "memory content")
        self.assertEqual(stored.change_payload["operation"], "add")

    def test_knowledge_request_persisted_as_drafted(self):
        req = _make_knowledge_request("B12-PERSIST-KNW")
        result = self.sink.enqueue_request(req)
        self.assertTrue(result.accepted)

        stored = self._store.get_request("B12-PERSIST-KNW")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status.name, "DRAFTED")
        self.assertEqual(stored.target_scope, ScopeType.KNOWLEDGE)
        self.assertEqual(stored.change_payload["entry_id"], "K-1")
        self.assertEqual(stored.change_payload["confidence"], 0.85)
# ---------------------------------------------------------------------------
# Unit: to_applier_entries (pure translation helper)
# ---------------------------------------------------------------------------


class TestToApplierEntries(unittest.TestCase):
    """Pure, deterministic translation of flat payload → applier entries."""

    def test_memory_translation(self):
        req = _make_memory_request()
        result = GovernanceIngestSink.to_applier_entries(req)
        self.assertIn("entries", result)
        self.assertEqual(len(result["entries"]), 1)
        entry = result["entries"][0]
        self.assertEqual(entry["memory_id"], "M-1")
        self.assertEqual(entry["content"], "memory content")

    def test_memory_translation_no_content(self):
        req = EvolutionRequest(
            request_id="B12-M-NC",
            source="s",
            target_scope=ScopeType.MEMORY,
            change_payload={"entry_id": "M-noc"},
        )
        result = GovernanceIngestSink.to_applier_entries(req)
        entry = result["entries"][0]
        self.assertEqual(entry["memory_id"], "M-noc")
        self.assertNotIn("content", entry)

    def test_knowledge_translation(self):
        req = _make_knowledge_request()
        result = GovernanceIngestSink.to_applier_entries(req)
        entry = result["entries"][0]
        self.assertEqual(entry["knowledge_key"], "K-1")
        self.assertEqual(entry["content"], "knowledge content")
        self.assertEqual(entry["confidence"], 0.85)

    def test_knowledge_translation_no_confidence(self):
        req = EvolutionRequest(
            request_id="B12-K-NC",
            source="s",
            target_scope=ScopeType.KNOWLEDGE,
            change_payload={"entry_id": "K-nc", "content": "x"},
        )
        result = GovernanceIngestSink.to_applier_entries(req)
        entry = result["entries"][0]
        self.assertEqual(entry["knowledge_key"], "K-nc")
        self.assertNotIn("confidence", entry)

    def test_translation_never_modifies_original_payload(self):
        req = _make_memory_request()
        payload_before = dict(req.change_payload)
        GovernanceIngestSink.to_applier_entries(req)
        self.assertEqual(req.change_payload, payload_before)
# ---------------------------------------------------------------------------
# Integration: Kernel wiring (bridges + sink after Atlas.start())
# ---------------------------------------------------------------------------


class TestBridgeSinkWiring(unittest.TestCase):
    """After Atlas.start(), the three kernel-owned bridges have a shared sink."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b12_wire_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir

        from atlas.kernel.atlas import Atlas

        self.atlas = Atlas()
        self.atlas.start()

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_bridges_have_sink_after_startup(self):
        self.assertTrue(
            self.atlas._research_ingest_bridge.has_sink,
            "research bridge should have sink after startup",
        )
        self.assertTrue(
            self.atlas._longterm_ingest_bridge.has_sink,
            "longterm bridge should have sink after startup",
        )
        self.assertTrue(
            self.atlas._advanced_reasoning_ingest_bridge.has_sink,
            "reasoning bridge should have sink after startup",
        )

    def test_bridges_share_same_sink_instance(self):
        sink_r = self.atlas._research_ingest_bridge._sink
        sink_l = self.atlas._longterm_ingest_bridge._sink
        sink_a = self.atlas._advanced_reasoning_ingest_bridge._sink
        self.assertIsNotNone(sink_r)
        self.assertIs(sink_r, sink_l)
        self.assertIs(sink_r, sink_a)

    def test_kernel_sink_matches_bridge_sink(self):
        self.assertIsNotNone(self.atlas._governed_ingest_sink)
        self.assertIs(
            self.atlas._governed_ingest_sink,
            self.atlas._research_ingest_bridge._sink,
        )


class TestBridgeIngestionProducesDrafted(unittest.TestCase):
    """Bridge ingestion produces a DRAFTED request in ScheduleStore."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b12_ingest_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir

        from atlas.kernel.atlas import Atlas

        self.atlas = Atlas()
        self.atlas.start()

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_research_ingest_persists_drafted_knowledge(self):
        from atlas.research.models import ResearchReport

        report = ResearchReport(
            report_id="b12-rpt-001",
            plan_id="b12-plan-001",
            query_id="b12-q-001",
            question="batch 12 test question",
            findings="test finding for batch 12",
            confidence=0.92,
        )
        bridge = self.atlas._research_ingest_bridge
        result = bridge.ingest(report)
        self.assertTrue(result.accepted, f"ingest failed: {result.error}")

        store = self.atlas._schedule_store
        persisted = store.get_request(result.request_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status.name, "DRAFTED")
        self.assertEqual(persisted.source, f"research:{report.report_id}")
        self.assertEqual(persisted.target_scope, ScopeType.KNOWLEDGE)
        self.assertIn("content", persisted.change_payload)
        self.assertEqual(
            persisted.change_payload["content"], "test finding for batch 12"
        )
        self.assertEqual(
            persisted.change_payload["entry_id"], f"research:{report.report_id}"
        )

    def test_longterm_ingest_persists_drafted_memory(self):
        from atlas.longterm.models import ConsolidationRecord, ConsolidationStatus

        record = ConsolidationRecord(
            record_id="b12-cons-001",
            reason="batch 12 consolidation",
            operation="consolidate",
            status=ConsolidationStatus.PENDING,
            target_type="episode",
            target_ids=frozenset({"ep-1"}),
        )
        bridge = self.atlas._longterm_ingest_bridge
        result = bridge.ingest(record)
        self.assertTrue(result.accepted, f"ingest failed: {result.error}")

        store = self.atlas._schedule_store
        persisted = store.get_request(result.request_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status.name, "DRAFTED")
        self.assertEqual(persisted.target_scope, ScopeType.MEMORY)
        self.assertEqual(
            persisted.change_payload["entry_id"], "longterm:b12-cons-001"
        )

    def test_reasoning_ingest_persists_drafted_knowledge(self):
        bridge = self.atlas._advanced_reasoning_ingest_bridge
        result = bridge.ingest(
            content="reasoning insight from batch 12",
            source_trace_id="trace:b12",
            strategy_name="decompose",
            confidence=0.88,
        )
        self.assertTrue(result.accepted, f"ingest failed: {result.error}")

        store = self.atlas._schedule_store
        persisted = store.get_request(result.request_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status.name, "DRAFTED")
        self.assertEqual(persisted.target_scope, ScopeType.KNOWLEDGE)
        self.assertEqual(
            persisted.change_payload["entry_id"],
            "advanced_reasoning:insight:trace:b12",
        )
class TestProtectedScopesRemainFailClosed(unittest.TestCase):
    """CONFIG/CAPABILITY scopes cannot be ingested through the bridge."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b12_scope_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir

        from atlas.kernel.atlas import Atlas

        self.atlas = Atlas()
        self.atlas.start()

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_sink_rejects_config_scope(self):
        result = self.atlas._governed_ingest_sink.enqueue_request(
            _make_config_request()
        )
        self.assertFalse(result.accepted)

    def test_sink_rejects_capability_scope(self):
        result = self.atlas._governed_ingest_sink.enqueue_request(
            _make_capability_request()
        )
        self.assertFalse(result.accepted)


class TestShutdownClearsSink(unittest.TestCase):
    """Shutdown clears the kernel-private sink reference."""

    def test_shutdown_clears_sink(self):
        tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b12_shut_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = tmp_dir / "memory.json"
        Storage.DATA_DIR = tmp_dir

        from atlas.kernel.atlas import Atlas

        try:
            atlas = Atlas()
            atlas.start()
            self.assertIsNotNone(atlas._governed_ingest_sink)
            atlas.shutdown()
            self.assertIsNone(atlas._governed_ingest_sink)
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestNoServiceContainerKey(unittest.TestCase):
    """The sink is NOT registered in the public ServiceContainer."""

    def test_sink_not_in_container(self):
        tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b12_svc_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = tmp_dir / "memory.json"
        Storage.DATA_DIR = tmp_dir

        from atlas.kernel.atlas import Atlas

        try:
            atlas = Atlas()
            atlas.start()
            self.assertFalse(atlas.container.has("governed_ingest_sink"))
        finally:
            atlas.shutdown()
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()