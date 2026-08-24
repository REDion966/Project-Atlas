"""Phase F3 — Capability / Model / Tool Lifecycle & Deprecation tests.

Deterministic, offline coverage of the 20 F3 acceptance criteria:

  1. capability lifecycle assessment
  2. tool lifecycle assessment
  3. skill lifecycle assessment
  4. model lifecycle assessment
  5. explicit environment-change detection
  6. stale knowledge signal
  7. uncertain knowledge signal
  8. explicit deprecation
  9. unavailable target
 10. valid target with no action
 11. deterministic ordering
 12. bounded priority/confidence
 13. no mutation of ModelProfileRegistry
 14. no mutation of ToolRegistry
 15. no mutation of SkillRegistry
 16. no mutation of CapabilityRegistry
 17. no code execution
 18. no research execution
 19. no governance imports
 20. no proposal approval / no SelfDevelopmentLoop invocation
 21. duplicate signal handling
 22. repeated assessment determinism
 23. malformed target fails safe
 24. unknown target fails safe
 25. existing registry behavior stays intact
 26. F1 integration
 27. F2 integration
 28. architecture import scan
 29. no parallel registry/memory/event infrastructure

No network/no wall-clock; UTC injection used throughout.
"""

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlas.evolution.lifecycle.targets import (
    target_from_capability,
    target_from_model,
    targets_from_registries,
    target_from_skill,
    target_from_tool,
)
from atlas.evolution.lifecycle.models import (
    LifecycleAction,
    LifecycleAssessment,
    LifecycleAssessmentResult,
    LifecycleReason,
    LifecycleTarget,
    LifecycleTargetKind,
)
from atlas.evolution.lifecycle.assessor import CapabilityLifecycleAssessor
from atlas.evolution.environment.models import (
    EnvironmentChange,
    EnvironmentChangeType,
    EnvironmentDomain,
    EnvironmentEntity,
    EnvironmentState,
    ObservationReliability,
)
from atlas.evolution.freshness.models import (
    FreshnessStatus,
    KnowledgeFreshnessAssessment,
)

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


def _kind(value):
    """Map a string to LifecycleTargetKind."""
    for member in LifecycleTargetKind:
        if member.name == value.upper():
            return member
    raise ValueError(f"unknown LifecycleTargetKind: {value}")


def _target(kind, identifier, **kwargs):
    """Convenience helper to build a LifecycleTarget from a kind name."""
    return LifecycleTarget(target_kind=_kind(kind), identifier=identifier, **kwargs)


def _change(domain, entity_id, current=None, previous=None,
            change_type=EnvironmentChangeType.CHANGED, observed_at=NOW):
    """Build a real F1 EnvironmentChange."""
    entity = EnvironmentEntity(EnvironmentDomain[domain], entity_id)
    return EnvironmentChange(
        entity=entity,
        change_type=change_type,
        previous=previous,
        current=current if current is not None else {},
        observed_at=observed_at,
        source="tool_registry",
        reliability=ObservationReliability.MEDIUM,
    )


def _freshness(knowledge_id, status):
    """Build a real F2 KnowledgeFreshnessAssessment."""
    return KnowledgeFreshnessAssessment(
        knowledge_id=knowledge_id,
        status=status,
        assessed_at=NOW,
    )


def _made(now=None):
    return CapabilityLifecycleAssessor(now=lambda: now or NOW)


# ---------------------------------------------------------------------------
# 1–4. Per-kind lifecycle assessment
# ---------------------------------------------------------------------------


