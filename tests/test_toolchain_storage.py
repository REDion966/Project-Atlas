"""Phase 18.8 — Toolchain SQLite Storage tests.

Covers:
  - SQLite lifecycle (initialize, close, is_available)
  - initialization (idempotent, migrations applied)
  - persistence (round-trip for skills, chains, records, plans, results)
  - serialization (datetime round-trip, metadata round-trip, nested chain)
  - migration v8 (schema version, additive tables, existing tables untouched)
  - unavailable storage (write before initialize raises)
  - deterministic behavior (same data → same loaded fields)
"""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.storage.toolchain_storage import ToolchainSQLiteStorage
from atlas.toolchain.models import (
    Skill,
    SkillKind,
    SkillStatus,
    ToolChain,
    ToolChainPlan,
    ToolChainResult,
    ToolEffectivenessRecord,
    ToolStep,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    """A fresh, initialized ToolchainSQLiteStorage."""
    adapter = ToolchainSQLiteStorage(db_path=tmp_path / "toolchain_test.db")
    adapter.initialize()
    assert adapter.is_available()
    yield adapter
    adapter.close()


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_step(
    step_id: str = "step:0000",
    tool_name: str = "read_file",
    parameters: dict | None = None,
    depends_on: tuple[str, ...] = (),
    description: str = "Read a file.",
) -> ToolStep:
    return ToolStep(
        step_id=step_id,
        tool_name=tool_name,
        parameters=parameters or {"path": "/tmp/test.txt"},
        depends_on=depends_on,
        description=description,
    )


def make_chain(
    chain_id: str = "chain::test:1",
    goal: str = "Read and search.",
    steps: tuple[ToolStep, ...] | None = None,
    strategy: str = "sequential",
    metadata: dict | None = None,
) -> ToolChain:
    return ToolChain(
        chain_id=chain_id,
        goal=goal,
        steps=steps or (make_step(), make_step("step:0001", "search")),
        strategy=strategy,
        metadata=metadata or {"source": "test"},
    )


def make_skill(
    skill_id: str = "skill:test:1",
    name: str = "Read File",
    kind: SkillKind = SkillKind.BUILTIN,
    chain: ToolChain | None = None,
    status: SkillStatus = SkillStatus.ACTIVE,
    category: str = "file",
    tags: tuple[str, ...] = ("file", "read"),
    metadata: dict | None = None,
) -> Skill:
    return Skill(
        skill_id=skill_id,
        name=name,
        description="Reads a file from disk.",
        kind=kind,
        category=category,
        tool_name="read_file" if kind == SkillKind.BUILTIN else "",
        chain=chain,
        tags=tags,
        status=status,
        metadata=metadata or {"version": 1},
    )


def make_composed_skill(skill_id: str = "skill:test:2") -> Skill:
    return make_skill(
        skill_id=skill_id,
        name="Search And Read",
        kind=SkillKind.COMPOSED,
        chain=make_chain(),
        category="search",
    )


def make_record(
    record_id: str = "eff:read_file:abc123",
    tool_name: str = "read_file",
    success: bool = True,
    execution_time_ms: float = 10.0,
    skill_id: str = "skill:test:1",
    metadata: dict | None = None,
) -> ToolEffectivenessRecord:
    return ToolEffectivenessRecord(
        record_id=record_id,
        tool_name=tool_name,
        success=success,
        execution_time_ms=execution_time_ms,
        context_hash="abc123",
        skill_id=skill_id,
        metadata=metadata or {"run": 1},
    )


def make_plan(
    plan_id: str = "plan::test:1",
    goal: str = "Read a file.",
    steps: tuple[ToolStep, ...] | None = None,
    strategy: str = "sequential",
    max_depth: int = 1,
    metadata: dict | None = None,
) -> ToolChainPlan:
    return ToolChainPlan(
        plan_id=plan_id,
        goal=goal,
        steps=steps or (make_step(),),
        strategy=strategy,
        max_depth=max_depth,
        metadata=metadata or {"planner": "test"},
    )


def make_result(
    chain_id: str = "chain::test:1",
    success: bool = True,
    error: str = "",
    metadata: dict | None = None,
) -> ToolChainResult:
    return ToolChainResult(
        chain_id=chain_id,
        success=success,
        step_results=(
            {
                "step_id": "step:0000",
                "tool_name": "read_file",
                "success": True,
                "output": {"content": "hello"},
                "error": "",
                "execution_time_ms": 1.0,
            },
        ),
        error=error,
        execution_time_ms=5.0,
        metadata=metadata or {"strategy": "sequential"},
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_initialize_and_close(self, tmp_path):
        adapter = ToolchainSQLiteStorage(db_path=tmp_path / "x.db")
        adapter.initialize()
        assert adapter.is_available()
        adapter.close()
        assert not adapter.is_available()

    def test_initialize_is_idempotent(self, tmp_path):
        adapter = ToolchainSQLiteStorage(db_path=tmp_path / "x.db")
        adapter.initialize()
        adapter.initialize()  # second call is a no-op
        assert adapter.is_available()
        adapter.close()

    def test_unavailable_write_raises(self):
        adapter = ToolchainSQLiteStorage()  # never initialized
        with pytest.raises(Exception):
            adapter.store_skill(make_skill())


# ---------------------------------------------------------------------------
# Skill round-trip
# ---------------------------------------------------------------------------


class TestSkillRoundTrip:
    def test_store_and_load_builtin(self, storage):
        skill = make_skill()
        storage.store_skill(skill)
        loaded = storage.load_skills()
        assert len(loaded) == 1
        assert loaded[0].skill_id == skill.skill_id
        assert loaded[0].name == skill.name
        assert loaded[0].kind == SkillKind.BUILTIN
        assert loaded[0].category == skill.category
        assert loaded[0].tool_name == skill.tool_name
        assert loaded[0].status == skill.status
        assert loaded[0].tags == skill.tags

    def test_store_and_load_composed(self, storage):
        skill = make_composed_skill()
        storage.store_skill(skill)
        loaded = storage.load_skills()
        assert len(loaded) == 1
        assert loaded[0].kind == SkillKind.COMPOSED
        assert loaded[0].chain is not None
        assert loaded[0].chain.chain_id == "chain::test:1"
        assert loaded[0].chain.goal == "Read and search."
        assert len(loaded[0].chain.steps) == 2

    def test_upsert_is_idempotent(self, storage):
        skill = make_skill()
        storage.store_skill(skill)
        storage.store_skill(skill)
        assert len(storage.load_skills()) == 1

    def test_metadata_round_trip(self, storage):
        skill = make_skill(metadata={"k": "v", "n": 42})
        storage.store_skill(skill)
        loaded = storage.load_skills()
        assert loaded[0].metadata == {"k": "v", "n": 42}

    def test_datetime_round_trip(self, storage):
        skill = make_skill()
        storage.store_skill(skill)
        loaded = storage.load_skills()
        assert isinstance(loaded[0].created_at, datetime)


# ---------------------------------------------------------------------------
# Chain round-trip
# ---------------------------------------------------------------------------


class TestChainRoundTrip:
    def test_store_and_load(self, storage):
        chain = make_chain()
        storage.store_chain(chain)
        loaded = storage.load_chains()
        assert len(loaded) == 1
        assert loaded[0].chain_id == chain.chain_id
        assert loaded[0].goal == chain.goal
        assert loaded[0].strategy == chain.strategy
        assert len(loaded[0].steps) == 2
        assert loaded[0].steps[0].step_id == "step:0000"
        assert loaded[0].steps[0].tool_name == "read_file"
        assert loaded[0].steps[0].parameters == {"path": "/tmp/test.txt"}

    def test_upsert_is_idempotent(self, storage):
        chain = make_chain()
        storage.store_chain(chain)
        storage.store_chain(chain)
        assert len(storage.load_chains()) == 1

    def test_step_depends_on_round_trip(self, storage):
        chain = ToolChain(
            chain_id="chain::dep",
            goal="Dep chain.",
            steps=(
                ToolStep(step_id="step:a", tool_name="tool_a"),
                ToolStep(
                    step_id="step:b",
                    tool_name="tool_b",
                    depends_on=("step:a",),
                ),
            ),
            strategy="sequential",
        )
        storage.store_chain(chain)
        loaded = storage.load_chains()
        assert loaded[0].steps[1].depends_on == ("step:a",)


# ---------------------------------------------------------------------------
# Effectiveness record round-trip
# ---------------------------------------------------------------------------


class TestEffectivenessRecordRoundTrip:
    def test_store_and_load(self, storage):
        record = make_record()
        storage.store_effectiveness_record(record)
        loaded = storage.load_effectiveness_records()
        assert len(loaded) == 1
        assert loaded[0].record_id == record.record_id
        assert loaded[0].tool_name == record.tool_name
        assert loaded[0].success == record.success
        assert loaded[0].execution_time_ms == record.execution_time_ms
        assert loaded[0].context_hash == record.context_hash
        assert loaded[0].skill_id == record.skill_id

    def test_append_only_ignores_duplicate(self, storage):
        record = make_record()
        storage.store_effectiveness_record(record)
        storage.store_effectiveness_record(record)  # same record_id → IGNORE
        assert len(storage.load_effectiveness_records()) == 1

    def test_multiple_records(self, storage):
        storage.store_effectiveness_record(make_record("eff:a", "read_file"))
        storage.store_effectiveness_record(make_record("eff:b", "search"))
        loaded = storage.load_effectiveness_records()
        assert len(loaded) == 2

    def test_datetime_round_trip(self, storage):
        record = make_record()
        storage.store_effectiveness_record(record)
        loaded = storage.load_effectiveness_records()
        assert isinstance(loaded[0].recorded_at, datetime)

    def test_metadata_round_trip(self, storage):
        record = make_record(metadata={"k": "v"})
        storage.store_effectiveness_record(record)
        loaded = storage.load_effectiveness_records()
        assert loaded[0].metadata == {"k": "v"}


# ---------------------------------------------------------------------------
# Plan round-trip
# ---------------------------------------------------------------------------


class TestPlanRoundTrip:
    def test_store_and_load(self, storage):
        plan = make_plan()
        storage.store_plan(plan)
        loaded = storage.load_plans()
        assert len(loaded) == 1
        assert loaded[0].plan_id == plan.plan_id
        assert loaded[0].goal == plan.goal
        assert loaded[0].strategy == plan.strategy
        assert loaded[0].max_depth == plan.max_depth
        assert len(loaded[0].steps) == 1
        assert loaded[0].steps[0].tool_name == "read_file"

    def test_upsert_is_idempotent(self, storage):
        plan = make_plan()
        storage.store_plan(plan)
        storage.store_plan(plan)
        assert len(storage.load_plans()) == 1

    def test_metadata_round_trip(self, storage):
        plan = make_plan(metadata={"k": "v"})
        storage.store_plan(plan)
        loaded = storage.load_plans()
        assert loaded[0].metadata == {"k": "v"}


# ---------------------------------------------------------------------------
# Result round-trip
# ---------------------------------------------------------------------------


class TestResultRoundTrip:
    def test_store_and_load(self, storage):
        result = make_result()
        storage.store_result(result)
        loaded = storage.load_results()
        assert len(loaded) == 1
        assert loaded[0].chain_id == result.chain_id
        assert loaded[0].success == result.success
        assert loaded[0].error == result.error
        assert loaded[0].execution_time_ms == result.execution_time_ms
        assert len(loaded[0].step_results) == 1
        assert loaded[0].step_results[0]["tool_name"] == "read_file"

    def test_append_only_keeps_multiple(self, storage):
        result = make_result()
        storage.store_result(result)
        storage.store_result(result)  # different result_id (timestamp)
        loaded = storage.load_results()
        assert len(loaded) == 2

    def test_failed_result_round_trip(self, storage):
        result = make_result(success=False, error="Step failed.")
        storage.store_result(result)
        loaded = storage.load_results()
        assert not loaded[0].success
        assert loaded[0].error == "Step failed."

    def test_metadata_round_trip(self, storage):
        result = make_result(metadata={"k": "v"})
        storage.store_result(result)
        loaded = storage.load_results()
        assert loaded[0].metadata == {"k": "v"}


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigration:
    def test_schema_version_reaches_v8(self, tmp_path):
        adapter = ToolchainSQLiteStorage(db_path=tmp_path / "m.db")
        adapter.initialize()
        assert adapter.get_schema_version() >= 8
        adapter.close()

    def test_migrations_are_additive(self, tmp_path):
        adapter = ToolchainSQLiteStorage(db_path=tmp_path / "m.db")
        adapter.initialize()
        tables = {
            row[0]
            for row in adapter._execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "toolchain_skills",
            "toolchain_chains",
            "toolchain_effectiveness_records",
            "toolchain_plans",
            "toolchain_reports",
        }.issubset(tables)
        # Existing schema tables are untouched
        assert "experiences" in tables
        assert "research_sources" in tables
        adapter.close()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_chain_nested_in_skill_round_trip(self, storage):
        skill = make_composed_skill()
        storage.store_skill(skill)
        loaded = storage.load_skills()
        chain = loaded[0].chain
        assert chain is not None
        assert chain.steps[0].parameters == {"path": "/tmp/test.txt"}
        assert chain.steps[0].description == "Read a file."

    def test_step_parameters_round_trip(self, storage):
        chain = ToolChain(
            chain_id="chain::params",
            goal="Params chain.",
            steps=(
                ToolStep(
                    step_id="step:0000",
                    tool_name="read_file",
                    parameters={"path": "/a/b/c.txt", "mode": "r"},
                ),
            ),
        )
        storage.store_chain(chain)
        loaded = storage.load_chains()
        assert loaded[0].steps[0].parameters == {"path": "/a/b/c.txt", "mode": "r"}

    def test_datetime_fields_round_trip(self, storage):
        chain = make_chain()
        storage.store_chain(chain)
        loaded = storage.load_chains()
        assert isinstance(loaded[0].created_at, datetime)


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


class TestRecovery:
    def test_close_then_reopen_persists(self, tmp_path):
        path = tmp_path / "persist.db"
        adapter = ToolchainSQLiteStorage(db_path=path)
        adapter.initialize()
        adapter.store_skill(make_skill())
        adapter.store_chain(make_chain())
        adapter.close()

        reopened = ToolchainSQLiteStorage(db_path=path)
        reopened.initialize()
        assert len(reopened.load_skills()) == 1
        assert len(reopened.load_chains()) == 1
        reopened.close()


# ---------------------------------------------------------------------------
# Deterministic behavior
# ---------------------------------------------------------------------------


class TestDeterministicBehavior:
    def test_same_skill_data_loads_identically(self, storage):
        skill = make_skill(metadata={"k": "v"})
        storage.store_skill(skill)
        first_load = storage.load_skills()
        second_load = storage.load_skills()
        assert len(first_load) == len(second_load)
        assert first_load[0].skill_id == second_load[0].skill_id
        assert first_load[0].metadata == second_load[0].metadata

    def test_same_chain_data_loads_identically(self, storage):
        chain = make_chain()
        storage.store_chain(chain)
        first_load = storage.load_chains()
        second_load = storage.load_chains()
        assert first_load[0].chain_id == second_load[0].chain_id
        assert first_load[0].steps[0].tool_name == second_load[0].steps[0].tool_name

    def test_same_result_data_loads_identically(self, storage):
        result = make_result()
        storage.store_result(result)
        first_load = storage.load_results()
        second_load = storage.load_results()
        assert first_load[0].chain_id == second_load[0].chain_id
        assert first_load[0].success == second_load[0].success
        assert (
            first_load[0].step_results[0]["tool_name"]
            == second_load[0].step_results[0]["tool_name"]
        )