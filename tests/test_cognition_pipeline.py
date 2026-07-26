"""
Phase 7.2 — Integrated Cognitive Pipeline: Tests.

Tests for the complete pipeline, individual stages, metrics,
state passing, failure handling, and backward compatibility.
"""

from unittest.mock import MagicMock, patch

import pytest

from atlas.cognition.models import (
    CognitionState,
    PipelineMetrics,
    PipelineResult,
    StageResult,
    StageStatus,
    StageType,
)
from atlas.cognition.pipeline import CognitionPipeline


# ===================================================================
# Model Tests
# ===================================================================

class TestStageType:
    def test_has_all_stages(self):
        types = list(StageType)
        assert StageType.CONVERSATION_CONTEXT in types
        assert StageType.MEMORY_RETRIEVAL in types
        assert StageType.KNOWLEDGE_RETRIEVAL in types
        assert StageType.UNDERSTANDING in types
        assert StageType.REASONING in types
        assert StageType.PLANNING in types
        assert StageType.TOOL_DECISION in types
        assert StageType.TOOL_EXECUTION in types
        assert StageType.AI_RESPONSE in types
        assert StageType.REFLECTION in types
        assert StageType.LEARNING in types
        assert StageType.EVOLUTION_OBSERVATION in types
        assert StageType.MEMORY_STORAGE in types


class TestStageResult:
    def test_create(self):
        sr = StageResult(stage=StageType.REASONING, status=StageStatus.SUCCESS)
        assert sr.stage == StageType.REASONING
        assert sr.status == StageStatus.SUCCESS
        assert sr.duration_ms == 0.0
        assert sr.confidence == 0.0


class TestPipelineMetrics:
    def test_defaults(self):
        m = PipelineMetrics()
        assert m.total_duration_ms == 0.0
        assert m.stage_count == 0
        assert m.tool_usage == []
        assert m.pipeline_path == []


class TestPipelineResult:
    def test_create(self):
        pr = PipelineResult(success=True, final_response="hello")
        assert pr.success is True
        assert pr.final_response == "hello"
        assert pr.stages == []


class TestCognitionState:
    def test_defaults(self):
        state = CognitionState()
        assert state.user_input == ""
        assert state.memories == []
        assert state.knowledge == []

    def test_with_input(self):
        state = CognitionState(user_input="hello")
        assert state.user_input == "hello"


# ===================================================================
# Pipeline Integration Tests
# ===================================================================


class TestCognitionPipelineMinimal:
    """Pipeline with no dependencies — all stages should be skipped."""

    def test_process_empty_string(self):
        pipeline = CognitionPipeline()
        result = pipeline.process("")
        assert result.success is True
        assert len(result.stages) > 0
        # Every stage should be skipped (no dependencies injected)
        assert all(s.status == StageStatus.SKIPPED for s in result.stages)

    def test_process_returns_metrics(self):
        pipeline = CognitionPipeline()
        result = pipeline.process("test")
        assert result.metrics.stage_count > 0
        assert result.metrics.total_duration_ms >= 0
        assert result.metrics.started_at is not None
        assert result.metrics.completed_at is not None

    def test_process_tracks_path(self):
        pipeline = CognitionPipeline()
        result = pipeline.process("test")
        assert len(result.metrics.pipeline_path) > 0

    def test_process_intermediate_data(self):
        pipeline = CognitionPipeline()
        result = pipeline.process("test")
        assert "user_input" in result.intermediate_data
        assert result.intermediate_data["user_input"] == "test"