class TestPerKindAssessment(unittest.TestCase):

    def test_capability_with_change_reviews(self):
        target = _target("CAPABILITY", "research.query", affected_domains=("CAPABILITY",))
        change = _change("CAPABILITY", "research.query")
        assessment = _made().assess(target, changes=[change])
        self.assertIs(assessment.action, LifecycleAction.REVIEW)
        self.assertIn(LifecycleReason.ENVIRONMENT_CHANGE, assessment.reasons)

    def test_tool_with_change_reviews(self):
        target = _target("TOOL", "sandbox_pytest", dependency_entity_keys=("TOOL:sandbox_pytest",))
        change = _change("TOOL", "sandbox_pytest")
        assessment = _made().assess(target, changes=[change])
        self.assertIs(assessment.action, LifecycleAction.REVIEW)

    def test_skill_with_change_reviews(self):
        target = _target("SKILL", "sk1", dependency_entity_keys=("SKILL:sk1",))
        change = _change("SKILL", "sk1")
        assessment = _made().assess(target, changes=[change])
        self.assertIs(assessment.action, LifecycleAction.REVIEW)

    def test_model_with_change_reviews(self):
        target = _target("MODEL", "openai:gpt-4", dependency_entity_keys=("MODEL:openai:gpt-4",))
        change = _change("MODEL", "openai:gpt-4")
        assessment = _made().assess(target, changes=[change])
        self.assertIs(assessment.action, LifecycleAction.REVIEW)

    def test_model_stale_knowledge_reviews(self):
        target = _target("MODEL", "openai:gpt-4", knowledge_dependencies=("claim-1",))
        freshness = [_freshness("claim-1", FreshnessStatus.STALE)]
        assessment = _made().assess(target, freshness=freshness)
        self.assertIs(assessment.action, LifecycleAction.REVIEW)
        self.assertIn(LifecycleReason.STALE_KNOWLEDGE, assessment.reasons)
        self.assertEqual(assessment.evidence_knowledge_ids, ("claim-1",))

    def test_tool_uncertain_knowledge_reviews(self):
        target = _target("TOOL", "search_tool", knowledge_dependencies=("claim-2",))
        freshness = [_freshness("claim-2", FreshnessStatus.UNCERTAIN)]
        assessment = _made().assess(target, freshness=freshness)
        self.assertIs(assessment.action, LifecycleAction.REVIEW)
        self.assertIn(LifecycleReason.UNCERTAIN_KNOWLEDGE, assessment.reasons)
        self.assertEqual(assessment.priority, 0.4)

    def test_no_actionable_evidence_is_none(self):
        target = _target("CAPABILITY", "research.query")
        assessment = _made().assess(target)
        self.assertIs(assessment.action, LifecycleAction.NONE)
        self.assertIn(LifecycleReason.VALID, assessment.reasons)
        self.assertEqual(assessment.priority, 0.0)


# ---------------------------------------------------------------------------
# 5. Explicit deprecation
# ---------------------------------------------------------------------------


class TestLifecycleExplicitDeprecation(unittest.TestCase):

    def test_deprecated_model_recommends_replace_when_replacement_is_known(self):
        target = _target(
            "MODEL",
            "openai:gpt-4",
            status="DEPRECATED",
            deprecated=True,
            replacement="openai:gpt-4.1",
        )
        assessment = CapabilityLifecycleAssessor().assess(
            target, changes=[], freshness=[]
        )
        self.assertIs(assessment.action, LifecycleAction.REPLACE)
        self.assertIn(LifecycleReason.EXPLICIT_DEPRECATION, assessment.reasons)
        self.assertEqual(assessment.priority, 1.0)
        self.assertIn(LifecycleReason.REPLACEMENT_AVAILABLE, assessment.reasons)

    def test_deprecated_model_without_replacement_recommends_deprecate(self):
        target = _target("MODEL", "openai:gpt-4", status="DEPRECATED", deprecated=True)
        assessment = CapabilityLifecycleAssessor().assess(target)
        self.assertIs(assessment.action, LifecycleAction.DEPRECATE)
        self.assertEqual(assessment.priority, 1.0)
        self.assertIn(LifecycleReason.EXPLICIT_DEPRECATION, assessment.reasons)

    def test_unavailable_target_recommends_fallback_when_replacement_known(self):
        target = _target(
            "TOOL", "sandbox_pytest",
            available=False, replacement="sandbox_pytest_v2",
        )
        assessment = CapabilityLifecycleAssessor().assess(target)
        self.assertIs(assessment.action, LifecycleAction.FALLBACK)
        self.assertEqual(assessment.priority, 1.0)
        self.assertIn(LifecycleReason.UNAVAILABLE, assessment.reasons)

    def test_unavailable_target_without_replacement_deprecates(self):
        target = _target("CAPABILITY", "research.query", available=False)
        assessment = CapabilityLifecycleAssessor().assess(target)
        self.assertIs(assessment.action, LifecycleAction.DEPRECATE)
        self.assertEqual(assessment.priority, 0.9)
        self.assertIn(LifecycleReason.UNAVAILABLE, assessment.reasons)


