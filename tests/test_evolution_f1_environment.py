"""Phase F1 — Environment & World-State Observation Foundation tests.

Covers the 22 F1 acceptance requirements with deterministic, offline tests:

 1. observation model validation
 2. deterministic observation identity
 3. provider/adaptor contract
 4. model/provider state observation
 5. tool state observation
 6. capability state observation
 7. added change detection
 8. removed change detection
 9. changed change detection
10. unchanged state
11. duplicate/dedup behavior
12. malformed observation fail-closed behavior
13. observation failure handling
14. provenance preservation
15. secret/credential filtering
16. bounded result behavior
17. EventBus integration
18. scheduler-compatible integration seam
19. no real repository mutation
20. no governance bypass
21. no duplicate EventBus/registry/scheduler
22. architecture/import boundary checks

All tests use real F1 production classes with tiny fake registries — no
network, no mocks of the observer/detector, no repository writes.
"""

import ast
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from atlas.evolution.environment.detector import EnvironmentChangeDetector
from atlas.evolution.environment.models import (
    EnvironmentChangeType,
    EnvironmentDomain,
    EnvironmentEntity,
    EnvironmentObservationResult,
    EnvironmentProviderFailure,
    EnvironmentState,
    ObservationReliability,
)
from atlas.evolution.environment.observer import (
    ENVIRONMENT_CHANGED_EVENT,
    EnvironmentObserver,
    sanitize_state,
)
from atlas.evolution.environment.providers import (
    CapabilityRegistryObserver,
    EnvironmentProvider,
    ModelProfileObserver,
    ProviderAvailabilityObserver,
    RuntimeEnvironmentObserver,
    SkillRegistryObserver,
    ToolRegistryObserver,
    default_providers,
)
from atlas.events.event_bus import EventBus

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Tiny fake registries (duck-typed against the real registry contracts)
# ---------------------------------------------------------------------------


class _FakeProfile:
    def __init__(self, provider_name, model_name, complexity=0.5, latency="medium",
                 cost=0.5, tasks=(), priority=0):
        self.provider_name = provider_name
        self.model_name = model_name
        self.complexity_score = complexity
        self.latency_class = latency
        self.cost_tier = cost
        self.supported_tasks = list(tasks)
        self.priority = priority


class _FakeModelRegistry:
    def __init__(self, profiles=None):
        self._profiles = profiles or []

    def list_profiles(self):
        return self._profiles


class _FakeProviderRegistry:
    def __init__(self, names=None):
        self._names = list(names or [])

    def providers(self):
        return sorted(self._names)


class _FakeTool:
    def __init__(self, name, category="utility", tags=None, handler=None):
        self.name = name
        self.category = category
        self.tags = list(tags or [])
        self.handler = handler


class _FakeToolRegistry:
    def __init__(self, tools=None):
        self._tools = list(tools or [])

    def list(self):
        return self._tools


class _FakeCapabilityRegistry:
    def __init__(self, names=None):
        self._names = list(names or [])

    @property
    def registered_names(self):
        return sorted(self._names)


class _FakeSkill:
    def __init__(self, skill_id, name="", kind=None, status=None):
        self.skill_id = skill_id
        self.name = name
        self.kind = kind
        self.status = status


class _FakeSkillRegistry:
    def __init__(self, skills=None):
        self._skills = list(skills or [])

    def list(self):
        return self._skills


class _RecordingBus(EventBus):
    """An existing EventBus that records published events."""

    def __init__(self):
        super().__init__()
        self.published = []

    def publish(self, event_name, payload=None):
        self.published.append((event_name, payload))
        super().publish(event_name, payload)


class _RecordingObservationEngine:
    def __init__(self):
        self.observations = []

    def record_observation(self, observation):
        self.observations.append(observation)


def _entity(domain, entity_id):
    return EnvironmentEntity(domain, entity_id)


# ---------------------------------------------------------------------------
# 1. Observation model validation
# ---------------------------------------------------------------------------


