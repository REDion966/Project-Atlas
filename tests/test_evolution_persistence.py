"""
Phase 11.3 — Evolution Persistence Tests.

Tests that EvolutionMemory correctly persists proposals, approval requests,
and evolution records through SQLiteEvolutionStorage, and restores them on
restart.

Reuses the same atlas_experience.db pattern as experience storage tests.
"""

from datetime import datetime
from pathlib import Path
import tempfile

import pytest

from atlas.evolution.storage_interface import EvolutionStorage, EvolutionRestoreResult
from atlas.storage.evolution_storage import SQLiteEvolutionStorage
from atlas.evolution.evolution_memory import (
    EvolutionMemory,
    _proposal_to_dict,
    _proposal_from_dict,
    _approval_request_to_dict,
    _approval_request_from_dict,
    _evolution_record_to_dict,
    _evolution_record_from_dict,
)
from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionProposal,
    EvolutionRecord,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
    Weakness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_proposal(proposal_id="PROP-PERSIST-001") -> EvolutionProposal:
    """Create a test EvolutionProposal."""
    plan = ImprovementPlan(
        plan_id="IMP-PERSIST-001",
        title="Persist Test Plan",
        description="Test plan for persistence",
        priority=ImprovementPriority.MEDIUM,
    )
    return EvolutionProposal(
        proposal_id=proposal_id,
        title="Persist Test Proposal",
        summary="Testing persistence of proposals",
        rationale="Need to verify save/restore.",
        expected_benefit="Data survives restarts.",
        risks="None.",
        impact_analysis="Affects evolution storage.",
        implementation_approach="1. Save. 2. Load. 3. Verify.",
        plan=plan,
        status=ProposalStatus.PENDING_APPROVAL,
    )


def make_approval_request(proposal_id="PROP-PERSIST-001") -> ApprovalRequest:
    """Create a test ApprovalRequest."""
    return ApprovalRequest(
        request_id="APPR-PERSIST-001",
        proposal_id=proposal_id,
        title="Persist Approval",
        description="Testing approval persistence",
        rationale="Need to verify save/restore.",
        risks="None.",
        expected_benefit="Data survives restarts.",
        decision=ApprovalDecision.PENDING,
    )


def make_evolution_record() -> EvolutionRecord:
    """Create a test EvolutionRecord."""
    return EvolutionRecord(
        record_id="EVR-PERSIST-001",
        event_type="execution",
        description="Test execution record for persistence",
        related_ids=["PROP-PERSIST-001"],
        metadata={"test": True},
    )


# ---------------------------------------------------------------------------
# Test: Serialization round-trip helpers
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:

    def test_proposal_round_trip(self):
        """Serializing and deserializing a proposal preserves all fields."""
        original = make_proposal()
        data = _proposal_to_dict(original)
        restored = _proposal_from_dict(data)

        assert restored.proposal_id == original.proposal_id
        assert restored.title == original.title
        assert restored.summary == original.summary
        assert restored.rationale == original.rationale
        assert restored.status == original.status
        assert restored.plan.plan_id == original.plan.plan_id
        assert restored.plan.priority == original.plan.priority

    def test_approval_request_round_trip(self):
        """Serializing and deserializing an approval request preserves all fields."""
        original = make_approval_request()
        data = _approval_request_to_dict(original)
        restored = _approval_request_from_dict(data)

        assert restored.request_id == original.request_id
        assert restored.proposal_id == original.proposal_id
        assert restored.title == original.title
        assert restored.decision == original.decision

    def test_evolution_record_round_trip(self):
        """Serializing and deserializing an evolution record preserves all fields."""
        original = make_evolution_record()
        data = _evolution_record_to_dict(original)
        restored = _evolution_record_from_dict(data)

        assert restored.record_id == original.record_id
        assert restored.event_type == original.event_type
        assert restored.description == original.description
        assert restored.related_ids == original.related_ids
        assert restored.metadata == original.metadata


# ---------------------------------------------------------------------------
# Test: SQLiteEvolutionStorage adapter
# ---------------------------------------------------------------------------


