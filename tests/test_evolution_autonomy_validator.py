"""
Atlas Evolution Autonomy — Validator Tests — Phase 16.2

Verifies Gate 2 per-scope payload schema validation:

- Each Phase 16 state scope has a deterministic schema rule.
- Valid payloads pass; invalid payloads fail with specific violations.
- UNKNOWN, IDENTITY, and CODE scopes are refused fail-closed.
- The validator is pure: it does not mutate the request or produce side
  effects.
- Custom registries can be injected for extensibility.

Pure logic. No infra. No AI.
"""

import unittest

from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    ValidationReport,
)
from atlas.evolution.autonomy.validator import (
    EvolutionValidator,
    ValidatorRegistry,
    _validate_config,
    _validate_capability,
    _validate_knowledge,
    _validate_memory,
)
from atlas.evolution.governance.models import ScopeType


class _RequestFactory:
    """Builds minimal EvolutionRequests for validator tests."""

    @staticmethod
    def request(
        scope: ScopeType,
        payload: dict | None = None,
        request_id: str = "AUTORQ-1",
    ) -> EvolutionRequest:
        return EvolutionRequest(
            request_id=request_id,
            source="cli",
            target_scope=scope,
            change_payload=payload or {},
        )


class TestValidatorRegistry(unittest.TestCase):
    """Default registry covers the four state scopes and no others."""

    def test_default_scopes(self):
        registry = ValidatorRegistry()
        self.assertEqual(
            registry.registered_scopes(),
            {ScopeType.CONFIG, ScopeType.MEMORY, ScopeType.KNOWLEDGE, ScopeType.CAPABILITY},
        )

    def test_get_rule(self):
        registry = ValidatorRegistry()
        self.assertIsNotNone(registry.get_rule(ScopeType.CONFIG))
        self.assertIsNone(registry.get_rule(ScopeType.IDENTITY))

    def test_custom_registry(self):
        registry = ValidatorRegistry()
        # Replace MEMORY rule with a custom one.
        registry.register(_SchemaRuleStub(ScopeType.MEMORY, "stub"))
        self.assertEqual(registry.get_rule(ScopeType.MEMORY).schema_version, "stub")


class _SchemaRuleStub:
    def __init__(self, scope: ScopeType, schema_version: str):
        self.scope = scope
        self.schema_version = schema_version

    def validate(self, request: EvolutionRequest) -> ValidationReport:
        return ValidationReport(
            valid=True,
            schema_version=self.schema_version,
            validator_version="stub",
        )


class TestConfigValidation(unittest.TestCase):
    """CONFIG schema: key + value required; protected keys refused."""

    def test_valid_config(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "feature_flag_x", "value": True}
        )
        report = _validate_config(req)
        self.assertTrue(report.valid)
        self.assertEqual(report.schema_version, "config-1.0")

    def test_missing_key(self):
        req = _RequestFactory.request(ScopeType.CONFIG, {"value": True})
        report = _validate_config(req)
        self.assertFalse(report.valid)
        self.assertIn("non-empty string 'key'", report.violations[0])

    def test_empty_key(self):
        req = _RequestFactory.request(ScopeType.CONFIG, {"key": "   ", "value": True})
        report = _validate_config(req)
        self.assertFalse(report.valid)

    def test_missing_value(self):
        req = _RequestFactory.request(ScopeType.CONFIG, {"key": "flag"})
        report = _validate_config(req)
        self.assertFalse(report.valid)
        self.assertIn("'value' field", report.violations[0])

    def test_protected_autonomy_policy_key(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "evolution.autonomy.policy.enabled", "value": True}
        )
        report = _validate_config(req)
        self.assertFalse(report.valid)
        self.assertTrue(any("autonomy.policy" in v for v in report.violations))

    def test_protected_constraint_registry_key(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "constraint_registry_path", "value": "x"}
        )
        report = _validate_config(req)
        self.assertFalse(report.valid)
        self.assertTrue(any("constraint_registry" in v for v in report.violations))

    def test_protected_execution_gateway_key(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "execution_gateway_level", "value": 3}
        )
        report = _validate_config(req)
        self.assertFalse(report.valid)

    def test_identity_namespace_warning(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "identity.core_value", "value": "x"}
        )
        report = _validate_config(req)
        self.assertTrue(report.valid)
        self.assertTrue(any("identity." in w for w in report.warnings))


class TestMemoryValidation(unittest.TestCase):
    """MEMORY schema: operation + memory_id required."""

    def test_valid_add(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY,
            {"operation": "add", "memory_id": "M-1", "content": "hello"},
        )
        report = _validate_memory(req)
        self.assertTrue(report.valid)

    def test_valid_remove(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "remove", "memory_id": "M-1"}
        )
        report = _validate_memory(req)
        self.assertTrue(report.valid)
        self.assertTrue(any("irreversible" in w for w in report.warnings))

    def test_invalid_operation(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "delete", "memory_id": "M-1"}
        )
        report = _validate_memory(req)
        self.assertFalse(report.valid)

    def test_missing_memory_id(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "add", "content": "hello"}
        )
        report = _validate_memory(req)
        self.assertFalse(report.valid)

    def test_add_requires_content(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "add", "memory_id": "M-1"}
        )
        report = _validate_memory(req)
        self.assertFalse(report.valid)

    def test_invalid_tags(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY,
            {"operation": "add", "memory_id": "M-1", "content": "x", "tags": "notalist"},
        )
        report = _validate_memory(req)
        self.assertFalse(report.valid)