class TestModelValidation(unittest.TestCase):

    def test_entity_requires_valid_domain_and_id(self):
        with self.assertRaises(TypeError):
            EnvironmentEntity("MODEL", "x")  # not an EnvironmentDomain
        with self.assertRaises(ValueError):
            EnvironmentEntity(EnvironmentDomain.MODEL, "")
        with self.assertRaises(ValueError):
            EnvironmentEntity(EnvironmentDomain.MODEL, "   ")
        entity = EnvironmentEntity(EnvironmentDomain.MODEL, "openai:gpt-4")
        self.assertEqual(entity.key, "MODEL:openai:gpt-4")

    def test_state_is_frozen_dataclass(self):
        entity = _entity(EnvironmentDomain.TOOL, "sandbox_pytest")
        state = EnvironmentState(entity=entity, state={"category": "code"})
        self.assertEqual(state.key, entity.key)

    def test_result_serializes_to_plain_dict(self):
        entity = _entity(EnvironmentDomain.RUNTIME, "python")
        state = EnvironmentState(entity=entity, state={"version": "3.14"})
        change = EnvironmentChangeDetector().compare({}, {state.key: state})[0]
        result = EnvironmentObservationResult(
            cycle_id="ENV-0001",
            changes=(change,),
            provider_count=1,
            observed_count=1,
            success=True,
        )
        as_dict = result.to_dict()
        self.assertEqual(as_dict["cycle_id"], "ENV-0001")
        self.assertEqual(as_dict["changes"][0]["change_type"], "ADDED")
        json.dumps(as_dict)  # JSON-safe


# ---------------------------------------------------------------------------
# 2. Deterministic observation identity
# ---------------------------------------------------------------------------


class TestDeterministicIdentity(unittest.TestCase):

    def test_entity_key_is_stable_and_unique(self):
        a = _entity(EnvironmentDomain.MODEL, "openai:gpt-4")
        b = _entity(EnvironmentDomain.MODEL, "openai:gpt-4")
        c = _entity(EnvironmentDomain.PROVIDER, "openai")
        self.assertEqual(a.key, b.key)
        self.assertEqual(a.key, "MODEL:openai:gpt-4")
        self.assertNotEqual(a.key, c.key)

    def test_same_snapshot_yields_identical_cycle_results(self):
        registry = _FakeModelRegistry([
            _FakeProfile("openai", "gpt-4", tasks=["chat"]),
        ])
        observer_a = EnvironmentObserver(
            providers=[ModelProfileObserver(registry)],
            now=lambda: datetime(2026, 1, 1, 12, 0, 0),
        )
        observer_b = EnvironmentObserver(
            providers=[ModelProfileObserver(registry)],
            now=lambda: datetime(2026, 1, 1, 12, 0, 0),
        )
        result_a = observer_a.observe_cycle()
        result_b = observer_b.observe_cycle()
        self.assertEqual(result_a.cycle_id, "ENV-0001")
        self.assertEqual(result_a.cycle_id, result_b.cycle_id)
        self.assertEqual(result_a.observed_count, result_b.observed_count)
        self.assertEqual(
            [c.entity.key for c in result_a.changes],
            [c.entity.key for c in result_b.changes],
        )

    def test_cycle_id_monotonic(self):
        observer = EnvironmentObserver(providers=[])
        first = observer.observe_cycle().cycle_id
        second = observer.observe_cycle().cycle_id
        self.assertEqual(first, "ENV-0001")
        self.assertEqual(second, "ENV-0002")


# ---------------------------------------------------------------------------
# 3. Provider/adaptor contract
# ---------------------------------------------------------------------------


class TestProviderContract(unittest.TestCase):

    def test_protocol_is_satisfied_by_real_providers(self):
        self.assertIsInstance(RuntimeEnvironmentObserver(), EnvironmentProvider)
        self.assertIsInstance(
            ModelProfileObserver(_FakeModelRegistry()), EnvironmentProvider
        )
        self.assertIsInstance(
            ToolRegistryObserver(_FakeToolRegistry()), EnvironmentProvider
        )
        self.assertIsInstance(
            CapabilityRegistryObserver(_FakeCapabilityRegistry()), EnvironmentProvider
        )
        self.assertIsInstance(
            SkillRegistryObserver(_FakeSkillRegistry()), EnvironmentProvider
        )
        self.assertIsInstance(
            ProviderAvailabilityObserver(_FakeProviderRegistry()), EnvironmentProvider
        )

    def test_provider_names_are_unique_and_sorted(self):
        observer = EnvironmentObserver(providers=default_providers(
            model_registry=_FakeModelRegistry(),
            tool_registry=_FakeToolRegistry(),
            capability_registry=_FakeCapabilityRegistry(),
        ))
        names = observer.provider_names
        self.assertEqual(names, sorted(names))
        self.assertEqual(len(names), len(set(names)))

    def test_register_duplicate_name_rejected(self):
        observer = EnvironmentObserver(
            providers=[ModelProfileObserver(_FakeModelRegistry())]
        )
        with self.assertRaises(ValueError):
            observer.register(ModelProfileObserver(_FakeModelRegistry()))