class TestSQLiteEvolutionStorage:

    @pytest.fixture
    def storage(self):
        """Create a temporary SQLiteEvolutionStorage for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_evolution.db"
            s = SQLiteEvolutionStorage(db_path=db_path)
            s.initialize()
            yield s
            s.close()

    def test_initialize_and_available(self, storage):
        """Storage is available after initialization."""
        assert storage.is_available() is True
        assert storage.db_path.exists()

    def test_store_and_load_proposal(self, storage):
        """Proposal stored and loaded correctly."""
        original = make_proposal()
        storage.store_proposal(_proposal_to_dict(original))

        loaded = storage.load_proposals()
        assert len(loaded) == 1
        assert loaded[0]["proposal_id"] == "PROP-PERSIST-001"
        assert loaded[0]["title"] == "Persist Test Proposal"

        # Verify round-trip via dict
        restored = _proposal_from_dict(loaded[0])
        assert restored.proposal_id == original.proposal_id
        assert restored.title == original.title

    def test_store_and_load_approval_request(self, storage):
        """Approval request stored and loaded correctly."""
        original = make_approval_request()
        storage.store_approval_request(_approval_request_to_dict(original))

        loaded = storage.load_approval_requests()
        assert len(loaded) == 1
        assert loaded[0]["request_id"] == "APPR-PERSIST-001"
        assert loaded[0]["proposal_id"] == "PROP-PERSIST-001"

        restored = _approval_request_from_dict(loaded[0])
        assert restored.decision == ApprovalDecision.PENDING

    def test_store_and_load_record(self, storage):
        """Evolution record stored and loaded correctly."""
        original = make_evolution_record()
        storage.store_record(_evolution_record_to_dict(original))

        loaded = storage.load_records()
        assert len(loaded) == 1
        assert loaded[0]["record_id"] == "EVR-PERSIST-001"
        assert loaded[0]["event_type"] == "execution"

        restored = _evolution_record_from_dict(loaded[0])
        assert restored.event_type == "execution"
        assert "PROP-PERSIST-001" in restored.related_ids

    def test_multiple_proposals(self, storage):
        """Multiple proposals stored and loaded."""
        for i in range(5):
            p = make_proposal(proposal_id=f"PROP-MULTI-{i:03d}")
            storage.store_proposal(_proposal_to_dict(p))

        loaded = storage.load_proposals()
        assert len(loaded) == 5

    def test_clear_all(self, storage):
        """clear_all removes all data."""
        storage.store_proposal(_proposal_to_dict(make_proposal()))
        storage.store_approval_request(_approval_request_to_dict(make_approval_request()))
        storage.store_record(_evolution_record_to_dict(make_evolution_record()))

        assert len(storage.load_proposals()) == 1
        assert len(storage.load_approval_requests()) == 1
        assert len(storage.load_records()) == 1

        storage.clear_all()

        assert len(storage.load_proposals()) == 0
        assert len(storage.load_approval_requests()) == 0
        assert len(storage.load_records()) == 0

    def test_empty_database(self, storage):
        """Empty database returns empty lists."""
        assert storage.load_proposals() == []
        assert storage.load_approval_requests() == []
        assert storage.load_records() == []

    def test_schema_version(self, storage):
        """Schema version is 8 after Phase 18.8 additive toolchain tables."""
        assert storage.get_schema_version() == 8


# ---------------------------------------------------------------------------
# Test: EvolutionMemory with storage injection
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_and_memory():
    """Create a memory with injected storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_evolution.db"
        s = SQLiteEvolutionStorage(db_path=db_path)
        s.initialize()
        mem = EvolutionMemory(storage=s)
        yield s, mem
        s.close()


