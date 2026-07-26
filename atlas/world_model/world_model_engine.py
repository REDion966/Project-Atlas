"""
Atlas World Model Engine

Orchestrates the world model: updates world state, builds causal graph,
maintains entity relationships, produces predictions, and supports
reasoning queries.

Phase 7.4 — World Model Foundation.
"""

from datetime import datetime
from typing import Any

from atlas.world_model.models import (
    Action,
    CausalRelation,
    Entity,
    EntityCategory,
    EntityStatus,
    Event,
    EventType,
    Goal,
    GoalStatus,
    Observation,
    Prediction,
    RelationType,
    State,
)
from atlas.world_model.behavior_model import BehaviorModel
from atlas.world_model.prediction_engine import PredictionEngine
from atlas.world_model.world_graph import WorldGraph
from atlas.world_model.world_model_memory import WorldModelMemory


class WorldModelEngine:
    """
    Orchestrates Atlas's internal world model.

    Pure logic component. No infrastructure dependencies.
    Uses dependency injection for all sub-components.

    Responsibilities:
    - Update world state
    - Build causal graph
    - Maintain entity relationships
    - Produce predictions
    - Support reasoning queries
    """

    def __init__(
        self,
        memory: WorldModelMemory | None = None,
        graph: WorldGraph | None = None,
        prediction_engine: PredictionEngine | None = None,
        behavior_model: BehaviorModel | None = None,
    ) -> None:
        self._memory = memory or WorldModelMemory()
        self._graph = graph or WorldGraph()
        self._prediction_engine = prediction_engine or PredictionEngine()
        self._behavior_model = behavior_model or BehaviorModel()
        self._entity_counter = 0
        self._event_counter = 0
        self._state_counter = 0

    @property
    def memory(self) -> WorldModelMemory:
        return self._memory

    @property
    def graph(self) -> WorldGraph:
        return self._graph

    # ------------------------------------------------------------------
    # Entity lifecycle
    # ------------------------------------------------------------------

    def register_entity(
        self,
        label: str,
        category: EntityCategory,
        description: str = "",
        confidence: float = 0.8,
    ) -> Entity:
        """
        Register a new entity in the world model.

        Args:
            label: Human-readable label.
            category: Entity category.
            description: Optional description.
            confidence: Initial confidence.

        Returns:
            The created Entity.
        """
        self._entity_counter += 1
        entity_id = f"ENT-{self._entity_counter:06d}"
        entity = Entity(
            entity_id=entity_id,
            label=label,
            category=category,
            confidence=confidence,
            description=description,
        )
        self._memory.store_entity(entity)
        self._graph.add_entity(entity)
        return entity

    def update_entity_status(
        self,
        entity_id: str,
        status: EntityStatus,
    ) -> bool:
        """Update an entity's status."""
        entity = self._graph.get_entity(entity_id)
        if entity is None:
            return False
        entity.status = status
        entity.last_updated = datetime.now()
        self._memory.store_entity(entity)
        return True

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._graph.get_entity(entity_id)

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_event(
        self,
        event_type: EventType,
        description: str,
        source_entity_id: str = "",
        target_entity_ids: list[str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Event:
        """Record an event in the world model timeline."""
        self._event_counter += 1
        event = Event(
            event_id=f"EVT-{self._event_counter:06d}",
            event_type=event_type,
            description=description,
            source_entity_id=source_entity_id,
            target_entity_ids=target_entity_ids or [],
            data=data or {},
        )
        self._memory.store_event(event)
        return event

    # ------------------------------------------------------------------
    # State snapshotting
    # ------------------------------------------------------------------

    def snapshot_state(
        self,
        entity_id: str,
        properties: dict[str, Any],
    ) -> State:
        """Record a state snapshot for an entity."""
        self._state_counter += 1
        state = State(
            state_id=f"STATE-{self._state_counter:06d}",
            entity_id=entity_id,
            property_values=properties,
        )
        self._memory.store_state(state)
        return state

    # ------------------------------------------------------------------
    # Causal relation building
    # ------------------------------------------------------------------

    def add_causal_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        description: str = "",
        confidence: float = 0.5,
    ) -> CausalRelation:
        """Add a causal relation between two entities."""
        rel_id = f"REL-{self._graph.relation_count + 1:06d}"
        relation = CausalRelation(
            relation_id=rel_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            confidence=confidence,
            description=description,
        )
        self._graph.add_relation(relation)
        self._memory.store_relation(relation)
        return relation

    # ------------------------------------------------------------------
    # Prediction generation
    # ------------------------------------------------------------------

    def predict_for_entity(self, entity_id: str) -> list[Prediction]:
        """Generate predictions for a specific entity."""
        entity = self._graph.get_entity(entity_id)
        causes = self._graph.find_causes_of(entity_id)
        states = self._memory.get_states(entity_id, n=20)
        rules = self._behavior_model.get_rules()

        predictions = self._prediction_engine.predict_all(
            entity_id, entity, causes, states, rules,
        )
        for prediction in predictions:
            self._memory.store_prediction(prediction)
        return predictions

    # ------------------------------------------------------------------
    # Goal management
    # ------------------------------------------------------------------

    def define_goal(
        self,
        description: str,
        priority: int = 3,
        parent_goal_id: str = "",
    ) -> Goal:
        """Define a new goal."""
        goal_id = f"GOAL-{self._memory.goal_count + 1:04d}"
        goal = Goal(
            goal_id=goal_id,
            description=description,
            priority=priority,
            parent_goal_id=parent_goal_id,
        )
        self._memory.store_goal(goal)
        return goal

    def activate_goal(self, goal_id: str) -> bool:
        goal = self._memory.get_goal(goal_id)
        if goal is None:
            return False
        goal.status = GoalStatus.ACTIVE
        return True

    def complete_goal(self, goal_id: str) -> bool:
        goal = self._memory.get_goal(goal_id)
        if goal is None:
            return False
        goal.status = GoalStatus.COMPLETED
        return True

    # ------------------------------------------------------------------
    # Action management
    # ------------------------------------------------------------------

    def register_action(
        self,
        label: str,
        description: str = "",
        goal_id: str = "",
        preconditions: list[str] | None = None,
        expected_outcomes: list[str] | None = None,
    ) -> Action:
        """Register an action."""
        action_id = f"ACT-{self._memory.action_count + 1:04d}"
        action = Action(
            action_id=action_id,
            label=label,
            description=description,
            goal_id=goal_id,
            preconditions=preconditions or [],
            expected_outcomes=expected_outcomes or [],
        )
        self._memory.store_action(action)
        return action

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def record_observation(
        self,
        description: str,
        entity_id: str = "",
        property_name: str = "",
        value: Any = None,
        source: str = "",
    ) -> Observation:
        """Record an observation."""
        obs_id = f"OBS-{self._memory.observation_count + 1:04d}"
        obs = Observation(
            observation_id=obs_id,
            description=description,
            entity_id=entity_id,
            property_name=property_name,
            value=value,
            source=source,
        )
        self._memory.store_observation(obs)
        return obs

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_causal_chain(
        self,
        source_id: str,
        target_id: str,
    ) -> list[list[CausalRelation]]:
        """Find causal paths between two entities."""
        return self._graph.find_causal_chain(source_id, target_id)

    def get_entity_causes(self, entity_id: str) -> list[CausalRelation]:
        return self._graph.find_causes_of(entity_id)

    def get_entity_effects(self, entity_id: str) -> list[CausalRelation]:
        return self._graph.find_effects_of(entity_id)

    def get_world_summary(self) -> dict[str, Any]:
        """Return a summary of the current world state."""
        return {
            "memory": self._memory.summary(),
            "graph_entities": self._graph.entity_count,
            "graph_relations": self._graph.relation_count,
            "behavior_rules": self._behavior_model.rule_count,
            "active_goals": self._memory.get_active_goals(),
        }