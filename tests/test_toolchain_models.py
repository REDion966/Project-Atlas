"""Phase 18.1 — Toolchain toolchain models: data model tests.

Covers immutability (frozen + slots), defaults, enum membership, and
serialization compatibility for atlas/skills/models.py.
"""

import json
from datetime import datetime
from enum import Enum

import pytest

from atlas.toolchain.models import (
    ChainStrategy,
    Skill,
    SkillKind,
    SkillStatus,
    ToolChain,
    ToolChainPlan,
    ToolChainResult,
    ToolEffectivenessRecord,
    ToolEffectivenessScore,
    ToolStep,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestSkillKind:
    def test_members(self):
        expected = {SkillKind.BUILTIN, SkillKind.COMPOSED, SkillKind.LEARNED}
        assert set(SkillKind) == expected

    def test_members_are_enum(self):
        assert issubclass(SkillKind, Enum)


class TestSkillStatus:
    def test_members(self):
        expected = {SkillStatus.DRAFT, SkillStatus.ACTIVE, SkillStatus.DEPRECATED}
        assert set(SkillStatus) == expected


class TestChainStrategy:
    def test_members(self):
        expected = {
            ChainStrategy.SEQUENTIAL,
            ChainStrategy.PARALLEL,
            ChainStrategy.FALLBACK,
            ChainStrategy.CONDITIONAL,
        }
        assert set(ChainStrategy) == expected


# ---------------------------------------------------------------------------
# ToolStep
# ---------------------------------------------------------------------------


class TestToolStep:
    def test_create_minimal(self):
        step = ToolStep(step_id="s1", tool_name="echo")
        assert step.step_id == "s1"
        assert step.tool_name == "echo"
        assert step.parameters == {}
        assert step.depends_on == ()
        assert step.description == ""

    def test_create_full(self):
        step = ToolStep(
            step_id="s2",
            tool_name="search",
            parameters={"q": "atlas"},
            depends_on=("s1",),
            description="Search for atlas",
        )
        assert step.parameters == {"q": "atlas"}
        assert step.depends_on == ("s1",)
        assert step.description == "Search for atlas"

    def test_immutability(self):
        step = ToolStep(step_id="s3", tool_name="echo")
        with pytest.raises(AttributeError):
            step.tool_name = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            step.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        step = ToolStep(
            step_id="s4",
            tool_name="echo",
            parameters={"k": "v"},
            depends_on=("s0",),
        )
        data = step.to_dict()
        assert data["step_id"] == "s4"
        assert data["tool_name"] == "echo"
        assert data["parameters"] == {"k": "v"}
        assert data["depends_on"] == ("s0",)


# ---------------------------------------------------------------------------
# ToolChain
# ---------------------------------------------------------------------------


class TestToolChain:
    def test_create_minimal(self):
        chain = ToolChain(chain_id="c1", goal="do something")
        assert chain.chain_id == "c1"
        assert chain.goal == "do something"
        assert chain.steps == ()
        assert chain.strategy == "sequential"
        assert isinstance(chain.created_at, datetime)
        assert chain.metadata == {}

    def test_create_with_steps(self):
        step = ToolStep(step_id="s1", tool_name="echo")
        chain = ToolChain(
            chain_id="c2",
            goal="echo input",
            steps=(step,),
            strategy="fallback",
        )
        assert chain.step_count == 1
        assert chain.steps == (step,)
        assert chain.strategy == "fallback"
        assert chain.tool_names == ("echo",)

    def test_immutability(self):
        chain = ToolChain(chain_id="c3", goal="g")
        with pytest.raises(AttributeError):
            chain.goal = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            chain.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        step = ToolStep(step_id="s1", tool_name="echo")
        chain = ToolChain(
            chain_id="c4",
            goal="g",
            steps=(step,),
            metadata={"k": "v"},
        )
        data = chain.to_dict()
        assert data["chain_id"] == "c4"
        assert data["goal"] == "g"
        assert data["steps"][0]["step_id"] == "s1"
        assert data["metadata"] == {"k": "v"}
        assert isinstance(data["created_at"], datetime)

    def test_tool_names_property(self):
        step1 = ToolStep(step_id="s1", tool_name="a")
        step2 = ToolStep(step_id="s2", tool_name="b")
        chain = ToolChain(chain_id="c", goal="g", steps=(step1, step2))
        assert chain.tool_names == ("a", "b")

    def test_step_count_property(self):
        chain = ToolChain(chain_id="c", goal="g", steps=())
        assert chain.step_count == 0
        step = ToolStep(step_id="s1", tool_name="a")
        chain2 = ToolChain(chain_id="c2", goal="g", steps=(step,))
        assert chain2.step_count == 1


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


class TestSkill:
    def test_create_minimal(self):
        skill = Skill(skill_id="sk1", name="echo_skill")
        assert skill.skill_id == "sk1"
        assert skill.name == "echo_skill"
        assert skill.description == ""
        assert skill.kind == SkillKind.BUILTIN
        assert skill.category == "utility"
        assert skill.tool_name == ""
        assert skill.chain is None
        assert skill.tags == ()
        assert skill.status == SkillStatus.ACTIVE
        assert isinstance(skill.created_at, datetime)
        assert skill.metadata == {}

    def test_create_builtin(self):
        skill = Skill(
            skill_id="sk2",
            name="echo",
            kind=SkillKind.BUILTIN,
            tool_name="echo",
            tags=("debug", "test"),
        )
        assert skill.is_builtin
        assert not skill.is_composed
        assert skill.is_active
        assert skill.tags == ("debug", "test")

    def test_create_composed(self):
        chain = ToolChain(chain_id="c1", goal="g")
        skill = Skill(
            skill_id="sk3",
            name="composed",
            kind=SkillKind.COMPOSED,
            chain=chain,
        )
        assert skill.is_composed
        assert not skill.is_builtin
        assert skill.chain is chain

    def test_create_learned(self):
        chain = ToolChain(chain_id="c1", goal="g")
        skill = Skill(
            skill_id="sk4",
            name="learned",
            kind=SkillKind.LEARNED,
            chain=chain,
        )
        assert skill.is_composed

    def test_deprecated_skill_not_active(self):
        skill = Skill(
            skill_id="sk5",
            name="old",
            status=SkillStatus.DEPRECATED,
        )
        assert not skill.is_active

    def test_immutability(self):
        skill = Skill(skill_id="sk6", name="n")
        with pytest.raises(AttributeError):
            skill.name = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            skill.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict_builtin(self):
        skill = Skill(
            skill_id="sk7",
            name="echo",
            kind=SkillKind.BUILTIN,
            tool_name="echo",
            tags=("debug",),
        )
        data = skill.to_dict()
        assert data["skill_id"] == "sk7"
        assert data["kind"] == "BUILTIN"
        assert data["status"] == "ACTIVE"
        assert data["chain"] is None
        assert data["tags"] == ("debug",)

    def test_to_dict_composed(self):
        chain = ToolChain(chain_id="c1", goal="g")
        skill = Skill(
            skill_id="sk8",
            name="composed",
            kind=SkillKind.COMPOSED,
            chain=chain,
        )
        data = skill.to_dict()
        assert data["kind"] == "COMPOSED"
        assert data["chain"]["chain_id"] == "c1"


# ---------------------------------------------------------------------------
# ToolChainPlan
# ---------------------------------------------------------------------------


class TestToolChainPlan:
    def test_create_minimal(self):
        plan = ToolChainPlan(plan_id="p1", goal="do something")
        assert plan.plan_id == "p1"
        assert plan.goal == "do something"
        assert plan.steps == ()
        assert plan.strategy == "sequential"
        assert plan.max_depth == 1
        assert isinstance(plan.created_at, datetime)
        assert plan.metadata == {}

    def test_create_with_steps(self):
        step = ToolStep(step_id="s1", tool_name="echo")
        plan = ToolChainPlan(
            plan_id="p2",
            goal="g",
            steps=(step,),
            strategy="fallback",
            max_depth=2,
        )
        assert plan.step_count == 1
        assert not plan.is_empty
        assert plan.strategy == "fallback"
        assert plan.max_depth == 2

    def test_is_empty(self):
        plan = ToolChainPlan(plan_id="p", goal="g")
        assert plan.is_empty
        assert plan.step_count == 0

    def test_immutability(self):
        plan = ToolChainPlan(plan_id="p3", goal="g")
        with pytest.raises(AttributeError):
            plan.goal = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        step = ToolStep(step_id="s1", tool_name="echo")
        plan = ToolChainPlan(
            plan_id="p4",
            goal="g",
            steps=(step,),
            metadata={"k": "v"},
        )
        data = plan.to_dict()
        assert data["plan_id"] == "p4"
        assert data["steps"][0]["step_id"] == "s1"
        assert data["metadata"] == {"k": "v"}


# ---------------------------------------------------------------------------
# ToolChainResult
# ---------------------------------------------------------------------------


class TestToolChainResult:
    def test_defaults(self):
        result = ToolChainResult(chain_id="c1")
        assert result.chain_id == "c1"
        assert not result.success
        assert result.step_results == ()
        assert result.error == ""
        assert result.execution_time_ms == 0.0
        assert result.metadata == {}

    def test_create_full(self):
        result = ToolChainResult(
            chain_id="c2",
            success=True,
            step_results=({"step": "s1", "success": True},),
            execution_time_ms=42.5,
        )
        assert result.success
        assert len(result.step_results) == 1
        assert result.execution_time_ms == 42.5

    def test_immutability(self):
        result = ToolChainResult(chain_id="c3")
        with pytest.raises(AttributeError):
            result.success = True  # type: ignore[misc]

    def test_to_dict(self):
        result = ToolChainResult(
            chain_id="c4",
            success=True,
            step_results=({"s": 1},),
        )
        data = result.to_dict()
        assert data["chain_id"] == "c4"
        assert data["success"] is True
        assert data["step_results"] == ({"s": 1},)


# ---------------------------------------------------------------------------
# ToolEffectivenessRecord
# ---------------------------------------------------------------------------


class TestToolEffectivenessRecord:
    def test_defaults(self):
        record = ToolEffectivenessRecord(record_id="r1", tool_name="echo")
        assert record.record_id == "r1"
        assert record.tool_name == "echo"
        assert not record.success
        assert record.execution_time_ms == 0.0
        assert record.context_hash == ""
        assert record.skill_id == ""
        assert isinstance(record.recorded_at, datetime)
        assert record.metadata == {}

    def test_create_full(self):
        record = ToolEffectivenessRecord(
            record_id="r2",
            tool_name="search",
            success=True,
            execution_time_ms=100.0,
            context_hash="abc123",
            skill_id="sk1",
        )
        assert record.success
        assert record.execution_time_ms == 100.0
        assert record.context_hash == "abc123"
        assert record.skill_id == "sk1"

    def test_immutability(self):
        record = ToolEffectivenessRecord(record_id="r3", tool_name="echo")
        with pytest.raises(AttributeError):
            record.success = True  # type: ignore[misc]

    def test_to_dict(self):
        record = ToolEffectivenessRecord(
            record_id="r4",
            tool_name="echo",
            success=True,
            metadata={"k": "v"},
        )
        data = record.to_dict()
        assert data["record_id"] == "r4"
        assert data["success"] is True
        assert data["metadata"] == {"k": "v"}


# ---------------------------------------------------------------------------
# ToolEffectivenessScore
# ---------------------------------------------------------------------------


class TestToolEffectivenessScore:
    def test_defaults(self):
        score = ToolEffectivenessScore(tool_name="echo")
        assert score.tool_name == "echo"
        assert score.total_observations == 0
        assert score.success_count == 0
        assert score.failure_count == 0
        assert score.success_rate == 0.0
        assert score.avg_execution_time_ms == 0.0
        assert score.effectiveness == 0.0
        assert score.last_observed_at is None

    def test_create_full(self):
        now = datetime.now()
        score = ToolEffectivenessScore(
            tool_name="echo",
            total_observations=10,
            success_count=8,
            failure_count=2,
            success_rate=0.8,
            avg_execution_time_ms=50.0,
            effectiveness=0.75,
            last_observed_at=now,
        )
        assert score.total_observations == 10
        assert score.success_rate == 0.8
        assert score.effectiveness == 0.75
        assert score.last_observed_at == now

    def test_immutability(self):
        score = ToolEffectivenessScore(tool_name="echo")
        with pytest.raises(AttributeError):
            score.effectiveness = 1.0  # type: ignore[misc]

    def test_to_dict(self):
        now = datetime.now()
        score = ToolEffectivenessScore(
            tool_name="echo",
            total_observations=5,
            effectiveness=0.9,
            last_observed_at=now,
        )
        data = score.to_dict()
        assert data["tool_name"] == "echo"
        assert data["total_observations"] == 5
        assert data["effectiveness"] == 0.9
        assert data["last_observed_at"] == now.isoformat()

    def test_to_dict_none_last_observed(self):
        score = ToolEffectivenessScore(tool_name="echo")
        data = score.to_dict()
        assert data["last_observed_at"] is None


# ---------------------------------------------------------------------------
# Serialization compatibility
# ---------------------------------------------------------------------------


class TestSerializationCompatibility:
    def test_nested_chain_serializes_to_json(self):
        step = ToolStep(step_id="s1", tool_name="echo", parameters={"k": "v"})
        chain = ToolChain(chain_id="c1", goal="g", steps=(step,))
        skill = Skill(
            skill_id="sk1",
            name="n",
            kind=SkillKind.COMPOSED,
            chain=chain,
        )
        data = skill.to_dict()

        def drop_datetimes(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: drop_datetimes(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [drop_datetimes(v) for v in value]
            return value

        payload = json.dumps(drop_datetimes(data))
        parsed = json.loads(payload)
        assert parsed["skill_id"] == "sk1"
        assert parsed["chain"]["chain_id"] == "c1"
        assert parsed["chain"]["steps"][0]["tool_name"] == "echo"

    def test_plan_serializes_to_json(self):
        step = ToolStep(step_id="s1", tool_name="echo")
        plan = ToolChainPlan(plan_id="p1", goal="g", steps=(step,))
        data = plan.to_dict()

        def drop_datetimes(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: drop_datetimes(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [drop_datetimes(v) for v in value]
            return value

        payload = json.dumps(drop_datetimes(data))
        parsed = json.loads(payload)
        assert parsed["plan_id"] == "p1"
        assert parsed["steps"][0]["step_id"] == "s1"

    def test_enum_names_are_stable_strings(self):
        skill = Skill(skill_id="sk1", name="n", kind=SkillKind.LEARNED)
        assert skill.to_dict()["kind"] == "LEARNED"
        chain = ToolChain(chain_id="c", goal="g", strategy="fallback")
        assert chain.to_dict()["strategy"] == "fallback"