"""Phase 18.3 — SkillRegistry tests."""

import pytest

from atlas.toolchain.models import (
    Skill,
    SkillKind,
    SkillStatus,
    ToolChain,
    ToolStep,
)
from atlas.toolchain.registry import SkillRegistry


def make_builtin_skill(
    skill_id="sk1",
    name="echo_skill",
    tool_name="echo",
    category="utility",
    tags=("debug",),
):
    return Skill(
        skill_id=skill_id,
        name=name,
        kind=SkillKind.BUILTIN,
        tool_name=tool_name,
        category=category,
        tags=tags,
    )


def make_composed_skill(skill_id="sk_c1", name="composed"):
    step = ToolStep(step_id="s1", tool_name="echo")
    chain = ToolChain(chain_id="c1", goal="g", steps=(step,))
    return Skill(
        skill_id=skill_id,
        name=name,
        kind=SkillKind.COMPOSED,
        chain=chain,
        category="utility",
    )


class TestRegistration:
    def test_empty_registry(self):
        registry = SkillRegistry()
        assert registry.count == 0
        assert registry.list() == []

    def test_register_and_get(self):
        registry = SkillRegistry()
        skill = make_builtin_skill()
        registry.register(skill)
        assert registry.count == 1
        assert registry.get("sk1") is skill

    def test_register_duplicate_raises(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill())
        with pytest.raises(ValueError):
            registry.register(make_builtin_skill())

    def test_get_nonexistent_returns_none(self):
        registry = SkillRegistry()
        assert registry.get("nonexistent") is None

    def test_get_by_name(self):
        registry = SkillRegistry()
        skill = make_builtin_skill(name="my_skill")
        registry.register(skill)
        assert registry.get_by_name("my_skill") is skill

    def test_get_by_name_nonexistent(self):
        registry = SkillRegistry()
        assert registry.get_by_name("nonexistent") is None

    def test_get_by_name_returns_first_match(self):
        registry = SkillRegistry()
        s1 = make_builtin_skill(skill_id="sk1", name="dup")
        s2 = make_builtin_skill(skill_id="sk2", name="dup")
        registry.register(s1)
        registry.register(s2)
        result = registry.get_by_name("dup")
        assert result is s1


class TestUnregister:
    def test_unregister(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill())
        registry.unregister("sk1")
        assert registry.count == 0
        assert registry.get("sk1") is None

    def test_unregister_nonexistent_raises(self):
        registry = SkillRegistry()
        with pytest.raises(KeyError):
            registry.unregister("nonexistent")


class TestListing:
    def test_list_sorted_by_id(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(skill_id="sk_c"))
        registry.register(make_builtin_skill(skill_id="sk_a"))
        registry.register(make_builtin_skill(skill_id="sk_b"))
        ids = [s.skill_id for s in registry.list()]
        assert ids == ["sk_a", "sk_b", "sk_c"]

    def test_list_active(self):
        registry = SkillRegistry()
        active = make_builtin_skill(skill_id="sk1", name="active")
        deprecated = Skill(
            skill_id="sk2",
            name="old",
            status=SkillStatus.DEPRECATED,
        )
        registry.register(active)
        registry.register(deprecated)
        active_list = registry.list_active()
        assert len(active_list) == 1
        assert active_list[0].skill_id == "sk1"

    def test_skill_ids_sorted(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(skill_id="sk_b"))
        registry.register(make_builtin_skill(skill_id="sk_a"))
        assert registry.skill_ids == ["sk_a", "sk_b"]


