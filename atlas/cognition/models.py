"""
Atlas Cognition Pipeline Models

Data models for the integrated cognitive pipeline.
Phase 7.2 — Integrated Cognitive Pipeline.
Phase 7.5 — Added WORLD_MODEL stage and learning_engine_result field.
Phase 8.3 — Added GOAL_INTELLIGENCE stage.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class StageType(Enum):
    """Every stage in the cognitive pipeline."""

    CONVERSATION_CONTEXT = auto()
    MEMORY_RETRIEVAL = auto()
    KNOWLEDGE_RETRIEVAL = auto()
    UNDERSTANDING = auto()
    WORLD_MODEL = auto()
    REASONING = auto()
    PLANNING = auto()
    TOOL_DECISION = auto()
    TOOL_EXECUTION = auto()
    AI_RESPONSE = auto()
    REFLECTION = auto()
    LEARNING = auto()
    EVOLUTION_OBSERVATION = auto()
    GOAL_INTELLIGENCE = auto()
    MEMORY_STORAGE = auto()


class StageStatus(Enum):
    """Status of a pipeline stage execution."""

    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    SKIPPED = auto()


@dataclass(slots=True)
class StageResult:
    """
    Result of a single pipeline stage execution.

    Attributes:
        stage: The stage type.
        status: Execution status.
        duration_ms: Execution duration in milliseconds.
        data: Structured output data produced by the stage.
        error: Error message if the stage failed.
        confidence: Optional confidence score (0.0 to 1.0).
    """

    stage: StageType
    status: StageStatus
    duration_ms: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    confidence: float = 0.0


@dataclass(slots=True)
class PipelineMetrics:
    """
    Execution metrics for the full pipeline.

    Attributes:
        total_duration_ms: Total pipeline execution time.
        stage_count: Number of stages executed.
        success_count: Number of stages that succeeded.
        failed_count: Number of stages that failed.
        skipped_count: Number of stages skipped.
        tool_usage: Names of tools executed (if any).
        memory_queries: Number of memory queries made.
        understanding_insights: Number of understanding insights generated.
        pipeline_path: Ordered list of stage types that executed.
        started_at: When pipeline execution began.
        completed_at: When pipeline execution completed.
    """

    total_duration_ms: float = 0.0
    stage_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    tool_usage: list[str] = field(default_factory=list)
    memory_queries: int = 0
    understanding_insights: int = 0
    pipeline_path: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None


@dataclass(slots=True)
class PipelineResult:
    """
    The complete result of a cognitive pipeline execution.

    Attributes:
        success: True if the pipeline completed without critical failure.
        final_response: The final response text (if AI response stage ran).
        stages: Ordered list of stage results.
        metrics: Pipeline execution metrics.
        intermediate_data: Accumulated data from all stages.
        error: Top-level error message if the pipeline failed critically.
    """

    success: bool
    final_response: str = ""
    stages: list[StageResult] = field(default_factory=list)
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)
    intermediate_data: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(slots=True)
class CognitionState:
    """
    Mutable state passed through the pipeline stages.

    Each stage reads from and writes to this state. This is the
    structured data exchange mechanism that replaces raw text
    passing between stages.

    Attributes:
        user_input: The original user input text.
        conversation_context: Context from conversation history.
        memories: Retrieved memories.
        knowledge: Retrieved knowledge.
        understanding_insights: Insights from the Understanding Engine.
        concepts: Extracted concepts.
        patterns: Detected patterns.
        world_model_state: State snapshot from the World Model Engine.
        reasoning_result: Output from the reasoning pipeline.
        planning_result: Output from the planning engine.
        tool_request: Tool request (if tools are needed).
        tool_result: Tool execution result (if tools were used).
        ai_response: Response from the AI provider.
        reflection_suggestions: Reflection analysis results.
        learning_result: Legacy learning feedback result.
        learning_engine_result: Structured learning engine result.
        evolution_observations: Observations for the evolution subsystem.
        goal_intelligence_report: Latest goal intelligence report.
        metadata: Additional context data.
    """

    user_input: str = ""
    conversation_context: dict[str, Any] = field(default_factory=dict)
    memories: list[Any] = field(default_factory=list)
    knowledge: list[Any] = field(default_factory=list)
    understanding_insights: list[Any] = field(default_factory=list)
    concepts: list[Any] = field(default_factory=list)
    patterns: list[Any] = field(default_factory=list)
    world_model_state: dict[str, Any] = field(default_factory=dict)
    reasoning_result: dict[str, Any] = field(default_factory=dict)
    planning_result: dict[str, Any] = field(default_factory=dict)
    tool_request: Any | None = None
    tool_result: dict[str, Any] = field(default_factory=dict)
    ai_response: str = ""
    reflection_suggestions: list[Any] = field(default_factory=list)
    learning_result: dict[str, Any] = field(default_factory=dict)
    learning_engine_result: dict[str, Any] = field(default_factory=dict)
    evolution_observations: list[Any] = field(default_factory=list)
    goal_intelligence_report: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)