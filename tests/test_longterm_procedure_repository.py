"""Track C — ProceduralRepository tests (Batch 2).

Covers bounded storage, query methods, storage dual-write (best-effort),
and restore behavior.
"""

from datetime import datetime

import pytest

from atlas.longterm.models import Procedure, ProcedureKind, ProcedureStep
from atlas.longterm.procedure_repository import ProceduralRepository


def _make_procedure(
    procedure_id: str,
    *,
    name: str = "proc",
    category: str = "utility",
    kind: ProcedureKind = ProcedureKind.DISTILLED,
    created_at: datetime | None = None,
    steps: tuple[ProcedureStep, ...] = (),
) -> Procedure:
    return Procedure(
        procedure_id=procedure_id,
        name=name,
        category=category,
        kind=kind,
        created_at=created_at or datetime(2026, 1, 1, 0, 0, 0),
        steps=steps,
    )


def _make_step(step_id: str, *, tool_name: str = "") -> ProcedureStep:
    return ProcedureStep(step_id=step_id, tool_name=tool_name)


class TestInit:
    def test_defaults(self):
        repo = ProceduralRepository()
        assert repo.procedure_count == 0
        assert repo._max_procedures == 1_000

    def test_custom_limit(self):
        repo = ProceduralRepository(max_procedures=10)
        assert repo._max_procedures == 10

    def test_invalid_max_procedures(self):
        with pytest.raises(ValueError):
            ProceduralRepository(max_procedures=0)


class TestStoreAndGetProcedure:
    def test_store_and_get(self):
        repo = ProceduralRepository()
        proc = _make_procedure("p1")
        repo.store_procedure(proc)
        assert repo.get_procedure("p1") is proc
        assert repo.procedure_count == 1

    def test_get_missing(self):
        repo = ProceduralRepository()
        assert repo.get_procedure("missing") is None

    def test_store_replaces_existing(self):
        repo = ProceduralRepository()
        proc1 = _make_procedure("p1", name="old")
        proc2 = _make_procedure("p1", name="new")
        repo.store_procedure(proc1)
        repo.store_procedure(proc2)
        assert repo.get_procedure("p1") is proc2
        assert repo.procedure_count == 1

    def test_bounded_eviction(self):
        repo = ProceduralRepository(max_procedures=2)
        repo.store_procedure(_make_procedure("p1"))
        repo.store_procedure(_make_procedure("p2"))
        repo.store_procedure(_make_procedure("p3"))
        assert repo.procedure_count == 2
        assert repo.get_procedure("p1") is None
        assert repo.get_procedure("p2") is not None
        assert repo.get_procedure("p3") is not None


class TestQueryProcedures:
    def test_get_procedures_newest_first(self):
        repo = ProceduralRepository()
        repo.store_procedure(_make_procedure("p1", created_at=datetime(2026, 1, 1)))
        repo.store_procedure(_make_procedure("p2", created_at=datetime(2026, 1, 2)))
        procedures = repo.get_procedures()
        assert [p.procedure_id for p in procedures] == ["p2", "p1"]

    def test_get_procedures_limit(self):
        repo = ProceduralRepository()
        for i in range(5):
            repo.store_procedure(_make_procedure(f"p{i}"))
        assert len(repo.get_procedures(n=2)) == 2

    def test_get_procedures_zero_limit(self):
        repo = ProceduralRepository()
        repo.store_procedure(_make_procedure("p1"))
        assert repo.get_procedures(n=0) == []

    def test_get_by_category(self):
        repo = ProceduralRepository()
        repo.store_procedure(_make_procedure("p1", category="research"))
        repo.store_procedure(_make_procedure("p2", category="tool"))
        research = repo.get_procedures_by_category("research")
        assert [p.procedure_id for p in research] == ["p1"]

    def test_get_by_kind(self):
        repo = ProceduralRepository()
        repo.store_procedure(_make_procedure("p1", kind=ProcedureKind.DISTILLED))
        repo.store_procedure(_make_procedure("p2", kind=ProcedureKind.MANUAL))
        manuals = repo.get_procedures_by_kind(ProcedureKind.MANUAL)
        assert [p.procedure_id for p in manuals] == ["p2"]

    def test_get_by_tool(self):
        repo = ProceduralRepository()
        step = _make_step("s1", tool_name="search")
        repo.store_procedure(_make_procedure("p1", steps=(step,)))
        repo.store_procedure(_make_procedure("p2"))
        result = repo.get_procedures_by_tool("search")
        assert [p.procedure_id for p in result] == ["p1"]

    def test_get_procedures_since(self):
        repo = ProceduralRepository()
        repo.store_procedure(_make_procedure("p1", created_at=datetime(2026, 1, 1)))
        repo.store_procedure(_make_procedure("p2", created_at=datetime(2026, 1, 2)))
        since = datetime(2026, 1, 2)
        procedures = repo.get_procedures_since(since)
        assert [p.procedure_id for p in procedures] == ["p2"]


