"""
Atlas Evolution Autonomy — Validator — Phase 16.2

Per-scope payload schema validation and preconditions for ``EvolutionRequest``.

Gate 2 of the governance pipeline (see ``PHASE_16_ARCHITECTURE.md`` §7).
The validator is pure logic: it inspects the request's ``target_scope`` and
``change_payload`` and returns an immutable ``ValidationReport``. It never
mutates the request, never touches storage, and never calls the gateway.

Validation rules are deterministic and versioned. New scopes or payload
kinds can be added by registering a ``ValidationRule`` with the
``ValidatorRegistry``; the default rules cover the four Phase 16 state
scopes (CONFIG, MEMORY, KNOWLEDGE, CAPABILITY).

Pure logic. No infrastructure. No AI. No gateway access.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    ValidationReport,
)
from atlas.evolution.governance.models import ScopeType


# ---------------------------------------------------------------------------
# Rule protocol and registry
# ---------------------------------------------------------------------------


class ValidationRule(Protocol):
    """A single, deterministic validation rule for a scope/payload pair."""

    @property
    def scope(self) -> ScopeType:
        """The ScopeType this rule applies to."""
        ...

    @property
    def schema_version(self) -> str:
        """Opaque version of the rule (for audit)."""
        ...

    def validate(self, request: EvolutionRequest) -> ValidationReport:
        """Return a ValidationReport for the request."""
        ...


@dataclass(frozen=True, slots=True)
class _SchemaRule:
    """Concrete rule wrapper binding a scope to a pure callable."""

    scope: ScopeType
    schema_version: str
    _validate: Callable[[EvolutionRequest], ValidationReport]

    def validate(self, request: EvolutionRequest) -> ValidationReport:
        return self._validate(request)


class ValidatorRegistry:
    """Holds the set of scope-specific validation rules.

    The registry is pure logic. Rules are added; rules are looked up by
    scope. A request whose scope has no registered rule validates as
    invalid (fail-closed), because unrecognised scopes must not pass Gate 2.
    """

    def __init__(self) -> None:
        self._rules: dict[ScopeType, ValidationRule] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the deterministic Phase 16 schema rules."""
        self.register(_SchemaRule(ScopeType.CONFIG, "1.0", _validate_config))
        self.register(_SchemaRule(ScopeType.MEMORY, "1.0", _validate_memory))
        self.register(_SchemaRule(ScopeType.KNOWLEDGE, "1.0", _validate_knowledge))
        self.register(_SchemaRule(ScopeType.CAPABILITY, "1.0", _validate_capability))

    def register(self, rule: ValidationRule) -> None:
        """Register (or replace) a validation rule for a scope."""
        self._rules[rule.scope] = rule

    def get_rule(self, scope: ScopeType) -> ValidationRule | None:
        """Return the rule for a scope, or None if no rule is registered."""
        return self._rules.get(scope)

    def registered_scopes(self) -> set[ScopeType]:
        """Return the set of scopes with registered rules."""
        return set(self._rules.keys())


# ---------------------------------------------------------------------------
# Per-scope schema validators
# ---------------------------------------------------------------------------


_VALIDATOR_VERSION = "phase16.2-1.0"


def _validation_report(
    valid: bool,
    violations: list[str],
    warnings: list[str],
    schema_version: str,
) -> ValidationReport:
    return ValidationReport(
        valid=valid,
        violations=violations,
        warnings=warnings,
        schema_version=schema_version,
        validator_version=_VALIDATOR_VERSION,
    )


def _validate_config(request: EvolutionRequest) -> ValidationReport:
    """Validate a CONFIG-scoped request.

    Required payload fields:
      - key: non-empty configuration key string
      - value: present (may be None to clear a key)

    Optional fields:
      - schema: optional value-type hint (string)

    Prohibited:
      - empty key
      - key containing 'autonomy.policy' or 'constraint_registry'
        (constitutional protection of the envelope)
    """
    payload = request.change_payload
    violations: list[str] = []
    warnings: list[str] = []

    key = payload.get("key")
    if not isinstance(key, str) or not key.strip():
        violations.append("CONFIG payload requires a non-empty string 'key'")
    else:
        key = key.strip()
        if "autonomy.policy" in key.lower():
            violations.append("Configuration key 'autonomy.policy' is protected")
        if "constraint_registry" in key.lower():
            violations.append("Configuration key 'constraint_registry' is protected")
        if "execution_gateway" in key.lower():
            violations.append("Configuration key 'execution_gateway' is protected")

    if "value" not in payload:
        violations.append("CONFIG payload requires a 'value' field")

    if "schema" in payload and not isinstance(payload["schema"], str):
        violations.append("CONFIG optional 'schema' must be a string")

    if isinstance(key, str) and key.startswith("identity."):
        warnings.append("Key under 'identity.' namespace should be reviewed manually")

    return _validation_report(
        valid=len(violations) == 0,
        violations=violations,
        warnings=warnings,
        schema_version="config-1.0",
    )