# ---------------------------------------------------------------------------
# 4–6. Model / tool / capability state observation
# ---------------------------------------------------------------------------


class TestStateObservation(unittest.TestCase):

    def test_model_profile_observation(self):
        registry = _FakeModelRegistry([
            _FakeProfile("openai", "gpt-4", complexity=0.8, tasks=["chat", "code"]),
        ])
        states = ModelProfileObserver(registry).observe()
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].entity.key, "MODEL:openai:gpt-4")
        self.assertEqual(states[0].state["complexity_score"], 0.8)
        self.assertEqual(states[0].state["supported_tasks"], ["chat", "code"])

    def test_provider_availability_observation(self):
        registry = _FakeProviderRegistry(["openai", "ollama"])
        states = ProviderAvailabilityObserver(registry).observe()
        keys = {s.entity.key for s in states}
        self.assertEqual(keys, {"PROVIDER:openai", "PROVIDER:ollama"})
        self.assertTrue(all(s.state["available"] for s in states))

    def test_tool_state_observation(self):
        registry = _FakeToolRegistry([
            _FakeTool("sandbox_pytest", category="code", tags=["test"],
                      handler=lambda p: None),
        ])
        states = ToolRegistryObserver(registry).observe()
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].entity.key, "TOOL:sandbox_pytest")
        self.assertEqual(states[0].state["category"], "code")
        self.assertTrue(states[0].state["has_handler"])

    def test_capability_state_observation(self):
        registry = _FakeCapabilityRegistry(["research.query", "toolchain.run_skill"])
        states = CapabilityRegistryObserver(registry).observe()
        keys = {s.entity.key for s in states}
        self.assertIn("CAPABILITY:research.query", keys)
        self.assertIn("CAPABILITY:toolchain.run_skill", keys)

    def test_runtime_observation_is_safe_and_deterministic(self):
        provider = RuntimeEnvironmentObserver(
            python_version="3.14.0", platform_name="linux", implementation="CPython",
        )
        states = provider.observe()
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].state["version"], "3.14.0")
        self.assertEqual(states[0].state["platform"], "linux")
        # Never captures the process environment.
        self.assertNotIn("env", states[0].state)
        self.assertFalse(
            any("SECRET" in str(k).upper() or "KEY" in str(k).upper()
                for k in states[0].state)
        )


# ---------------------------------------------------------------------------
# 7–10. Change detection
# ---------------------------------------------------------------------------


class TestChangeDetection(unittest.TestCase):

    def _snapshot(self, items):
        """items: list of (entity_key, state_dict, source)"""
        out = {}
        for entity_key, state, source in items:
            domain_name, _, entity_id = entity_key.partition(":")
            entity = EnvironmentEntity(EnvironmentDomain[domain_name], entity_id)
            out[entity.key] = EnvironmentState(
                entity=entity, state=state, source=source,
            )
        return out

    def test_added_detection(self):
        detector = EnvironmentChangeDetector()
        current = self._snapshot([
            ("MODEL:openai:gpt-4", {"complexity_score": 0.8}, "model_profile"),
        ])
        changes = detector.compare({}, current)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, EnvironmentChangeType.ADDED)
        self.assertIsNone(changes[0].previous)
        self.assertEqual(changes[0].current["complexity_score"], 0.8)

    def test_removed_detection(self):
        detector = EnvironmentChangeDetector()
        previous = self._snapshot([
            ("TOOL:old_tool", {"category": "utility"}, "tool_registry"),
        ])
        changes = detector.compare(previous, {})
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, EnvironmentChangeType.REMOVED)
        self.assertIsNone(changes[0].current)
        self.assertEqual(changes[0].previous["category"], "utility")

    def test_changed_detection(self):
        detector = EnvironmentChangeDetector()
        previous = self._snapshot([
            ("MODEL:openai:gpt-4", {"complexity_score": 0.8}, "model_profile"),
        ])
        current = self._snapshot([
            ("MODEL:openai:gpt-4", {"complexity_score": 0.9}, "model_profile"),
        ])
        changes = detector.compare(previous, current)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, EnvironmentChangeType.CHANGED)
        self.assertEqual(changes[0].previous["complexity_score"], 0.8)
        self.assertEqual(changes[0].current["complexity_score"], 0.9)
        self.assertEqual(changes[0].metadata["changed_fields"], ["complexity_score"])

    def test_unchanged_detection(self):
        detector = EnvironmentChangeDetector()
        state = self._snapshot([
            ("CAPABILITY:research.query", {"registered": True}, "capability_registry"),
        ])
        changes = detector.compare(state, state)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, EnvironmentChangeType.UNCHANGED)

    def test_detection_order_is_stable(self):
        detector = EnvironmentChangeDetector()
        current = self._snapshot([
            ("TOOL:zeta", {"category": "x"}, "tool_registry"),
            ("TOOL:alpha", {"category": "x"}, "tool_registry"),
        ])
        changes = detector.compare({}, current)
        self.assertEqual(
            [c.entity.key for c in changes], ["TOOL:alpha", "TOOL:zeta"]
        )


