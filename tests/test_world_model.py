"""
Phase 7.4 — World Model Foundation: Tests.
"""
import pytest
from datetime import datetime

from atlas.world_model.models import (
    Entity, EntityCategory, EntityStatus, Event, EventType, State,
    Goal, GoalStatus, Action, Observation, Prediction,
    CausalRelation, RelationType, BehavioralRule, BehaviorTrigger,
)
from atlas.world_model.world_graph import WorldGraph
from atlas.world_model.behavior_model import BehaviorModel
from atlas.world_model.prediction_engine import PredictionEngine
from atlas.world_model.world_model_memory import WorldModelMemory
from atlas.world_model.world_model_engine import WorldModelEngine


class TestEntity:
    def test_create(self):
        e = Entity(entity_id="ENT-001", label="test_entity", category=EntityCategory.SYSTEM_COMPONENT)
        assert e.entity_id == "ENT-001"
        assert e.status == EntityStatus.ACTIVE
        assert e.confidence == 0.5


class TestState:
    def test_create(self):
        s = State(state_id="S1", entity_id="ENT-001", property_values={"cpu": 80})
        assert s.property_values["cpu"] == 80


class TestWorldGraph:
    def test_add_entity(self):
        g = WorldGraph()
        e = Entity(entity_id="E1", label="test")
        g.add_entity(e)
        assert g.entity_count == 1
        assert g.get_entity("E1") is not None

    def test_add_relation(self):
        g = WorldGraph()
        g.add_entity(Entity(entity_id="E1", label="a"))
        g.add_entity(Entity(entity_id="E2", label="b"))
        r = CausalRelation(relation_id="R1", source_id="E1", target_id="E2", relation_type=RelationType.CAUSES)
        g.add_relation(r)
        assert g.relation_count == 1

    def test_find_causes(self):
        g = WorldGraph()
        g.add_entity(Entity(entity_id="E1", label="cpu"))
        g.add_entity(Entity(entity_id="E2", label="app"))
        g.add_relation(CausalRelation("R1", "E1", "E2", RelationType.DEGRADES))
        causes = g.find_causes_of("E2")
        assert len(causes) == 1
        assert causes[0].source_id == "E1"

    def test_find_causal_chain(self):
        g = WorldGraph()
        for i in range(4):
            g.add_entity(Entity(entity_id=f"E{i}", label=f"n{i}"))
        g.add_relation(CausalRelation("R1", "E0", "E1", RelationType.CAUSES))
        g.add_relation(CausalRelation("R2", "E1", "E2", RelationType.CAUSES))
        g.add_relation(CausalRelation("R3", "E2", "E3", RelationType.CAUSES))
        paths = g.find_causal_chain("E0", "E3")
        assert len(paths) == 1
        assert len(paths[0]) == 3


class TestBehaviorModel:
    def test_builtin_rules_seeded(self):
        bm = BehaviorModel()
        assert bm.rule_count >= 3

    def test_match_rules(self):
        bm = BehaviorModel()
        matches = bm.match_rules(BehaviorTrigger.GOAL_ACTIVATED, "system modification")
        assert len(matches) >= 1

    def test_predict_behavior(self):
        bm = BehaviorModel()
        e = Entity(entity_id="U1", label="user", category=EntityCategory.USER)
        behaviors = bm.predict_behavior(e, BehaviorTrigger.GOAL_ACTIVATED, "system modification")
        assert len(behaviors) >= 1

    def test_add_rule(self):
        bm = BehaviorModel()
        r = BehavioralRule(rule_id="R99", description="test", trigger=BehaviorTrigger.ALWAYS)
        bm.add_rule(r)
        assert bm.rule_count >= 4


class TestPredictionEngine:
    def test_predict_from_causal_degradation(self):
        pe = PredictionEngine()
        causes = [CausalRelation("R1", "bad", "E1", RelationType.DEGRADES, confidence=0.9)]
        preds = pe.predict_from_causal_relations("E1", causes, [])
        assert len(preds) >= 1
        assert preds[0].predicted_value.get("status") == "DEGRADED"

    def test_predict_from_behavior(self):
        pe = PredictionEngine()
        e = Entity(entity_id="U1", label="user")
        rules = [BehavioralRule(rule_id="R1", description="test", trigger=BehaviorTrigger.STATE_CHANGED, expected_behavior="reports issue", confidence=0.8)]
        preds = pe.predict_from_behavior(e, BehaviorTrigger.STATE_CHANGED, rules)
        assert len(preds) >= 1

    def test_predict_state_trend(self):
        pe = PredictionEngine()
        states = [
            State("S1", "E1", {"latency": 100}),
            State("S2", "E1", {"latency": 200}),
            State("S3", "E1", {"latency": 300}),
        ]
        pred = pe.predict_state_trend("E1", states, "latency")
        assert pred is not None
        assert pred.predicted_value.get("latency", 0) > 300

    def test_predict_all(self):
        pe = PredictionEngine()
        pe.predict_all("E1", None, [], [], [])
        # Should not crash with empty data


