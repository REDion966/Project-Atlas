"""
Atlas World Model — Data Models

Pure data models representing Atlas's internal world model.
Phase 7.4 — World Model Foundation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


# ===================================================================
# Core Entity Types
# ===================================================================


class EntityCategory(Enum):
    """Category of an entity in the world model."""

    SYSTEM_COMPONENT = auto()
    USER = auto()
    AI_PROVIDER = auto()
    TOOL = auto()
    KNOWLEDGE_DOMAIN = auto()
    EXTERNAL_SYSTEM = auto()
    ABSTRACT_CONCEPT = auto()
    TASK = auto()
    RESOURCE = auto()


class EntityStatus(Enum):
    """Current status of an entity."""

    ACTIVE = auto()
    INACTIVE = auto()
    DEGRADED = auto()
    UNKNOWN = auto()
    DEPRECATED = auto()


@dataclass(slots=True)
class Entity:
    """
    A discrete thing in Atlas's world model.

    Attributes:
        entity_id: Unique identifier.
        label: Human-readable label.
        category: The category this entity belongs to.
        status: Current operational status.
        confidence: How confident Atlas is in this entity's existence/properties.
        created_at: When this entity was first modeled.
        last_updated: When this entity was last modified.
        metadata: Optional additional properties.
    """

    entity_id: str
    label: str
    category: EntityCategory = EntityCategory.ABSTRACT_CONCEPT
    status: EntityStatus = EntityStatus.ACTIVE
    confidence: float = 0.5
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


# ===================================================================
# Events and States
# ===================================================================


class EventType(Enum):
    """Type of event in the world model."""

    STATE_CHANGE = auto()
    OBSERVATION = auto()
    PREDICTION = auto()
    USER_ACTION = auto()
    SYSTEM_ACTION = auto()
    EXTERNAL_EVENT = auto()
    TIMED_EVENT = auto()
    GOAL_COMPLETED = auto()
    GOAL_FAILED = auto()


@dataclass(slots=True)
class Event:
    """
    A discrete occurrence in the world model timeline.

    Attributes:
        event_id: Unique identifier.
        event_type: The type of event.
        description: Human-readable description.
        source_entity_id: Entity that caused this event.
        target_entity_ids: Entities affected by this event.
        data: Structured data about the event.
        timestamp: When this event occurred.
        confidence: How confident Atlas is that this event occurred.
    """

    event_id: str
    event_type: EventType
    description: str
    source_entity_id: str = ""
    target_entity_ids: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    confidence: float = 0.5


@dataclass(slots=True)
class State:
    """
    A snapshot of entity state at a point in time.

    Attributes:
        state_id: Unique identifier.
        entity_id: The entity this state belongs to.
        property_values: Key-value pairs of property names to values.
        observed_at: When this state was observed.
        confidence: How certain Atlas is about this state.
    """

    state_id: str
    entity_id: str
    property_values: dict[str, Any] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=datetime.now)
    confidence: float = 0.5


# ===================================================================
# Goals and Actions
# ===================================================================


class GoalStatus(Enum):
    """Status of a goal."""

    PROPOSED = auto()
    ACTIVE = auto()
    COMPLETED = auto()
    FAILED = auto()
    ABANDONED = auto()
    DEFERRED = auto()


@dataclass(slots=True)
class Goal:
    """
    A desired future state or outcome.

    Attributes:
        goal_id: Unique identifier.
        description: What this goal intends to achieve.
        status: Current goal status.
        priority: Priority level (1 = highest).
        parent_goal_id: ID of a parent goal (if this is a sub-goal).
        related_entity_ids: Entities this goal relates to.
        created_at: When this goal was defined.
        deadline: Optional deadline for completion.
        metadata: Optional additional context.
    """

    goal_id: str
    description: str
    status: GoalStatus = GoalStatus.PROPOSED
    priority: int = 3
    parent_goal_id: str = ""
    related_entity_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    deadline: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Action:
    """
    An executable action that can be performed.

    Attributes:
        action_id: Unique identifier.
        label: Human-readable label.
        description: What this action does.
        goal_id: The goal this action serves (if any).
        required_entity_ids: Entities needed to perform this action.
        affected_entity_ids: Entities affected by this action.
        preconditions: Conditions that must be true before execution.
        expected_outcomes: What is expected to happen.
        success_count: How many times this action succeeded.
        failure_count: How many times this action failed.
    """

    action_id: str
    label: str
    description: str = ""
    goal_id: str = ""
    required_entity_ids: list[str] = field(default_factory=list)
    affected_entity_ids: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ===================================================================
# Observation and Prediction
# ===================================================================


@dataclass(slots=True)
class Observation:
    """
    A discrete observation about the world.

    Attributes:
        observation_id: Unique identifier.
        description: What was observed.
        entity_id: The entity being observed.
        property_name: The property being observed.
        value: The observed value.
        observed_at: When the observation was made.
        confidence: How reliable the observation is.
        source: Where the observation came from.
    """

    observation_id: str
    description: str
    entity_id: str = ""
    property_name: str = ""
    value: Any = None
    observed_at: datetime = field(default_factory=datetime.now)
    confidence: float = 0.5
    source: str = ""


@dataclass(slots=True)
class Prediction:
    """
    A prediction about a future state or event.

    Attributes:
        prediction_id: Unique identifier.
        description: What is predicted.
        entity_id: The entity this prediction is about.
        predicted_value: The predicted future value or state.
        confidence: How confident Atlas is in this prediction.
        reasoning: Chain of reasoning that produced this prediction.
        causal_relation_ids: Causal relations that support this prediction.
        predicted_at: When this prediction was made.
        valid_until: When this prediction should be re-evaluated.
    """

    prediction_id: str
    description: str
    entity_id: str = ""
    predicted_value: Any = None
    confidence: float = 0.5
    reasoning: str = ""
    causal_relation_ids: list[str] = field(default_factory=list)
    predicted_at: datetime = field(default_factory=datetime.now)
    valid_until: datetime | None = None


# ===================================================================
# Relations
# ===================================================================


class RelationType(Enum):
    """Type of relationship between entities."""

    CAUSES = auto()
    DEPENDS_ON = auto()
    OWNS = auto()
    USES = auto()
    IMPROVES = auto()
    DEGRADES = auto()
    SUPPORTS = auto()
    CONFLICTS_WITH = auto()
    PREDICTS = auto()
    RELATES_TO = auto()
    PART_OF = auto()
    PRECEDES = auto()


@dataclass(slots=True)
class CausalRelation:
    """
    A causal relationship between two entities, events, or states.

    Attributes:
        relation_id: Unique identifier.
        source_id: The entity/event/state that is the cause.
        target_id: The entity/event/state that is the effect.
        relation_type: The type of causal relationship.
        confidence: How confident Atlas is in this causal link.
        observed_count: How many times this causation was observed.
        first_observed: When this relation was first noted.
        last_observed: When this relation was last observed.
        description: Human-readable description of the causation.
    """

    relation_id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    confidence: float = 0.5
    observed_count: int = 1
    first_observed: datetime = field(default_factory=datetime.now)
    last_observed: datetime = field(default_factory=datetime.now)
    description: str = ""


# ===================================================================
# Behavior Model Types
# ===================================================================


class BehaviorTrigger(Enum):
    """What triggers a behavioral rule."""

    EVENT_OCURRED = auto()
    STATE_CHANGED = auto()
    TIME_REACHED = auto()
    THRESHOLD_CROSSED = auto()
    GOAL_ACTIVATED = auto()
    ALWAYS = auto()


@dataclass(slots=True)
class BehavioralRule:
    """
    A single rule describing expected behavior.

    Attributes:
        rule_id: Unique identifier.
        description: What this rule describes.
        trigger: What triggers this rule.
        trigger_condition: Condition that must be met.
        expected_behavior: What behavior is expected.
        confidence: Confidence in this rule.
        observation_count: How many times this behavior was observed.
        domain: The domain this rule applies to.
        exceptions: Known exceptions to this rule.
    """

    rule_id: str
    description: str
    trigger: BehaviorTrigger = BehaviorTrigger.ALWAYS
    trigger_condition: str = ""
    expected_behavior: str = ""
    confidence: float = 0.5
    observation_count: int = 1
    domain: str = "general"
    exceptions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)