def _validate_memory(request: EvolutionRequest) -> ValidationReport:
    """Validate a MEMORY-scoped request.

    Required payload fields:
      - operation: one of 'add', 'update', 'remove'
      - memory_id: non-empty identifier

    Optional fields:
      - content: required for 'add'/'update'
      - tags: optional list of strings
    """
    payload = request.change_payload
    violations: list[str] = []
    warnings: list[str] = []

    operation = payload.get("operation")
    if operation not in {"add", "update", "remove"}:
        violations.append(
            "MEMORY payload 'operation' must be one of: add, update, remove"
        )

    memory_id = payload.get("memory_id")
    if not isinstance(memory_id, str) or not memory_id.strip():
        violations.append("MEMORY payload requires a non-empty string 'memory_id'")

    if operation in {"add", "update"} and "content" not in payload:
        violations.append(
            f"MEMORY operation '{operation}' requires a 'content' field"
        )

    tags = payload.get("tags")
    if tags is not None and not (
        isinstance(tags, list) and all(isinstance(t, str) for t in tags)
    ):
        violations.append("MEMORY optional 'tags' must be a list of strings")

    if operation == "remove":
        warnings.append("Remove operations are irreversible without rollback")

    return _validation_report(
        valid=len(violations) == 0,
        violations=violations,
        warnings=warnings,
        schema_version="memory-1.0",
    )


def _validate_knowledge(request: EvolutionRequest) -> ValidationReport:
    """Validate a KNOWLEDGE-scoped request.

    Required payload fields:
      - operation: one of 'add', 'update', 'remove'
      - entry_id: non-empty identifier
      - domain: non-empty domain/category string

    Optional fields:
      - content: required for 'add'/'update'
      - confidence: optional float in [0.0, 1.0]
    """
    payload = request.change_payload
    violations: list[str] = []
    warnings: list[str] = []

    operation = payload.get("operation")
    if operation not in {"add", "update", "remove"}:
        violations.append(
            "KNOWLEDGE payload 'operation' must be one of: add, update, remove"
        )

    entry_id = payload.get("entry_id")
    if not isinstance(entry_id, str) or not entry_id.strip():
        violations.append(
            "KNOWLEDGE payload requires a non-empty string 'entry_id'"
        )

    domain = payload.get("domain")
    if not isinstance(domain, str) or not domain.strip():
        violations.append("KNOWLEDGE payload requires a non-empty string 'domain'")

    if operation in {"add", "update"} and "content" not in payload:
        violations.append(
            f"KNOWLEDGE operation '{operation}' requires a 'content' field"
        )

    confidence = payload.get("confidence")
    if confidence is not None and (
        not isinstance(confidence, (int, float))
        or confidence < 0.0
        or confidence > 1.0
    ):
        violations.append("KNOWLEDGE optional 'confidence' must be a float in [0.0, 1.0]")

    if operation == "remove":
        warnings.append("Remove operations are irreversible without rollback")

    return _validation_report(
        valid=len(violations) == 0,
        violations=violations,
        warnings=warnings,
        schema_version="knowledge-1.0",
    )


def _validate_capability(request: EvolutionRequest) -> ValidationReport:
    """Validate a CAPABILITY-scoped request.

    Required payload fields:
      - upgrade_kind: one of 'REGISTER', 'ENHANCE', 'DEPRECATE'
      - capability_name: non-empty identifier

    Optional fields:
      - description: optional human-readable description
      - metadata: optional dict

    The capability applier (Phase 16.5) will dispatch by upgrade_kind.
    """
    payload = request.change_payload
    violations: list[str] = []
    warnings: list[str] = []

    upgrade_kind = payload.get("upgrade_kind")
    if upgrade_kind not in {"REGISTER", "ENHANCE", "DEPRECATE"}:
        violations.append(
            "CAPABILITY payload 'upgrade_kind' must be one of: "
            "REGISTER, ENHANCE, DEPRECATE"
        )

    capability_name = payload.get("capability_name")
    if not isinstance(capability_name, str) or not capability_name.strip():
        violations.append(
            "CAPABILITY payload requires a non-empty string 'capability_name'"
        )

    if "metadata" in payload and not isinstance(payload["metadata"], dict):
        violations.append("CAPABILITY optional 'metadata' must be a dict")

    if upgrade_kind == "DEPRECATE":
        warnings.append("Deprecation should include a migration plan in metadata")

    return _validation_report(
        valid=len(violations) == 0,
        violations=violations,
        warnings=warnings,
        schema_version="capability-1.0",
    )


# ---------------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvolutionValidator:
    """Deterministic gate 2 validator for ``EvolutionRequest`` payloads.

    Accepts an optional ``ValidatorRegistry`` via dependency injection so
    callers can supply custom rule sets in tests without mutating global
    state.

    The validator is fail-closed:
      - UNKNOWN, IDENTITY, or CODE scope => invalid
      - scope with no registered rule => invalid
      - payload violating the registered schema => invalid
    """

    registry: ValidatorRegistry = field(default_factory=ValidatorRegistry)

    def validate(self, request: EvolutionRequest) -> ValidationReport:
        """Validate ``request`` against the per-scope schema.

        Args:
            request: The EvolutionRequest to validate.

        Returns:
            A ValidationReport. ``valid`` is True only when the request
            targets a recognised state scope and the payload satisfies the
            schema.
        """
        scope = request.target_scope

        if scope in {ScopeType.UNKNOWN, ScopeType.IDENTITY, ScopeType.CODE}:
            return _validation_report(
                valid=False,
                violations=[
                    f"Scope {scope.name} is not a valid Phase 16 state scope"
                ],
                warnings=[],
                schema_version="validator-1.0",
            )

        rule = self.registry.get_rule(scope)
        if rule is None:
            return _validation_report(
                valid=False,
                violations=[f"No validation rule registered for scope {scope.name}"],
                warnings=[],
                schema_version="validator-1.0",
            )

        report = rule.validate(request)
        # Ensure the validator version is recorded even if the rule omitted it.
        return ValidationReport(
            valid=report.valid,
            violations=report.violations,
            warnings=report.warnings,
            schema_version=report.schema_version,
            validator_version=_VALIDATOR_VERSION,
        )