class TestCognitionPipelineWithMemory:
    """Pipeline with memory service injected."""

    def test_memory_stage_executes(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = ["memory1", "memory2"]

        pipeline = CognitionPipeline(memory_service=mock_memory)
        result = pipeline.process("test query")

        # Find memory retrieval stage
        memory_stages = [s for s in result.stages if s.stage == StageType.MEMORY_RETRIEVAL]
        assert len(memory_stages) == 1
        assert memory_stages[0].status == StageStatus.SUCCESS
        assert memory_stages[0].data["memories_count"] == 2

    def test_memory_stage_handles_no_results(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = []

        pipeline = CognitionPipeline(memory_service=mock_memory)
        result = pipeline.process("test")
        memory_stages = [s for s in result.stages if s.stage == StageType.MEMORY_RETRIEVAL]
        assert memory_stages[0].status == StageStatus.SUCCESS
        assert memory_stages[0].data["memories_count"] == 0


class TestCognitionPipelineWithKnowledge:
    """Pipeline with knowledge manager injected."""

    def test_knowledge_stage_executes(self):
        mock_knowledge = MagicMock()
        mock_knowledge.query.return_value = ["knowledge1"]

        pipeline = CognitionPipeline(knowledge_manager=mock_knowledge)
        result = pipeline.process("test query")

        knowledge_stages = [s for s in result.stages if s.stage == StageType.KNOWLEDGE_RETRIEVAL]
        assert len(knowledge_stages) == 1
        assert knowledge_stages[0].status == StageStatus.SUCCESS


class TestCognitionPipelineWithUnderstanding:
    """Pipeline with understanding engine injected."""

    def test_understanding_stage_executes(self):
        mock_engine = MagicMock()
        mock_engine.process_text.return_value = []
        mock_engine.graph.get_all_concepts.return_value = []
        mock_engine.memory.get_patterns.return_value = []

        pipeline = CognitionPipeline(understanding_engine=mock_engine)
        result = pipeline.process("test query")

        understanding_stages = [s for s in result.stages if s.stage == StageType.UNDERSTANDING]
        assert len(understanding_stages) == 1
        assert understanding_stages[0].status == StageStatus.SUCCESS


class TestCognitionPipelineWithReasoning:
    """Pipeline with reasoning components injected."""

    def test_reasoning_stage_executes(self):
        mock_controller = MagicMock()
        mock_analyzer = MagicMock()
        mock_router = MagicMock()
        mock_dispatcher = MagicMock()

        # Setup the reasoning pipeline mocks
        mock_plan = MagicMock()
        mock_plan.goal = "respond"
        mock_controller.create_plan.return_value = mock_plan

        mock_cap = MagicMock()
        mock_cap.name = "test_capability"
        mock_cap.priority = 1
        mock_cap.reason = "test"
        mock_analyzer.analyze.return_value = [mock_cap]

        mock_route = MagicMock()
        mock_route.capability = "test_capability"
        mock_route.handler_name = "test_handler"
        mock_route.strategy = "direct"
        mock_router.route.return_value = [mock_route]

        mock_result = MagicMock()
        mock_result.capability = "test_capability"
        mock_result.success = True
        mock_result.output = "done"
        mock_result.error = ""
        mock_dispatcher.dispatch.return_value = [mock_result]

        pipeline = CognitionPipeline(
            reasoning_controller=mock_controller,
            capability_analyzer=mock_analyzer,
            capability_registry=MagicMock(),
            capability_router=mock_router,
            capability_dispatcher=mock_dispatcher,
        )
        result = pipeline.process("test query")

        reasoning_stages = [s for s in result.stages if s.stage == StageType.REASONING]
        assert len(reasoning_stages) >= 1
        assert reasoning_stages[0].status == StageStatus.SUCCESS
        assert "goal" in reasoning_stages[0].data


class TestCognitionPipelineWithTools:
    """Pipeline with tool engine injected."""

    def test_tool_stages_execute(self):
        mock_controller = MagicMock()
        mock_analyzer = MagicMock()
        mock_router = MagicMock()
        mock_dispatcher = MagicMock()
        mock_tool_engine = MagicMock()

        mock_plan = MagicMock()
        mock_plan.goal = "use_tool"
        mock_controller.create_plan.return_value = mock_plan
        mock_cap = MagicMock()
        mock_cap.name = "tool_capability"
        mock_cap.priority = 1
        mock_cap.reason = "test"
        mock_analyzer.analyze.return_value = [mock_cap]
        mock_router.route.return_value = []
        mock_dispatcher.dispatch.return_value = []

        mock_tool_result = MagicMock()
        mock_tool_result.tool_name = "echo"
        mock_tool_result.success = True
        mock_tool_result.output = "hello"
        mock_tool_result.error = ""
        mock_tool_result.execution_time_ms = 5.0
        mock_tool_engine.fulfill.return_value = mock_tool_result

        pipeline = CognitionPipeline(
            reasoning_controller=mock_controller,
            capability_analyzer=mock_analyzer,
            capability_registry=MagicMock(),
            capability_router=mock_router,
            capability_dispatcher=mock_dispatcher,
            tool_engine=mock_tool_engine,
        )
        result = pipeline.process("test query")

        tool_decision = [s for s in result.stages if s.stage == StageType.TOOL_DECISION]
        tool_execution = [s for s in result.stages if s.stage == StageType.TOOL_EXECUTION]

        assert len(tool_decision) >= 1
        assert len(tool_execution) >= 1

    def test_tool_metrics_tracked(self):
        mock_controller = MagicMock()
        mock_analyzer = MagicMock()
        mock_router = MagicMock()
        mock_dispatcher = MagicMock()
        mock_tool_engine = MagicMock()

        mock_plan = MagicMock()
        mock_plan.goal = "use_tool"
        mock_controller.create_plan.return_value = mock_plan
        mock_cap = MagicMock()
        mock_cap.name = "tc"
        mock_cap.priority = 1
        mock_cap.reason = "test"
        mock_analyzer.analyze.return_value = [mock_cap]
        mock_router.route.return_value = []
        mock_dispatcher.dispatch.return_value = []

        mock_tool_result = MagicMock()
        mock_tool_result.tool_name = "echo"
        mock_tool_result.success = True
        mock_tool_result.output = "hello"
        mock_tool_result.error = ""
        mock_tool_result.execution_time_ms = 5.0
        mock_tool_engine.fulfill.return_value = mock_tool_result

        pipeline = CognitionPipeline(
            reasoning_controller=mock_controller,
            capability_analyzer=mock_analyzer,
            capability_registry=MagicMock(),
            capability_router=mock_router,
            capability_dispatcher=mock_dispatcher,
            tool_engine=mock_tool_engine,
        )
        result = pipeline.process("test")
        assert len(result.metrics.tool_usage) > 0
        assert "echo" in result.metrics.tool_usage


class TestCognitionPipelineWithAI:
    """Pipeline with AI service injected."""

    def test_ai_response_stage_executes(self):
        mock_ai = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Hello from Atlas"
        mock_ai.chat.return_value = mock_response

        pipeline = CognitionPipeline(ai_service=mock_ai)
        result = pipeline.process("hello")

        ai_stages = [s for s in result.stages if s.stage == StageType.AI_RESPONSE]
        assert len(ai_stages) == 1
        assert ai_stages[0].status == StageStatus.SUCCESS
        assert result.final_response == "Hello from Atlas"


class TestCognitionPipelineWithLearning:
    """Pipeline with learning components injected."""

    def test_learning_stage_executes(self):
        mock_learning = MagicMock()
        mock_result = MagicMock()
        mock_result.knowledge = "learned knowledge"
        mock_learning.learn.return_value = mock_result

        mock_feedback = MagicMock()
        mock_knowledge = MagicMock()

        pipeline = CognitionPipeline(
            learning_manager=mock_learning,
            knowledge_feedback=mock_feedback,
            knowledge_manager=mock_knowledge,
        )
        result = pipeline.process("test query")

        learning_stages = [s for s in result.stages if s.stage == StageType.LEARNING]
        assert len(learning_stages) == 1
        assert learning_stages[0].status == StageStatus.SUCCESS


class TestCognitionPipelineWithEvolution:
    """Pipeline with evolution observation engine injected."""

    def test_evolution_stage_executes(self):
        mock_evolution = MagicMock()
        mock_observation = MagicMock()
        mock_evolution.observe_runtime_metrics.return_value = mock_observation

        pipeline = CognitionPipeline(
            evolution_observation_engine=mock_evolution,
        )
        result = pipeline.process("test")

        evolution_stages = [s for s in result.stages if s.stage == StageType.EVOLUTION_OBSERVATION]
        assert len(evolution_stages) == 1
        assert evolution_stages[0].status == StageStatus.SUCCESS
        assert result.intermediate_data["evolution_observations_count"] >= 1


class TestCognitionPipelineFailureHandling:
    """Pipeline should handle stage failures gracefully."""

    def test_stage_failure_stops_pipeline(self):
        mock_memory = MagicMock()
        mock_memory.search.side_effect = RuntimeError("Memory unavailable")

        pipeline = CognitionPipeline(memory_service=mock_memory)
        result = pipeline.process("test")

        # The pipeline should have stopped after the memory failure
        memory_stages = [s for s in result.stages if s.stage == StageType.MEMORY_RETRIEVAL]
        assert len(memory_stages) == 1
        assert memory_stages[0].status == StageStatus.FAILED

        # Since memory retrieval failed, we shouldn't have later stages
        understanding_stages = [s for s in result.stages if s.stage == StageType.UNDERSTANDING]
        assert len(understanding_stages) == 0

    def test_pipeline_returns_success_false_on_failure(self):
        mock_memory = MagicMock()
        mock_memory.search.side_effect = RuntimeError("Memory unavailable")

        pipeline = CognitionPipeline(memory_service=mock_memory)
        result = pipeline.process("test")
        assert result.success is False


class TestCognitionPipelineStageOrder:
    """Stages should execute in the correct order."""

    def test_stage_order_is_correct(self):
        pipeline = CognitionPipeline()
        result = pipeline.process("test")

        stage_types = [s.stage for s in result.stages]
        # Verify the skip order matches the pipeline definition
        assert stage_types[0] == StageType.CONVERSATION_CONTEXT
        assert stage_types[1] == StageType.MEMORY_RETRIEVAL

    def test_pipeline_path_records_order(self):
        pipeline = CognitionPipeline()
        result = pipeline.process("test")
        assert len(result.metrics.pipeline_path) > 0


class TestCognitionPipelineBackwardCompatibility:
    """Original pipeline behavior must still work."""

    def test_original_pipeline_process_signature(self):
        """The old process() method signature must still work."""
        from atlas.cognition.engine import CognitionEngine
        original_engine = CognitionEngine()
        pipeline = CognitionPipeline(engine=original_engine)
        result = pipeline.process("hello")
        assert result is not None


class TestCognitionPipelineFullIntegration:
    """Test with all dependencies mocked."""

    def test_full_pipeline_all_dependencies(self):
        mock_memory = MagicMock()
        mock_memory.search.return_value = ["mem1"]
        mock_memory.store.return_value = None

        mock_knowledge = MagicMock()
        mock_knowledge.query.return_value = ["knowledge1"]
        mock_knowledge.remember.return_value = None

        mock_understanding = MagicMock()
        mock_understanding.process_text.return_value = []
        mock_understanding.graph.get_all_concepts.return_value = []
        mock_understanding.memory.get_patterns.return_value = []

        mock_controller = MagicMock()
        mock_analyzer = MagicMock()
        mock_router = MagicMock()
        mock_dispatcher = MagicMock()
        mock_plan = MagicMock()
        mock_plan.goal = "full_pipeline"
        mock_controller.create_plan.return_value = mock_plan
        mock_cap = MagicMock()
        mock_cap.name = "full_cap"
        mock_cap.priority = 1
        mock_cap.reason = "test"
        mock_analyzer.analyze.return_value = [mock_cap]
        mock_router.route.return_value = []
        mock_dispatcher.dispatch.return_value = []

        mock_tool = MagicMock()
        mock_tool_result = MagicMock()
        mock_tool_result.tool_name = "echo"
        mock_tool_result.success = True
        mock_tool_result.output = "out"
        mock_tool_result.error = ""
        mock_tool_result.execution_time_ms = 1.0
        mock_tool.fulfill.return_value = mock_tool_result

        mock_ai = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Full pipeline response"
        mock_ai.chat.return_value = mock_response

        mock_reflection = MagicMock()
        mock_reflection.analyze.return_value = []

        mock_recorder = MagicMock()
        mock_recorder.count = 5
        mock_recorder.recent.return_value = []

        mock_learning = MagicMock()
        mock_learning_result = MagicMock()
        mock_learning_result.knowledge = "learned"
        mock_learning.learn.return_value = mock_learning_result

        mock_feedback = MagicMock()
        mock_evolution = MagicMock()
        mock_evolution.observe_runtime_metrics.return_value = MagicMock()

        pipeline = CognitionPipeline(
            memory_service=mock_memory,
            knowledge_manager=mock_knowledge,
            understanding_engine=mock_understanding,
            reasoning_controller=mock_controller,
            capability_analyzer=mock_analyzer,
            capability_registry=MagicMock(),
            capability_router=mock_router,
            capability_dispatcher=mock_dispatcher,
            tool_engine=mock_tool,
            ai_service=mock_ai,
            reflection_engine=mock_reflection,
            reasoning_recorder=mock_recorder,
            learning_manager=mock_learning,
            knowledge_feedback=mock_feedback,
            evolution_observation_engine=mock_evolution,
        )

        result = pipeline.process("full pipeline test")
        assert result.success is True
        assert result.final_response == "Full pipeline response"
        assert result.metrics.stage_count > 0
        assert result.metrics.success_count > 0
        assert result.metrics.failed_count == 0
        assert result.intermediate_data["has_reasoning"] is True
        assert result.intermediate_data["has_tool_result"] is True