class TestFiltering:
    def test_find_by_category(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(skill_id="sk1", category="file"))
        registry.register(make_builtin_skill(skill_id="sk2", category="search"))
        registry.register(make_builtin_skill(skill_id="sk3", category="file"))
        results = registry.find_by_category("file")
        assert len(results) == 2
        assert {s.skill_id for s in results} == {"sk1", "sk3"}

    def test_find_by_category_no_match(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(category="file"))
        assert registry.find_by_category("network") == []

    def test_find_by_tag(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(skill_id="sk1", tags=("debug",)))
        registry.register(make_builtin_skill(skill_id="sk2", tags=("search",)))
        results = registry.find_by_tag("debug")
        assert len(results) == 1
        assert results[0].skill_id == "sk1"

    def test_find_by_tag_no_match(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(tags=("debug",)))
        assert registry.find_by_tag("nonexistent") == []

    def test_find_by_kind(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(skill_id="sk1"))
        registry.register(make_composed_skill(skill_id="sk2"))
        builtin = registry.find_by_kind(SkillKind.BUILTIN)
        composed = registry.find_by_kind(SkillKind.COMPOSED)
        assert len(builtin) == 1
        assert builtin[0].skill_id == "sk1"
        assert len(composed) == 1
        assert composed[0].skill_id == "sk2"

    def test_find_by_tool_builtin(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(skill_id="sk1", tool_name="echo"))
        results = registry.find_by_tool("echo")
        assert len(results) == 1
        assert results[0].skill_id == "sk1"

    def test_find_by_tool_composed(self):
        registry = SkillRegistry()
        registry.register(make_composed_skill(skill_id="sk1"))
        results = registry.find_by_tool("echo")
        assert len(results) == 1
        assert results[0].skill_id == "sk1"

    def test_find_by_tool_no_match(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(tool_name="echo"))
        assert registry.find_by_tool("nonexistent") == []


class TestStatusTransitions:
    def test_activate_draft_skill(self):
        registry = SkillRegistry()
        draft = Skill(
            skill_id="sk1",
            name="draft",
            status=SkillStatus.DRAFT,
        )
        registry.register(draft)
        activated = registry.activate("sk1")
        assert activated.status == SkillStatus.ACTIVE
        assert activated.is_active
        # Registry holds the new instance
        assert registry.get("sk1") is activated

    def test_activate_already_active_is_noop(self):
        registry = SkillRegistry()
        skill = make_builtin_skill()
        registry.register(skill)
        result = registry.activate("sk1")
        assert result is skill

    def test_deactivate_skill(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill())
        deprecated = registry.deactivate("sk1")
        assert deprecated.status == SkillStatus.DEPRECATED
        assert not deprecated.is_active
        assert registry.get("sk1") is deprecated

    def test_deactivate_already_deprecated_is_noop(self):
        registry = SkillRegistry()
        skill = Skill(
            skill_id="sk1",
            name="old",
            status=SkillStatus.DEPRECATED,
        )
        registry.register(skill)
        result = registry.deactivate("sk1")
        assert result is skill

    def test_activate_nonexistent_raises(self):
        registry = SkillRegistry()
        with pytest.raises(KeyError):
            registry.activate("nonexistent")

    def test_deactivate_nonexistent_raises(self):
        registry = SkillRegistry()
        with pytest.raises(KeyError):
            registry.deactivate("nonexistent")

    def test_status_transition_preserves_fields(self):
        registry = SkillRegistry()
        skill = Skill(
            skill_id="sk1",
            name="myname",
            description="desc",
            kind=SkillKind.BUILTIN,
            category="file",
            tool_name="echo",
            tags=("debug",),
            metadata={"k": "v"},
        )
        registry.register(skill)
        activated = registry.activate("sk1")
        assert activated.name == "myname"
        assert activated.description == "desc"
        assert activated.category == "file"
        assert activated.tool_name == "echo"
        assert activated.tags == ("debug",)
        assert activated.metadata == {"k": "v"}


class TestProperties:
    def test_count(self):
        registry = SkillRegistry()
        assert registry.count == 0
        registry.register(make_builtin_skill())
        assert registry.count == 1

    def test_active_count(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(skill_id="sk1"))
        registry.register(
            Skill(skill_id="sk2", name="old", status=SkillStatus.DEPRECATED)
        )
        assert registry.active_count == 1

    def test_skill_ids(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill(skill_id="sk1"))
        registry.register(make_builtin_skill(skill_id="sk2"))
        assert registry.skill_ids == ["sk1", "sk2"]


class TestMaintenance:
    def test_clear(self):
        registry = SkillRegistry()
        registry.register(make_builtin_skill())
        registry.register(make_builtin_skill(skill_id="sk2"))
        registry.clear()
        assert registry.count == 0
        assert registry.list() == []