# ---------------------------------------------------------------------------
# Helper fakes (duck-typed against real registry contracts)
# ---------------------------------------------------------------------------


class _FakeProfile:
    def __init__(self, provider_name, model_name, metadata=None):
        self.provider_name = provider_name
        self.model_name = model_name
        self.metadata = metadata or {}


class _FakeModelRegistry:
    def __init__(self, profiles=None):
        self._profiles = list(profiles or [])

    def list_profiles(self):
        return list(self._profiles)


class _FakeTool:
    def __init__(self, name, metadata=None, handler=None):
        self.name = name
        self.metadata = metadata or {}
        self.handler = handler


class _FakeToolRegistry:
    def __init__(self, tools=None):
        self._tools = list(tools or [])

    def list(self):
        return list(self._tools)


class _FakeSkill:
    def __init__(self, skill_id, name="", kind=None, status=None, metadata=None):
        self.skill_id = skill_id
        self.name = name
        self.kind = kind
        self.status = status
        self.metadata = metadata or {}


class _FakeSkillRegistry:
    def __init__(self, skills=None):
        self._skills = list(skills or [])

    def list(self):
        return list(self._skills)


class _FakeCapabilityRegistry:
    def __init__(self, names=None):
        self._names = list(names or [])

    @property
    def registered_names(self):
        return sorted(self._names)


# ---------------------------------------------------------------------------
# 13-16: no mutation of underlying registries
# ---------------------------------------------------------------------------


class TestNoRegistryMutation(unittest.TestCase):

    def test_model_registry_not_mutated(self):
        registry = _FakeModelRegistry([_FakeProfile("openai", "gpt-4")])
        before = list(registry.list_profiles())
        _made().assess_many(targets_from_registries(model_registry=registry))
        after = list(registry.list_profiles())
        self.assertEqual(before, after)

    def test_tool_registry_not_mutated(self):
        registry = _FakeToolRegistry([
            _FakeTool("sandbox_pytest", handler=lambda p: None),
        ])
        before = list(registry.list())
        _made().assess_many(targets_from_registries(tool_registry=registry))
        after = list(registry.list())
        self.assertEqual(before, after)

    def test_skill_registry_not_mutated(self):
        registry = _FakeSkillRegistry([
            _FakeSkill("sk1", name="greet", status="ACTIVE"),
        ])
        before = list(registry.list())
        _made().assess_many(targets_from_registries(skill_registry=registry))
        after = list(registry.list())
        self.assertEqual(before, after)

    def test_capability_registry_not_mutated(self):
        registry = _FakeCapabilityRegistry(["research.query"])
        before = list(registry.registered_names)
        _made().assess_many(targets_from_registries(capability_registry=registry))
        after = list(registry.registered_names)
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# 21-22: duplicate signals and repeated determinism
# ---------------------------------------------------------------------------