class TestEvolutionMemoryPersistence:

    def test_store_auto_persists_proposal(self, storage_and_memory):
        """Storing a proposal in memory also persists to storage."""
        s, mem = storage_and_memory
        proposal = make_proposal()
        mem.store_proposal(proposal)

        # Verify in memory
        assert mem.proposal_count == 1
        assert mem.get_proposal("PROP-PERSIST-001") is not None

        # Verify in storage
        loaded = s.load_proposals()
        assert len(loaded) == 1
        assert loaded[0]["proposal_id"] == "PROP-PERSIST-001"

    def test_store_auto_persists_approval_request(self, storage_and_memory):
        """Storing an approval request in memory also persists to storage."""
        s, mem = storage_and_memory
        req = make_approval_request()
        mem.store_approval_request(req)

        assert mem.approval_request_count == 1
        loaded = s.load_approval_requests()
        assert len(loaded) == 1

    def test_store_auto_persists_record(self, storage_and_memory):
        """Storing an evolution record in memory also persists to storage."""
        s, mem = storage_and_memory
        rec = make_evolution_record()
        mem.store_record(rec)

        assert mem.record_count == 1
        loaded = s.load_records()
        assert len(loaded) == 1

    def test_restore_loads_all_data(self, storage_and_memory):
        """restore() loads previously persisted data back into memory."""
        s, mem = storage_and_memory

        # Write data directly through storage
        s.store_proposal(_proposal_to_dict(make_proposal("PROP-RESTORE-001")))
        s.store_proposal(_proposal_to_dict(make_proposal("PROP-RESTORE-002")))
        s.store_approval_request(_approval_request_to_dict(
            make_approval_request("PROP-RESTORE-001"),
        ))
        s.store_record(_evolution_record_to_dict(make_evolution_record()))

        # Create a fresh memory (no pre-loaded data)
        fresh_mem = EvolutionMemory(storage=s)
        fresh_mem.restore()

        assert fresh_mem.proposal_count == 2
        assert fresh_mem.approval_request_count == 1
        assert fresh_mem.record_count == 1
        assert fresh_mem.get_proposal("PROP-RESTORE-001") is not None

    def test_restart_simulation(self, storage_and_memory):
        """
        Simulate a full restart:
        1. Store data in memory (auto-persists)
        2. Create fresh memory + storage pointing to same DB
        3. Verify data is restored
        """
        s, mem = storage_and_memory

        # Phase 1: save data
        proposal = make_proposal("PROP-RESTART-001")
        proposal.status = ProposalStatus.IMPLEMENTED
        mem.store_proposal(proposal)
        mem.store_approval_request(make_approval_request("PROP-RESTART-001"))
        mem.store_record(make_evolution_record())

        # Close first session
        mem.clear()
        s.close()

        # Phase 2: new session (same db file)
        s2 = SQLiteEvolutionStorage(db_path=s.db_path)
        s2.initialize()
        mem2 = EvolutionMemory(storage=s2)
        mem2.restore()

        assert mem2.proposal_count == 1
        restored_proposal = mem2.get_proposal("PROP-RESTART-001")
        assert restored_proposal is not None
        assert restored_proposal.status == ProposalStatus.IMPLEMENTED
        assert restored_proposal.title == "Persist Test Proposal"

        assert mem2.approval_request_count == 1
        assert mem2.record_count == 1

        s2.close()

    def test_restore_empty_database(self):
        """Restoring an empty database is a no-op."""
        s = EvolutionMemory()
        # No storage configured - restore is no-op
        s.restore()
        assert s.proposal_count == 0

    def test_without_storage_memory_still_works(self):
        """Memory without storage injection still works normally."""
        mem = EvolutionMemory()
        proposal = make_proposal()
        mem.store_proposal(proposal)
        assert mem.proposal_count == 1
        assert mem.get_proposal("PROP-PERSIST-001") is not None


# ---------------------------------------------------------------------------
# Test: Edge cases and corruption handling
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_duplicate_id_overwrites(self, storage_and_memory):
        """Storing two proposals with the same ID overwrites in storage."""
        s, mem = storage_and_memory
        p1 = make_proposal("PROP-DUP")
        p1.title = "First Version"
        mem.store_proposal(p1)

        p2 = make_proposal("PROP-DUP")
        p2.title = "Second Version"
        mem.store_proposal(p2)

        # Memory keeps both (deque)
        assert mem.proposal_count == 2

        # Storage has latest (INSERT OR REPLACE)
        loaded = s.load_proposals()
        assert len(loaded) == 1
        assert loaded[0]["title"] == "Second Version"