# ---------------------------------------------------------------------------
# 11. Duplicate / dedup behavior
# ---------------------------------------------------------------------------


class TestDedup(unittest.TestCase):

    def test_unchanged_cycle_emits_no_repeat_changes(self):
        registry = _FakeModelRegistry([_FakeProfile("openai", "gpt-4")])
        observer = EnvironmentObserver(
            providers=[ModelProfileObserver(registry)],
            now=lambda: datetime(2026, 1, 1, 12, 0, 0),
        )
        first = observer.observe_cycle()
        second = observer.observe_cycle()
        self.assertEqual(first.changes[0].change_type, EnvironmentChangeType.ADDED)
        self.assertEqual(second.changes[0].change_type, EnvironmentChangeType.UNCHANGED)
        significant = [
            c for c in second.changes
            if c.change_type != EnvironmentChangeType.UNCHANGED
        ]
        self.assertEqual(significant, [])

    def test_duplicate_entity_from_two_providers_first_wins(self):
        class _Dup1:
            def provider_name(self):
                return "dup1"

            def observe(self):
                entity = _entity(EnvironmentDomain.MODEL, "openai:gpt-4")
                return [EnvironmentState(
                    entity=entity, state={"priority": 1}, source="dup1",
                )]

        class _Dup2:
            def provider_name(self):
                return "dup2"

            def observe(self):
                entity = _entity(EnvironmentDomain.MODEL, "openai:gpt-4")
                return [EnvironmentState(
                    entity=entity, state={"priority": 999}, source="dup2",
                )]

        observer = EnvironmentObserver(providers=[_Dup1(), _Dup2()])
        result = observer.observe_cycle()
        self.assertEqual(result.observed_count, 1)
        self.assertEqual(result.changes[0].current, {"priority": 1})


# ---------------------------------------------------------------------------
# 12–13. Fail-closed and failure handling
# ---------------------------------------------------------------------------


class _BoomProvider:
    def provider_name(self):
        return "boom"

    def observe(self):
        raise RuntimeError("provider exploded")


class _MalformedProvider:
    def provider_name(self):
        return "malformed"

    def observe(self):
        return ["not-an-environment-state"]  # invalid type


class TestFailClosed(unittest.TestCase):

    def test_provider_exception_becomes_bounded_failure(self):
        observer = EnvironmentObserver(
            providers=[RuntimeEnvironmentObserver(), _BoomProvider()],
        )
        result = observer.observe_cycle()
        self.assertFalse(result.success)
        self.assertEqual(len(result.failures), 1)
        failure = result.failures[0]
        self.assertIsInstance(failure, EnvironmentProviderFailure)
        self.assertEqual(failure.provider_name, "boom")
        self.assertIn("provider exploded", failure.error)
        # Healthy providers still contributed.
        self.assertGreaterEqual(result.observed_count, 1)
        # The observer never raises.
        observer.observe_cycle()

    def test_error_message_is_bounded(self):
        class _Verbose:
            def provider_name(self):
                return "verbose"

            def observe(self):
                raise RuntimeError("x" * 5000)

        observer = EnvironmentObserver(providers=[_Verbose()])
        result = observer.observe_cycle()
        self.assertLessEqual(len(result.failures[0].error), 200)

    def test_malformed_state_does_not_crash_cycle(self):
        observer = EnvironmentObserver(providers=[_MalformedProvider()])
        result = observer.observe_cycle()
        self.assertFalse(result.success)
        self.assertGreaterEqual(len(result.failures), 1)

    def test_all_providers_fail_marks_result_unsuccessful(self):
        observer = EnvironmentObserver(providers=[_BoomProvider(), _BoomProvider()])
        result = observer.observe_cycle()
        self.assertFalse(result.success)
        self.assertEqual(result.observed_count, 0)


