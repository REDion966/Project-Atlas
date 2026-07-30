"""
Atlas Evolution Governance — Constraint Registry

Stores and manages explicit governance rules that constrain
evolution proposals. Rules are auditable, deterministic, and
apply to specific scope types.

Phase 13.1 — Evolution Governance Foundation.
"""

from atlas.evolution.governance.models import GovernanceRule, ScopeType
from atlas.evolution.models import ExecutionLevel


class ConstraintRegistry:
    """
    Stores auditable governance rules and provides scope-based queries.

    Default rules are loaded on construction. Additional rules can be
    registered at runtime. Rules are immutable once registered.

    Pure logic. No infrastructure. No AI. No storage.
    """

    def __init__(self) -> None:
        self._rules: dict[str, GovernanceRule] = {}
        self._load_default_rules()

    # ------------------------------------------------------------------
    # Default rules (loaded on construction)
    # ------------------------------------------------------------------

    def _load_default_rules(self) -> None:
        """Load the initial set of governance rules.

        These rules encode Atlas's constitutional constraints:
          - Identity is protected until AUTONOMOUS level.
          - Code changes require CODE_ARTIFACT level.
          - Config changes require SELF_CONFIG level.
          - Memory/knowledge changes require INFORMATION level.
        """
        self.register(
            GovernanceRule(
                rule_id="GOV-001",
                description=(
                    "Identity principles, beliefs, and preferences are "
                    "immutable below AUTONOMOUS execution level."
                ),
                scope=ScopeType.IDENTITY,
                min_execution_level=ExecutionLevel.AUTONOMOUS.value,
            )
        )
        self.register(
            GovernanceRule(
                rule_id="GOV-002",
                description=(
                    "Code modifications require CODE_ARTIFACT "
                    "execution level."
                ),
                scope=ScopeType.CODE,
                min_execution_level=ExecutionLevel.CODE_ARTIFACT.value,
            )
        )
        self.register(
            GovernanceRule(
                rule_id="GOV-003",
                description=(
                    "Configuration modifications require SELF_CONFIG "
                    "execution level."
                ),
                scope=ScopeType.CONFIG,
                min_execution_level=ExecutionLevel.SELF_CONFIG.value,
            )
        )
        self.register(
            GovernanceRule(
                rule_id="GOV-004",
                description=(
                    "Memory, knowledge, and world model modifications "
                    "require INFORMATION execution level."
                ),
                scope=ScopeType.MEMORY,
                min_execution_level=ExecutionLevel.INFORMATION.value,
            )
        )

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def register(self, rule: GovernanceRule) -> None:
        """Register a governance rule.

        Args:
            rule: The GovernanceRule to register.

        Raises:
            ValueError: If a rule with the same rule_id already exists.
        """
        if rule.rule_id in self._rules:
            raise ValueError(
                f"Governance rule '{rule.rule_id}' is already registered."
            )
        self._rules[rule.rule_id] = rule

    def get_rules(self) -> list[GovernanceRule]:
        """Return all registered governance rules."""
        return list(self._rules.values())

    def get_rules_for_scope(self, scope: ScopeType) -> list[GovernanceRule]:
        """Return all rules that apply to a given scope.

        Args:
            scope: The ScopeType to filter by.

        Returns:
            A list of GovernanceRule instances matching the scope.
            Returns an empty list if no rules match.
        """
        return [
            rule for rule in self._rules.values()
            if rule.scope == scope
        ]

    def get_rule(self, rule_id: str) -> GovernanceRule | None:
        """Look up a single rule by its ID.

        Args:
            rule_id: The rule identifier (e.g. "GOV-001").

        Returns:
            The GovernanceRule, or None if not found.
        """
        return self._rules.get(rule_id)

    @property
    def rule_count(self) -> int:
        """Return the number of registered rules."""
        return len(self._rules)

    def clear(self) -> None:
        """Remove all registered rules.

        Primarily useful for testing. Does not reload defaults.
        """
        self._rules.clear()