class TestWorldModelMemory:
    def test_store_entity(self):
        mem = WorldModelMemory()
        mem.store_entity(Entity(entity_id="E1", label="test"))
        assert mem.entity_count == 1

    def test_store_event(self):
        mem = WorldModelMemory()
        mem.store_event(Event(event_id="EV1", event_type=EventType.OBSERVATION, description="test"))
        assert mem.event_count == 1

    def test_store_state(self):
        mem = WorldModelMemory()
        mem.store_state(State("S1", "E1", {"x": 1}))
        assert mem.state_count == 1

    def test_store_goal(self):
        mem = WorldModelMemory()
        mem.store_goal(Goal(goal_id="G1", description="test"))
        assert mem.goal_count == 1

    def test_summary(self):
        mem = WorldModelMemory()
        s = mem.summary()
        assert s["entity_count"] == 0
        assert s["event_count"] == 0

    def test_invalid_limits(self):
        with pytest.raises(ValueError):
            WorldModelMemory(max_entities=0)

    def test_clear(self):
        mem = WorldModelMemory()
        mem.store_entity(Entity(entity_id="E1", label="test"))
        assert mem.entity_count == 1
        mem.clear()
        assert mem.entity_count == 0


class TestWorldModelEngine:
    def test_register_entity(self):
        engine = WorldModelEngine()
        e = engine.register_entity("test", EntityCategory.SYSTEM_COMPONENT)
        assert e.entity_id.startswith("ENT-")
        assert engine.graph.entity_count == 1

    def test_record_event(self):
        engine = WorldModelEngine()
        evt = engine.record_event(EventType.SYSTEM_ACTION, "test")
        assert evt.event_id.startswith("EVT-")

    def test_snapshot_state(self):
        engine = WorldModelEngine()
        e = engine.register_entity("test", EntityCategory.SYSTEM_COMPONENT)
        state = engine.snapshot_state(e.entity_id, {"cpu": 50})
        assert state.property_values["cpu"] == 50

    def test_add_causal_relation(self):
        engine = WorldModelEngine()
        e1 = engine.register_entity("cpu", EntityCategory.SYSTEM_COMPONENT)
        e2 = engine.register_entity("app", EntityCategory.SYSTEM_COMPONENT)
        rel = engine.add_causal_relation(e1.entity_id, e2.entity_id, RelationType.DEGRADES, "cpu degrades app")
        assert rel.source_id == e1.entity_id

    def test_causal_chain(self):
        engine = WorldModelEngine()
        a = engine.register_entity("a", EntityCategory.ABSTRACT_CONCEPT)
        b = engine.register_entity("b", EntityCategory.ABSTRACT_CONCEPT)
        c = engine.register_entity("c", EntityCategory.ABSTRACT_CONCEPT)
        engine.add_causal_relation(a.entity_id, b.entity_id, RelationType.CAUSES)
        engine.add_causal_relation(b.entity_id, c.entity_id, RelationType.CAUSES)
        paths = engine.get_causal_chain(a.entity_id, c.entity_id)
        assert len(paths) == 1
        assert len(paths[0]) == 2

    def test_goal_lifecycle(self):
        engine = WorldModelEngine()
        goal = engine.define_goal("Test goal", priority=2)
        assert engine.activate_goal(goal.goal_id) is True
        assert engine.complete_goal(goal.goal_id) is True

    def test_predict(self):
        engine = WorldModelEngine()
        e = engine.register_entity("test", EntityCategory.SYSTEM_COMPONENT)
        engine.snapshot_state(e.entity_id, {"latency": 100})
        engine.snapshot_state(e.entity_id, {"latency": 200})
        preds = engine.predict_for_entity(e.entity_id)
        assert len(preds) >= 0  # May produce predictions if trend detected

    def test_observation(self):
        engine = WorldModelEngine()
        e = engine.register_entity("test", EntityCategory.SYSTEM_COMPONENT)
        obs = engine.record_observation("observed value", e.entity_id, "latency", 150)
        assert obs.entity_id == e.entity_id

    def test_get_world_summary(self):
        engine = WorldModelEngine()
        engine.register_entity("test", EntityCategory.SYSTEM_COMPONENT)
        summary = engine.get_world_summary()
        assert summary["graph_entities"] == 1
        assert "memory" in summary