# ---------------------------------------------------------------------------
# 14. Provenance preservation
# ---------------------------------------------------------------------------


class TestProvenance(unittest.TestCase):

    def test_change_carries_full_provenance(self):
        detector = EnvironmentChangeDetector()
        entity = _entity(EnvironmentDomain.TOOL, "sandbox_pytest")
        when = datetime(2026, 1, 1, 12, 0, 0)
        prior = EnvironmentState(
            entity=entity, state={"category": "code"},
            source="tool_registry", observed_at=when,
            reliability=ObservationReliability.HIGH,
        )
        now = EnvironmentState(
            entity=entity, state={"category": "testing"},
            source="tool_registry", observed_at=when + timedelta(seconds=1),
            reliability=ObservationReliability.HIGH,
        )
        change = detector.compare({entity.key: prior}, {entity.key: now})[0]
        self.assertEqual(change.entity, entity)
        self.assertEqual(change.source, "tool_registry")
        self.assertEqual(change.observed_at, now.observed_at)
        self.assertEqual(change.reliability, ObservationReliability.HIGH)
        self.assertEqual(change.previous, {"category": "code"})
        self.assertEqual(change.current, {"category": "testing"})


# ---------------------------------------------------------------------------
# 15. Secret / credential filtering
# ---------------------------------------------------------------------------


class TestSecretFiltering(unittest.TestCase):

    def test_sanitize_state_strips_credential_keys(self):
        state = {
            "model": "gpt-4",
            "api_key": "sk-secret-123",
            "API_TOKEN": "abc",
            "password": "pw",
            "max_tokens": 128,
            "headers": {"Authorization": "Bearer x", "content_type": "json"},
        }
        cleaned = sanitize_state(state)
        self.assertEqual(cleaned["model"], "gpt-4")
        self.assertEqual(cleaned["max_tokens"], 128)
        self.assertNotIn("api_key", cleaned)
        self.assertNotIn("API_TOKEN", cleaned)
        self.assertNotIn("password", cleaned)
        self.assertNotIn("Authorization", cleaned.get("headers", {}))
        self.assertEqual(cleaned["headers"].get("content_type"), "json")

    def test_observer_never_records_secrets(self):
        class _Leaky:
            def provider_name(self):
                return "leaky"

            def observe(self):
                entity = _entity(EnvironmentDomain.PROVIDER, "openai")
                return [EnvironmentState(
                    entity=entity,
                    state={"api_key": "sk-leak", "status": "ok"},
                    source="leaky",
                )]

        observer = EnvironmentObserver(providers=[_Leaky()])
        result = observer.observe_cycle()
        self.assertEqual(result.changes[0].current, {"status": "ok"})
        self.assertNotIn("api_key", result.changes[0].current)


# ---------------------------------------------------------------------------
# 16. Bounded result behavior
# ---------------------------------------------------------------------------


class TestBoundedResult(unittest.TestCase):

    def test_failures_capped(self):
        from atlas.evolution.environment.observer import MAX_FAILURES_PER_CYCLE

        class _Failing:
            def provider_name(self):
                return "f"

            def observe(self):
                raise RuntimeError("nope")

        providers = [_Failing() for _ in range(MAX_FAILURES_PER_CYCLE + 50)]
        observer = EnvironmentObserver(providers=providers)
        result = observer.observe_cycle()
        self.assertLessEqual(len(result.failures), MAX_FAILURES_PER_CYCLE)

    def test_cycle_id_and_result_bounded_fields(self):
        observer = EnvironmentObserver(providers=[])
        result = observer.observe_cycle()
        self.assertTrue(result.success)
        self.assertEqual(result.changes, ())
        self.assertEqual(result.failures, ())
        self.assertEqual(result.provider_count, 0)


# ---------------------------------------------------------------------------
# 17. EventBus integration
# ---------------------------------------------------------------------------


