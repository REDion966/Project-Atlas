"""Phase 18.6 — ToolLearner tests."""

from atlas.toolchain.effectiveness import ToolEffectivenessTracker
from atlas.toolchain.learner import (
    ACT_LEARN_FAILURE,
    ACT_LEARN_SKILL,
    ACT_PROMOTE,
    ACT_RECORD,
    ToolLearner,
    ToolLearningRecommendation,
)
from atlas.toolchain.models import (
    SkillKind,
    ToolChainResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _success_result(
    chain_id: str = "chain:alpha",
    tools: tuple[str, ...] = ("tool_a", "tool_b"),
) -> ToolChainResult:
    """Build a successful ToolChainResult with per-step result dicts."""
    step_results = tuple(
        {
            "step_id": f"step:{index:04d}",
            "tool_name": tool_name,
            "success": True,
            "output": {},
            "error": "",
            "execution_time_ms": 0.0,
        }
        for index, tool_name in enumerate(tools)
    )
    return ToolChainResult(
        chain_id=chain_id,
        success=True,
        step_results=step_results,
        execution_time_ms=0.0,
        metadata={"strategy": "sequential"},
    )


def _failure_result(chain_id: str = "chain:beta") -> ToolChainResult:
    """Build a failed ToolChainResult."""
    return ToolChainResult(
        chain_id=chain_id,
        success=False,
        step_results=(),
        error="step failed",
        execution_time_ms=0.0,
    )


def _seed_effective_tracker(tracker: ToolEffectivenessTracker, tools: tuple[str, ...]) -> None:
    """Record successful high-effectiveness observations for each tool."""
    for tool in tools:
        tracker.record(
            tool,
            success=True,
            execution_time_ms=0.0,
        )


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_tracker(self):
        learner = ToolLearner()
        assert isinstance(learner.tracker, ToolEffectivenessTracker)

    def test_injected_tracker(self):
        tracker = ToolEffectivenessTracker()
        learner = ToolLearner(tracker=tracker)
        assert learner.tracker is tracker


# ---------------------------------------------------------------------------
# Fail-closed / malformed input tests
# ---------------------------------------------------------------------------


class TestFailClosedMalformed:
    def test_none_result_returns_empty(self):
        learner = ToolLearner()
        assert learner.learn(None) == []

    def test_none_result_never_raises(self):
        learner = ToolLearner()
        result = learner.learn(None)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Failure path tests
# ---------------------------------------------------------------------------


class TestFailurePath:
    def test_failed_result_emits_learn_failure(self):
        learner = ToolLearner()
        recommendations = learner.learn(_failure_result())

        assert len(recommendations) == 1
        rec = recommendations[0]
        assert rec.action == ACT_LEARN_FAILURE
        assert rec.chain_id == "chain:beta"
        assert rec.confidence == 0.0
        assert rec.skill is None

    def test_failure_never_promotes(self):
        learner = ToolLearner()
        recommendations = learner.learn(_failure_result())
        actions = [r.action for r in recommendations]
        assert ACT_PROMOTE not in actions
        assert ACT_LEARN_SKILL not in actions


# ---------------------------------------------------------------------------
# Learner recommendations tests
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_success_without_evidence_records_only(self):
        """Successful chain but no tracker evidence: only 'record'."""
        learner = ToolLearner()
        recommendations = learner.learn(_success_result())

        actions = [r.action for r in recommendations]
        assert ACT_RECORD in actions
        # No promote/learn without evidence (default effectiveness 0.5).
        assert ACT_PROMOTE not in actions
        assert ACT_LEARN_SKILL not in actions

    def test_success_with_effective_evidence(self):
        """Successful chain with effective tracker evidence: record + promote + learn."""
        tracker = ToolEffectivenessTracker()
        _seed_effective_tracker(tracker, ("tool_a", "tool_b"))
        learner = ToolLearner(tracker=tracker)

        recommendations = learner.learn(_success_result())
        actions = [r.action for r in recommendations]

        assert ACT_RECORD in actions
        assert ACT_PROMOTE in actions
        assert ACT_LEARN_SKILL in actions

    def test_learn_skill_kind_is_learned(self):
        tracker = ToolEffectivenessTracker()
        _seed_effective_tracker(tracker, ("tool_a",))
        learner = ToolLearner(tracker=tracker)

        recommendations = learner.learn(_success_result(tools=("tool_a",)))
        learn_recs = [r for r in recommendations if r.action == ACT_LEARN_SKILL]

        assert len(learn_recs) == 1
        skill = learn_recs[0].skill
        assert skill is not None
        assert skill.kind == SkillKind.LEARNED
        assert skill.chain is not None
        assert skill.chain.tool_names == ("tool_a",)

    def test_learn_skill_chain_wraps_same_tools(self):
        tracker = ToolEffectivenessTracker()
        tools = ("tool_a", "tool_b", "tool_c")
        _seed_effective_tracker(tracker, tools)
        learner = ToolLearner(tracker=tracker)

        recommendations = learner.learn(_success_result(tools=tools))
        learn_recs = [r for r in recommendations if r.action == ACT_LEARN_SKILL]

        assert len(learn_recs) == 1
        skill = learn_recs[0].skill
        assert skill is not None
        assert skill.chain is not None
        assert skill.chain.tool_names == tools

    def test_success_without_step_results_records_only(self):
        """Chain succeeded but has empty step_results: no tools to learn from."""
        result = ToolChainResult(
            chain_id="chain:empty",
            success=True,
            step_results=(),
            execution_time_ms=0.0,
        )
        learner = ToolLearner()
        recommendations = learner.learn(result)

        actions = [r.action for r in recommendations]
        assert actions == [ACT_RECORD]

    def test_success_never_emits_failure(self):
        learner = ToolLearner()
        recommendations = learner.learn(_success_result())
        actions = [r.action for r in recommendations]
        assert ACT_LEARN_FAILURE not in actions


# ---------------------------------------------------------------------------
# Effectiveness integration tests
# ---------------------------------------------------------------------------


class TestEffectivenessIntegration:
    def test_promotion_requires_evidence(self):
        """No tracker evidence means effectiveness is default (0.5) — no promote."""
        learner = ToolLearner()
        recommendations = learner.learn(_success_result())
        actions = [r.action for r in recommendations]
        assert ACT_PROMOTE not in actions

    def test_promote_when_effective(self):
        tracker = ToolEffectivenessTracker()
        _seed_effective_tracker(tracker, ("tool_a", "tool_b"))
        learner = ToolLearner(tracker=tracker)

        recommendations = learner.learn(_success_result())
        promote_recs = [r for r in recommendations if r.action == ACT_PROMOTE]

        assert len(promote_recs) == 1
        assert promote_recs[0].confidence >= 0.6

    def test_shared_tracker_via_learner_tracker_property(self):
        """The learner's tracker can be populated after construction."""
        learner = ToolLearner()
        # Populate via the public tracker property.
        learner.tracker.record("tool_a", success=True, execution_time_ms=0.0)

        recommendations = learner.learn(_success_result(tools=("tool_a",)))
        learn_recs = [r for r in recommendations if r.action == ACT_LEARN_SKILL]
        assert len(learn_recs) == 1

    def test_learning_requires_observations(self):
        """A tool without observations prevents skill learning."""
        tracker = ToolEffectivenessTracker()
        # Only tool_a has evidence; tool_b does not.
        _seed_effective_tracker(tracker, ("tool_a",))
        learner = ToolLearner(tracker=tracker)

        recommendations = learner.learn(_success_result(tools=("tool_a", "tool_b")))
        actions = [r.action for r in recommendations]
        assert ACT_LEARN_SKILL not in actions


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_identical_inputs_identical_recommendations(self):
        tracker = ToolEffectivenessTracker()
        _seed_effective_tracker(tracker, ("tool_a", "tool_b"))
        learner = ToolLearner(tracker=tracker)

        result = _success_result()
        r1 = learner.learn(result)
        r2 = learner.learn(result)

        assert [x.action for x in r1] == [x.action for x in r2]
        assert [x.recommendation_id for x in r1] == [
            x.recommendation_id for x in r2
        ]
        assert [x.confidence for x in r1] == [x.confidence for x in r2]

    def test_identical_failure_inputs_identical_recommendations(self):
        learner = ToolLearner()
        result = _failure_result()
        r1 = learner.learn(result)
        r2 = learner.learn(result)

        assert r1[0].action == r2[0].action
        assert r1[0].recommendation_id == r2[0].recommendation_id

    def test_learned_skill_id_is_stable(self):
        tracker = ToolEffectivenessTracker()
        _seed_effective_tracker(tracker, ("tool_a",))
        learner = ToolLearner(tracker=tracker)

        result = _success_result(tools=("tool_a",))
        r1 = learner.learn(result)
        r2 = learner.learn(result)

        s1 = [x for x in r1 if x.action == ACT_LEARN_SKILL][0].skill
        s2 = [x for x in r2 if x.action == ACT_LEARN_SKILL][0].skill
        assert s1 is not None and s2 is not None
        assert s1.skill_id == s2.skill_id


# ---------------------------------------------------------------------------
# Recommendation model tests
# ---------------------------------------------------------------------------


class TestRecommendationModel:
    def test_to_dict_serialization(self):
        tracker = ToolEffectivenessTracker()
        _seed_effective_tracker(tracker, ("tool_a",))
        learner = ToolLearner(tracker=tracker)

        recommendations = learner.learn(_success_result(tools=("tool_a",)))
        learn_recs = [r for r in recommendations if r.action == ACT_LEARN_SKILL]
        rec = learn_recs[0]

        data = rec.to_dict()
        assert data["action"] == ACT_LEARN_SKILL
        assert data["skill"] is not None
        assert data["skill"]["kind"] == "LEARNED"

    def test_failure_recommendation_to_dict(self):
        learner = ToolLearner()
        rec = learner.learn(_failure_result())[0]
        data = rec.to_dict()
        assert data["action"] == ACT_LEARN_FAILURE
        assert data["skill"] is None