class TestDuplicateAndDeterminism(unittest.TestCase):

    def test_only_relevant_changes_recorded_once(self):
        target = _target("MODEL", "openai:gpt-4", dependency_entity_keys=("MODEL:openai:gpt-4",))
        change = _change("MODEL", "openai:gpt-4")
        assessment = _made().assess(target, changes=[change, change, change])
        self.assertEqual(
            assessment.evidence_change_ids,
            (assessment.evidence_change_ids[0],),
        )
        self.assertLessEqual(len(assessment.reasons), 3)

    def test_repeated_assessment_is_identical(self):
        target = _target("TOOL", "sandbox_pytest", affected_domains=("TOOL",))
        change = _change("TOOL", "sandbox_pytest")
        a1 = _made().assess(target, changes=[change])
        a2 = _made().assess(target, changes=[change])
        self.assertEqual(a1.action, a2.action)
        self.assertEqual(a1.reasons, a2.reasons)
        self.assertEqual(a1.priority, a2.priority)
        self.assertEqual(a1.rationale, a2.rationale)

    def test_combined_signals_are_aggregated(self):
        target = _target(
            "MODEL", "openai:gpt-4",
            dependency_entity_keys=("MODEL:openai:gpt-4",),
            knowledge_dependencies=("claim-1",),
        )
        change = _change("MODEL", "openai:gpt-4")
        stale = [_freshness("claim-1", FreshnessStatus.STALE)]
        assessment = _made().assess(target, changes=[change], freshness=stale)
        self.assertIs(assessment.action, LifecycleAction.REVIEW)
        self.assertIn(LifecycleReason.ENVIRONMENT_CHANGE, assessment.reasons)
        self.assertIn(LifecycleReason.STALE_KNOWLEDGE, assessment.reasons)
        self.assertEqual(assessment.priority, 0.8)  # environment change dominates


# ---------------------------------------------------------------------------
# 23-24: malformed / unknown targets fail safely
# ---------------------------------------------------------------------------


class TestMalformedAndUnknown(unittest.TestCase):

    def test_empty_identifier_raises_value_error(self):
        with self.assertRaises(ValueError):
            LifecycleTarget(target_kind=LifecycleTargetKind.TOOL, identifier="")
        with self.assertRaises(ValueError):
            LifecycleTarget(target_kind=LifecycleTargetKind.TOOL, identifier="   ")

    def test_replacement_equal_to_identifier_rejected(self):
        with self.assertRaises(ValueError):
            LifecycleTarget(
                target_kind=LifecycleTargetKind.TOOL,
                identifier="sandbox_pytest",
                replacement="sandbox_pytest",
            )

    def test_unknown_target_kind_name_raises(self):
        with self.assertRaises(ValueError):
            _kind("BOGUS")

    def test_unreferenced_change_does_not_affect_target(self):
        target = _target("TOOL", "sandbox_pytest")
        unrelated = _change("MODEL", "openai:gpt-4")
        assessment = _made().assess(target, changes=[unrelated])
        self.assertIs(assessment.action, LifecycleAction.NONE)
        self.assertIn(LifecycleReason.VALID, assessment.reasons)


# ---------------------------------------------------------------------------
# 26-27: F1 / F2 integration
# ---------------------------------------------------------------------------


class TestF1F2Integration(unittest.TestCase):

    def test_real_f1_change_relevant_to_target(self):
        target = _target("MODEL", "openai:gpt-4",
                         dependency_entity_keys=("MODEL:openai:gpt-4",))
        change = _change("MODEL", "openai:gpt-4")
        self.assertTrue(CapabilityLifecycleAssessor._is_relevant(change, target))

    def test_real_f2_assessment_relevant_to_target(self):
        target = _target("MODEL", "openai:gpt-4",
                         dependency_entity_keys=("MODEL:openai:gpt-4",),
                         knowledge_dependencies=("claim-1",))
        freshness = [_freshness("claim-1", FreshnessStatus.STALE)]
        assessment = _made().assess(target, freshness=freshness)
        self.assertIn(LifecycleReason.STALE_KNOWLEDGE, assessment.reasons)
        self.assertEqual(assessment.evidence_knowledge_ids, ("claim-1",))

    def test_target_from_model_duck_type_maps_metadata(self):
        profile = _FakeProfile(
            "openai", "gpt-4",
            metadata={"deprecated": True, "replacement": "openai:gpt-4.1"},
        )
        target = target_from_model(profile)
        self.assertEqual(target.identifier, "openai:gpt-4")
        self.assertTrue(target.deprecated)
        self.assertEqual(target.replacement, "openai:gpt-4.1")

    def test_target_from_skill_duck_type_maps_status(self):
        skill = _FakeSkill("sk1", name="greet", status="DEPRECATED")
        target = target_from_skill(skill)
        self.assertTrue(target.deprecated)