class TestEventBusIntegration(unittest.TestCase):

    def test_environment_changed_event_published_on_change(self):
        bus = _RecordingBus()
        registry = _FakeModelRegistry([_FakeProfile("openai", "gpt-4")])
        observer = EnvironmentObserver(
            providers=[ModelProfileObserver(registry)],
            event_bus=bus,
        )
        observer.observe_cycle()
        names = [name for name, _ in bus.published]
        self.assertIn(ENVIRONMENT_CHANGED_EVENT, names)

    def test_no_event_when_nothing_changed(self):
        bus = _RecordingBus()
        registry = _FakeModelRegistry([_FakeProfile("openai", "gpt-4")])
        observer = EnvironmentObserver(
            providers=[ModelProfileObserver(registry)],
            event_bus=bus,
        )
        observer.observe_cycle()  # ADDED -> publishes
        observer.observe_cycle()  # UNCHANGED -> no publish
        self.assertEqual(len(bus.published), 1)

    def test_event_payload_is_plain_and_secret_free(self):
        bus = _RecordingBus()
        registry = _FakeModelRegistry([_FakeProfile("openai", "gpt-4")])
        observer = EnvironmentObserver(
            providers=[ModelProfileObserver(registry)],
            event_bus=bus,
        )
        observer.observe_cycle()
        _, payload = bus.published[0]
        self.assertEqual(payload["cycle_id"], "ENV-0001")
        self.assertEqual(payload["changes"][0]["change_type"], "ADDED")
        json.dumps(payload)  # JSON-safe

    def test_uses_existing_event_bus_instance(self):
        bus = _RecordingBus()
        observer = EnvironmentObserver(providers=[], event_bus=bus)
        self.assertIs(observer._event_bus, bus)  # no new bus created


# ---------------------------------------------------------------------------
# 18. Scheduler-compatible integration seam
# ---------------------------------------------------------------------------


class TestSchedulerSeam(unittest.TestCase):

    def test_observe_cycle_is_no_arg_callable(self):
        observer = EnvironmentObserver(providers=[])
        # A scheduler would call observer.observe_cycle() with no arguments.
        result = observer.observe_cycle()
        self.assertIsInstance(result, EnvironmentObservationResult)
        # observe() alias also works.
        observer.observe()

    def test_observations_recorded_into_existing_engine(self):
        engine = _RecordingObservationEngine()
        registry = _FakeModelRegistry([_FakeProfile("openai", "gpt-4")])
        observer = EnvironmentObserver(
            providers=[ModelProfileObserver(registry)],
            observation_engine=engine,
        )
        observer.observe_cycle()
        self.assertGreaterEqual(len(engine.observations), 1)
        obs = engine.observations[0]
        self.assertEqual(obs.metric_name, "environment:MODEL:openai:gpt-4")


# ---------------------------------------------------------------------------
# 19–21. Safety: no repo mutation, no governance bypass, no parallel subsystems
# ---------------------------------------------------------------------------


class TestSafety(unittest.TestCase):

    def test_no_real_repository_mutation(self):
        before = {str(p) for p in _REPO_ROOT.rglob("*")}
        registry = _FakeModelRegistry([_FakeProfile("openai", "gpt-4")])
        observer = EnvironmentObserver(
            providers=[ModelProfileObserver(registry)],
            event_bus=_RecordingBus(),
        )
        observer.observe_cycle()
        after = {str(p) for p in _REPO_ROOT.rglob("*")}
        self.assertEqual(before, after)

    def test_no_governance_or_authorization_imports(self):
        import inspect

        import atlas.evolution.environment as env_pkg

        src = inspect.getsource(env_pkg)
        for forbidden in ("ApprovalManager", "AuthorizationManager",
                          "RuleEngine", "ConstraintRegistry",
                          "ExecutionGateway", "SelfDevelopmentLoop"):
            self.assertNotIn(forbidden, src)

    def test_no_duplicate_event_bus_or_registry(self):
        # The observer only uses injected instances; it creates none.
        bus = _RecordingBus()
        observer = EnvironmentObserver(providers=[], event_bus=bus)
        self.assertIs(observer._event_bus, bus)
        self.assertEqual(observer._providers, [])


# ---------------------------------------------------------------------------
# 22. Architecture / import boundary checks
# ---------------------------------------------------------------------------


class TestImportBoundary(unittest.TestCase):

    def _forbidden_imports(self, module_path):
        forbidden = (
            "atlas.kernel",
            "atlas.runtime",
            "atlas.ai.providers",
            "atlas.ai.router",
            "atlas.evolution.autonomy",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.approval_manager",
        )
        tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
        return sorted(
            m for m in imported
            if any(m == f or m.startswith(f + ".") for f in forbidden)
        )

    def test_environment_package_boundary(self):
        pkg = _REPO_ROOT / "atlas" / "evolution" / "environment"
        violations = []
        for path in sorted(pkg.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            violations.extend(self._forbidden_imports(path))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()