class TestKnowledgeValidation(unittest.TestCase):
    """KNOWLEDGE schema: operation + entry_id + domain required."""

    def test_valid_add(self):
        req = _RequestFactory.request(
            ScopeType.KNOWLEDGE,
            {
                "operation": "add",
                "entry_id": "K-1",
                "domain": "reasoning",
                "content": "fact",
            },
        )
        report = _validate_knowledge(req)
        self.assertTrue(report.valid)

    def test_missing_domain(self):
        req = _RequestFactory.request(
            ScopeType.KNOWLEDGE,
            {"operation": "add", "entry_id": "K-1", "content": "fact"},
        )
        report = _validate_knowledge(req)
        self.assertFalse(report.valid)

    def test_invalid_confidence(self):
        req = _RequestFactory.request(
            ScopeType.KNOWLEDGE,
            {
                "operation": "add",
                "entry_id": "K-1",
                "domain": "reasoning",
                "content": "fact",
                "confidence": 1.5,
            },
        )
        report = _validate_knowledge(req)
        self.assertFalse(report.valid)


class TestCapabilityValidation(unittest.TestCase):
    """CAPABILITY schema: upgrade_kind + capability_name required."""

    def test_valid_register(self):
        req = _RequestFactory.request(
            ScopeType.CAPABILITY,
            {"upgrade_kind": "REGISTER", "capability_name": "ToolRegistry"},
        )
        report = _validate_capability(req)
        self.assertTrue(report.valid)

    def test_invalid_upgrade_kind(self):
        req = _RequestFactory.request(
            ScopeType.CAPABILITY,
            {"upgrade_kind": "DELETE", "capability_name": "ToolRegistry"},
        )
        report = _validate_capability(req)
        self.assertFalse(report.valid)

    def test_missing_capability_name(self):
        req = _RequestFactory.request(
            ScopeType.CAPABILITY, {"upgrade_kind": "ENHANCE"}
        )
        report = _validate_capability(req)
        self.assertFalse(report.valid)

    def test_deprecate_warning(self):
        req = _RequestFactory.request(
            ScopeType.CAPABILITY,
            {"upgrade_kind": "DEPRECATE", "capability_name": "OldTool"},
        )
        report = _validate_capability(req)
        self.assertTrue(report.valid)
        self.assertTrue(any("migration" in w for w in report.warnings))


class TestEvolutionValidatorFailClosed(unittest.TestCase):
    """Top-level validator refuses protected scopes and unregistered scopes."""

    def test_unknown_scope_invalid(self):
        validator = EvolutionValidator()
        req = _RequestFactory.request(ScopeType.UNKNOWN, {"key": "x", "value": 1})
        report = validator.validate(req)
        self.assertFalse(report.valid)
        self.assertIn("UNKNOWN", report.violations[0])

    def test_identity_scope_invalid(self):
        validator = EvolutionValidator()
        req = _RequestFactory.request(ScopeType.IDENTITY, {"key": "x"})
        report = validator.validate(req)
        self.assertFalse(report.valid)

    def test_code_scope_invalid(self):
        validator = EvolutionValidator()
        req = _RequestFactory.request(ScopeType.CODE, {"patch": "x"})
        report = validator.validate(req)
        self.assertFalse(report.valid)

    def test_valid_config_passes(self):
        validator = EvolutionValidator()
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "setting", "value": 42}
        )
        report = validator.validate(req)
        self.assertTrue(report.valid)
        self.assertEqual(report.validator_version, "phase16.2-1.0")

    def test_validator_does_not_mutate_request(self):
        validator = EvolutionValidator()
        payload = {"key": "setting", "value": 42}
        req = _RequestFactory.request(ScopeType.CONFIG, payload)
        validator.validate(req)
        # Frozen request cannot be mutated anyway, but assert payload intact.
        self.assertEqual(req.change_payload, payload)


class TestValidatorVersion(unittest.TestCase):
    """ValidationReport carries schema and validator versions."""

    def test_schema_version_in_report(self):
        req = _RequestFactory.request(
            ScopeType.CAPABILITY,
            {"upgrade_kind": "REGISTER", "capability_name": "X"},
        )
        report = EvolutionValidator().validate(req)
        self.assertEqual(report.schema_version, "capability-1.0")
        self.assertEqual(report.validator_version, "phase16.2-1.0")


if __name__ == "__main__":
    unittest.main()
