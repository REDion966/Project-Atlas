"""
Atlas Behavior Model

Represents recurring human/system behaviors.
Rule-based. Pluggable. No AI.

Phase 7.4 — World Model Foundation.
"""

from datetime import datetime
from typing import Any

from atlas.world_model.models import (
    BehavioralRule,
    BehaviorTrigger,
    Entity,
    EntityCategory,
)


class BehaviorModel:
    """
    Rule-based behavior model for recurring human/system behaviors.

    Pure logic. No AI providers. Pluggable — can be subclassed for
    domain-specific behavior patterns.

    Default implementation includes basic behavioral rules for
    common system and user interaction patterns.
    """

    def __init__(self) -> None:
        self._rules: list[BehavioralRule] = []
        self._rule_counter = 0
        self._seed_builtin_rules()

    def _next_rule_id(self) -> str:
        self._rule_counter += 1
        return f"RULE-{self._rule_counter:06d}"

    def _seed_builtin_rules(self) -> None:
        """Seed basic built-in behavioral rules."""
        builtins = [
            BehavioralRule(
                rule_id=self._next_rule_id(),
                description="User prefers explicit confirmation before major changes",
                trigger=BehaviorTrigger.GOAL_ACTIVATED,
                trigger_condition="goal involves system modification",
                expected_behavior="User expects to be asked before changes are applied",
                confidence=0.8,
                domain="user_interaction",
            ),
            BehavioralRule(
                rule_id=self._next_rule_id(),
                description="System degrades when memory usage exceeds threshold",
                trigger=BehaviorTrigger.THRESHOLD_CROSSED,
                trigger_condition="memory_usage > 90%",
                expected_behavior="Response latency increases; failures may occur",
                confidence=0.7,
                domain="system_behavior",
            ),
            BehavioralRule(
                rule_id=self._next_rule_id(),
                description="Repeated failures reduce confidence in an action",
                trigger=BehaviorTrigger.EVENT_OCURRED,
                trigger_condition="action fails more than 3 times consecutively",
                expected_behavior="System should try alternative approach",
                confidence=0.85,
                domain="system_behavior",
            ),
        ]
        self._rules.extend(builtins)

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, rule: BehavioralRule) -> None:
        """Add a new behavioral rule."""
        self._rules.append(rule)

    def get_rules(self, domain: str | None = None) -> list[BehavioralRule]:
        """Return all rules, optionally filtered by domain."""
        if domain is None:
            return list(self._rules)
        return [r for r in self._rules if r.domain == domain]

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    # ------------------------------------------------------------------
    # Pattern detection
    # ------------------------------------------------------------------

    def match_rules(
        self,
        trigger: BehaviorTrigger,
        condition_hint: str = "",
    ) -> list[BehavioralRule]:
        """
        Find rules matching a trigger and optional condition hint.

        Args:
            trigger: The trigger type to match.
            condition_hint: Optional text to match against conditions.

        Returns:
            List of matching BehavioralRule instances.
        """
        matches: list[BehavioralRule] = []
        for rule in self._rules:
            if rule.trigger == trigger:
                if not condition_hint:
                    matches.append(rule)
                elif condition_hint.lower() in rule.trigger_condition.lower():
                    matches.append(rule)
        return matches

    def predict_behavior(
        self,
        entity: Entity,
        trigger: BehaviorTrigger,
        condition_hint: str = "",
    ) -> list[str]:
        """
        Predict expected behaviors for a given entity and trigger.

        Args:
            entity: The entity to predict behavior for.
            trigger: The triggering event type.
            condition_hint: Optional condition to narrow predictions.

        Returns:
            List of expected behavior strings.
        """
        rules = self.match_rules(trigger, condition_hint)
        behaviors: list[str] = []

        for rule in rules:
            if rule.confidence >= 0.5:
                behaviors.append(rule.expected_behavior)

        return behaviors