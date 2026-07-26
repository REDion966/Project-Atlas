"""
Atlas Prediction Engine

Generates deterministic predictions using current state, known causal
relations, and behavioral rules. Pure logic. No AI calls.

Phase 7.4 — World Model Foundation.
"""

from datetime import datetime, timedelta
from typing import Any

from atlas.world_model.models import (
    BehavioralRule,
    BehaviorTrigger,
    CausalRelation,
    Entity,
    EntityStatus,
    Prediction,
    RelationType,
    State,
)


class PredictionEngine:
    """
    Generates deterministic predictions based on world model state.

    Pure logic component. No infrastructure dependencies.
    Uses causal relations and behavioral rules to predict future
    states and entity behavior.
    """

    def __init__(self) -> None:
        self._prediction_counter = 0

    def _next_prediction_id(self) -> str:
        self._prediction_counter += 1
        return f"PRED-{self._prediction_counter:06d}"

    # ------------------------------------------------------------------
    # Causal prediction
    # ------------------------------------------------------------------

    def predict_from_causal_relations(
        self,
        entity_id: str,
        causes: list[CausalRelation],
        states: list[State],
    ) -> list[Prediction]:
        """
        Predict entity states based on known causal relationships.

        Args:
            entity_id: The entity to predict for.
            causes: Causal relations where this entity is the effect.
            states: Recent state snapshots for context.

        Returns:
            List of Prediction instances.
        """
        if not causes:
            return []

        predictions: list[Prediction] = []

        for cause in causes:
            if cause.relation_type == RelationType.DEGRADES:
                predictions.append(Prediction(
                    prediction_id=self._next_prediction_id(),
                    description=f"Entity '{entity_id}' may degrade due to '{cause.source_id}'",
                    entity_id=entity_id,
                    predicted_value={"status": EntityStatus.DEGRADED.name},
                    confidence=cause.confidence * 0.8,
                    reasoning=f"Causal relation: {cause.description or cause.relation_type.name}",
                    causal_relation_ids=[cause.relation_id],
                ))
            elif cause.relation_type == RelationType.IMPROVES:
                predictions.append(Prediction(
                    prediction_id=self._next_prediction_id(),
                    description=f"Entity '{entity_id}' may improve due to '{cause.source_id}'",
                    entity_id=entity_id,
                    predicted_value={"status": EntityStatus.ACTIVE.name},
                    confidence=cause.confidence * 0.7,
                    reasoning=f"Causal relation: {cause.description or cause.relation_type.name}",
                    causal_relation_ids=[cause.relation_id],
                ))
            elif cause.relation_type == RelationType.CAUSES:
                predictions.append(Prediction(
                    prediction_id=self._next_prediction_id(),
                    description=f"Entity '{entity_id}' may change due to '{cause.source_id}'",
                    entity_id=entity_id,
                    predicted_value={"change_expected": True},
                    confidence=cause.confidence * 0.6,
                    reasoning=f"Causal relation: {cause.description or cause.relation_type.name}",
                    causal_relation_ids=[cause.relation_id],
                ))

        return predictions

    # ------------------------------------------------------------------
    # Behavioral prediction
    # ------------------------------------------------------------------

    def predict_from_behavior(
        self,
        entity: Entity,
        trigger: BehaviorTrigger,
        rules: list[BehavioralRule],
        condition_hint: str = "",
    ) -> list[Prediction]:
        """
        Predict entity behavior based on matching behavioral rules.

        Args:
            entity: The entity to predict behavior for.
            trigger: The triggering condition.
            rules: Available behavioral rules to match.
            condition_hint: Optional condition string.

        Returns:
            List of Prediction instances.
        """
        predictions: list[Prediction] = []

        for rule in rules:
            if rule.trigger != trigger:
                continue
            if condition_hint and condition_hint.lower() not in rule.trigger_condition.lower():
                continue
            if rule.confidence < 0.4:
                continue

            predictions.append(Prediction(
                prediction_id=self._next_prediction_id(),
                description=f"Predicted behavior: {rule.expected_behavior}",
                entity_id=entity.entity_id,
                predicted_value={"behavior": rule.expected_behavior},
                confidence=rule.confidence,
                reasoning=f"Behavioral rule: {rule.description}",
            ))

        return predictions

    # ------------------------------------------------------------------
    # State-based prediction
    # ------------------------------------------------------------------

    def predict_state_trend(
        self,
        entity_id: str,
        states: list[State],
        property_name: str,
    ) -> Prediction | None:
        """
        Predict a property trend based on state history.

        If the property has been monotonically changing across at
        least 2 states, predict continuation of the trend.

        Args:
            entity_id: The entity to predict for.
            states: Ordered list of State snapshots (oldest first).
            property_name: The property to analyze.

        Returns:
            A Prediction if a trend is detected, or None.
        """
        if len(states) < 2:
            return None

        values: list[Any] = []
        for state in states:
            if property_name in state.property_values:
                values.append(state.property_values[property_name])

        if len(values) < 2:
            return None

        # Check for numeric trend
        try:
            numeric_values = [float(v) for v in values]
        except (ValueError, TypeError):
            return None

        if len(numeric_values) < 2:
            return None

        first = numeric_values[0]
        last = numeric_values[-1]
        change = last - first

        if abs(change) < 0.001:
            return None

        direction = "increasing" if change > 0 else "decreasing"
        avg_change = change / (len(numeric_values) - 1)

        # Predict next value
        next_value = last + avg_change

        return Prediction(
            prediction_id=self._next_prediction_id(),
            description=(
                f"Property '{property_name}' is {direction} "
                f"({first:.2f} → {last:.2f}). "
                f"Predicted next: {next_value:.2f}"
            ),
            entity_id=entity_id,
            predicted_value={property_name: round(next_value, 2)},
            confidence=min(0.3 + (len(values) * 0.1), 0.9),
            reasoning=f"Trend analysis over {len(values)} state snapshots",
        )

    # ------------------------------------------------------------------
    # Combined prediction
    # ------------------------------------------------------------------

    def predict_all(
        self,
        entity_id: str,
        entity: Entity | None,
        causes: list[CausalRelation],
        states: list[State],
        rules: list[BehavioralRule],
        trigger: BehaviorTrigger = BehaviorTrigger.STATE_CHANGED,
    ) -> list[Prediction]:
        """
        Run all prediction methods and return combined results.

        Args:
            entity_id: The entity to predict for.
            entity: The Entity object (if available).
            causes: Causal relations affecting this entity.
            states: State history for this entity.
            rules: Available behavioral rules.
            trigger: Trigger to use for behavioral predictions.

        Returns:
            Combined list of Prediction instances.
        """
        predictions: list[Prediction] = []

        predictions.extend(self.predict_from_causal_relations(entity_id, causes, states))

        if entity is not None:
            predictions.extend(self.predict_from_behavior(entity, trigger, rules))

        if states:
            for prop_name in self._get_common_properties(states):
                trend = self.predict_state_trend(entity_id, states, prop_name)
                if trend is not None:
                    predictions.append(trend)

        return predictions

    def _get_common_properties(self, states: list[State]) -> list[str]:
        """Find properties that appear in multiple states."""
        prop_counts: dict[str, int] = {}
        for state in states:
            for key in state.property_values:
                prop_counts[key] = prop_counts.get(key, 0) + 1
        return [k for k, v in prop_counts.items() if v >= 2]