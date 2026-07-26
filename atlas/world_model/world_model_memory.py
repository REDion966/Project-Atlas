"""
Atlas World Model Memory

Bounded storage for entities, events, states, goals, actions,
observations, predictions, and relations.

Phase 7.4 — World Model Foundation.
"""

from collections import deque
from datetime import datetime
from typing import Any

from atlas.world_model.models import (
    Action,
    CausalRelation,
    Entity,
    Event,
    Goal,
    Observation,
    Prediction,
    State,
)


class WorldModelMemory:
    """
    Bounded in-memory store for world model data.

    Pure logic component. No infrastructure dependencies.
    """

    def __init__(
        self,
        max_entities: int = 1000,
        max_events: int = 2000,
        max_states: int = 1000,
        max_goals: int = 200,
        max_actions: int = 500,
        max_observations: int = 2000,
        max_predictions: int = 500,
        max_relations: int = 2000,
    ) -> None:
        if any(v <= 0 for v in (
            max_entities, max_events, max_states, max_goals,
            max_actions, max_observations, max_predictions, max_relations,
        )):
            raise ValueError("All limits must be positive integers")

        self._entities: dict[str, Entity] = {}
        self._events: deque[Event] = deque(maxlen=max_events)
        self._states: deque[State] = deque(maxlen=max_states)
        self._goals: dict[str, Goal] = {}
        self._actions: dict[str, Action] = {}
        self._observations: deque[Observation] = deque(maxlen=max_observations)
        self._predictions: deque[Prediction] = deque(maxlen=max_predictions)
        self._relations: deque[CausalRelation] = deque(maxlen=max_relations)

    def store_entity(self, entity: Entity) -> None:
        self._entities[entity.entity_id] = entity

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def get_all_entities(self) -> list[Entity]:
        return list(self._entities.values())

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    def store_event(self, event: Event) -> None:
        self._events.append(event)

    def get_events(self, n: int = 50) -> list[Event]:
        if n <= 0:
            return []
        return list(reversed(self._events))[:n]

    @property
    def event_count(self) -> int:
        return len(self._events)

    def store_state(self, state: State) -> None:
        self._states.append(state)

    def get_states(self, entity_id: str | None = None, n: int = 20) -> list[State]:
        if n <= 0:
            return []
        if entity_id is None:
            return list(reversed(self._states))[:n]
        return [s for s in reversed(self._states) if s.entity_id == entity_id][:n]

    @property
    def state_count(self) -> int:
        return len(self._states)

    def store_goal(self, goal: Goal) -> None:
        self._goals[goal.goal_id] = goal

    def get_goal(self, goal_id: str) -> Goal | None:
        return self._goals.get(goal_id)

    def get_active_goals(self) -> list[Goal]:
        from atlas.world_model.models import GoalStatus
        return [g for g in self._goals.values() if g.status == GoalStatus.ACTIVE]

    @property
    def goal_count(self) -> int:
        return len(self._goals)

    def store_action(self, action: Action) -> None:
        self._actions[action.action_id] = action

    def get_action(self, action_id: str) -> Action | None:
        return self._actions.get(action_id)

    @property
    def action_count(self) -> int:
        return len(self._actions)

    def store_observation(self, obs: Observation) -> None:
        self._observations.append(obs)

    def get_observations(self, entity_id: str | None = None, n: int = 20) -> list[Observation]:
        if n <= 0:
            return []
        if entity_id is None:
            return list(reversed(self._observations))[:n]
        return [o for o in reversed(self._observations) if o.entity_id == entity_id][:n]

    @property
    def observation_count(self) -> int:
        return len(self._observations)

    def store_prediction(self, prediction: Prediction) -> None:
        self._predictions.append(prediction)

    def get_predictions(self, entity_id: str | None = None, n: int = 20) -> list[Prediction]:
        if n <= 0:
            return []
        if entity_id is None:
            return list(reversed(self._predictions))[:n]
        return [p for p in reversed(self._predictions) if p.entity_id == entity_id][:n]

    @property
    def prediction_count(self) -> int:
        return len(self._predictions)

    def store_relation(self, relation: CausalRelation) -> None:
        self._relations.append(relation)

    def get_relations(self, n: int = 50) -> list[CausalRelation]:
        if n <= 0:
            return []
        return list(reversed(self._relations))[:n]

    @property
    def relation_count(self) -> int:
        return len(self._relations)

    def summary(self) -> dict[str, Any]:
        return {
            "entity_count": self.entity_count,
            "event_count": self.event_count,
            "state_count": self.state_count,
            "goal_count": self.goal_count,
            "action_count": self.action_count,
            "observation_count": self.observation_count,
            "prediction_count": self.prediction_count,
            "relation_count": self.relation_count,
        }

    def clear(self) -> None:
        self._entities.clear()
        self._events.clear()
        self._states.clear()
        self._goals.clear()
        self._actions.clear()
        self._observations.clear()
        self._predictions.clear()
        self._relations.clear()