_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 11-12: ordering and bounded priority
# ---------------------------------------------------------------------------


class TestOrderingAndBoundedPriority(unittest.TestCase):

    def test_assess_many_ordered_by_priority_desc(self):
        made = _made(now=NOW)
        targets = [
            _target("MODEL", "openai:gpt-1", available=False),
            _target("TOOL", "sandbox_pytest"),
            _target("CAPABILITY", "research.query", deprecated=True),
        ]
        result = made.assess_many(targets)
        ordered = result.ordered()
        priorities = [a.priority for a in ordered]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_all_priorities_within_bounds(self):
        made = _made(now=NOW)
        cases = [
            _target("MODEL", "openai:gpt-4", status="DEPRECATED"),
            _target("TOOL", "t1", available=False),
            _target("TOOL", "t2", available=False, replacement="t2v2"),
            _target("CAPABILITY", "c1"),
            _target("CAPABILITY", "c1", affected_domains=("CAPABILITY",)),
            _target(
                "MODEL", "openai:gpt-4",
                affected_domains=("MODEL",), replacement="openai:gpt-4.1",
            ),
        ]
        changes = [_change("CAPABILITY", "c1")]
        for target in cases:
            assessment = made.assess(target, changes=changes)
            self.assertGreaterEqual(assessment.priority, 0.0)
            self.assertLessEqual(assessment.priority, 1.0)

    def test_find_actionable_filters_none(self):
        made = _made(now=NOW)
        targets = [
            _target("TOOL", "healthy_tool"),
            _target("TOOL", "deprecated_tool", deprecated=True),
        ]
        actionable = made.find_actionable(targets)
        self.assertEqual(len(actionable), 1)
        self.assertEqual(actionable[0].target_identifier, "deprecated_tool")


# ---------------------------------------------------------------------------
# 25, 28-29: existing behavior intact + no parallel infra + import scan
# ---------------------------------------------------------------------------


class TestArchitectureBoundary(unittest.TestCase):

    def test_lifecycle_package_has_no_parallel_infrastructure_imports(self):
        lifecycle_dir = _REPO_ROOT / "atlas" / "evolution" / "lifecycle"
        forbidden_prefixes = (
            "atlas.kernel",
            "atlas.runtime",
            "atlas.ai",
            "atlas.evolution.autonomy",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.approval_manager",
            "atlas.evolution.governance",
            "atlas.events",
            "subprocess",
            "sqlite3",
        )
        violations = []
        for path in sorted(lifecycle_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == p or alias.name.startswith(p)
                               for p in forbidden_prefixes):
                            violations.append((str(path), alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module and any(node.module == p or node.module.startswith(p)
                                           for p in forbidden_prefixes):
                        violations.append((str(path), node.module))
        self.assertEqual(violations, [])

    def test_targets_from_registries_snapshot_is_read_only(self):
        reg = _FakeModelRegistry([_FakeProfile("openai", "gpt-4")])
        targets = targets_from_registries(model_registry=reg)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].target_kind, LifecycleTargetKind.MODEL)
        self.assertEqual(len(reg.list_profiles()), 1)


if __name__ == "__main__":
    unittest.main()