class TestRemoveAndUpdate:
    def test_remove_existing(self):
        repo = ProceduralRepository()
        repo.store_procedure(_make_procedure("p1"))
        assert repo.remove_procedure("p1") is True
        assert repo.procedure_count == 0

    def test_remove_missing(self):
        repo = ProceduralRepository()
        assert repo.remove_procedure("missing") is False

    def test_update_procedure(self):
        repo = ProceduralRepository()
        proc = _make_procedure("p1", name="initial")
        repo.store_procedure(proc)
        updated = Procedure(
            procedure_id="p1",
            name="updated",
            success_count=5,
        )
        repo.update_procedure(updated)
        stored = repo.get_procedure("p1")
        assert stored is not None
        assert stored.name == "updated"
        assert stored.success_count == 5


class TestSummaryAndClear:
    def test_summary(self):
        repo = ProceduralRepository(max_procedures=5)
        repo.store_procedure(_make_procedure("p1"))
        summary = repo.summary()
        assert summary["procedure_count"] == 1
        assert summary["max_procedures"] == 5
        assert summary["storage_available"] is False

    def test_clear(self):
        repo = ProceduralRepository()
        repo.store_procedure(_make_procedure("p1"))
        repo.clear()
        assert repo.procedure_count == 0


class _FakeStorage:
    """Minimal LongTermStorage-compatible fake for procedure tests."""

    def __init__(self, available: bool = True):
        self._available = available
        self.procedures: list[Procedure] = []
        self.store_calls: list[str] = []

    def initialize(self) -> None:
        self._available = True

    def close(self) -> None:
        self._available = False

    def is_available(self) -> bool:
        return self._available

    def store_episode(self, episode) -> None:
        pass

    def load_episodes(self) -> list:
        return []

    def load_episode(self, episode_id: str):
        return None

    def store_episode_event(self, event) -> None:
        pass

    def load_episode_events(self, episode_id: str) -> list:
        return []

    def store_procedure(self, procedure: Procedure) -> None:
        self.store_calls.append("store_procedure")
        self.procedures.append(procedure)

    def load_procedures(self) -> list[Procedure]:
        return list(self.procedures)

    def load_procedure(self, procedure_id: str) -> Procedure | None:
        for p in self.procedures:
            if p.procedure_id == procedure_id:
                return p
        return None

    def store_consolidation_record(self, record) -> None:
        pass

    def load_consolidation_records(self) -> list:
        return []


class TestStorageIntegration:
    def test_dual_write_procedure(self):
        storage = _FakeStorage()
        repo = ProceduralRepository(storage=storage)
        proc = _make_procedure("p1")
        repo.store_procedure(proc)
        assert "store_procedure" in storage.store_calls
        assert len(storage.procedures) == 1

    def test_storage_unavailable_does_not_break(self):
        storage = _FakeStorage(available=False)
        repo = ProceduralRepository(storage=storage)
        proc = _make_procedure("p1")
        repo.store_procedure(proc)  # Should not raise
        assert repo.get_procedure("p1") is proc

    def test_storage_write_failure_does_not_break(self):
        class _BrokenStorage(_FakeStorage):
            def store_procedure(self, procedure: Procedure) -> None:
                raise RuntimeError("storage down")

        storage = _BrokenStorage()
        repo = ProceduralRepository(storage=storage)
        proc = _make_procedure("p1")
        repo.store_procedure(proc)  # Should not raise
        assert repo.get_procedure("p1") is proc

    def test_restore_no_storage(self):
        repo = ProceduralRepository()
        result = repo.restore()
        assert result == {"restored_procedures": 0}

    def test_restore_from_storage(self):
        storage = _FakeStorage()
        proc = _make_procedure("p1")
        storage.procedures.append(proc)

        repo = ProceduralRepository(storage=storage)
        result = repo.restore()
        assert result["restored_procedures"] == 1
        assert repo.get_procedure("p1") is not None

    def test_restore_skips_existing(self):
        storage = _FakeStorage()
        proc = _make_procedure("p1", name="from_storage")
        storage.procedures.append(proc)

        repo = ProceduralRepository(storage=storage)
        repo.store_procedure(_make_procedure("p1", name="in_memory"))
        result = repo.restore()
        assert result["restored_procedures"] == 1
        stored = repo.get_procedure("p1")
        assert stored is not None
        assert stored.name == "in_memory"
