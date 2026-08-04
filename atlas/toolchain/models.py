"""Atlas Toolchain — Toolchain Data Models (Phase 18.1).

Pure data containers for the Track B tool-ecosystem layer. Every model is a
frozen, slotted dataclass with a ``to_dict()`` serializer — mirroring the
Phase 17.1 research-models contract so storage adapters and capability
handlers can serialize toolchain artifacts without touching business logic.

No infrastructure dependencies. No AI. No storage. No gateway. No kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SkillKind(Enum):
    """How a skill is realized.

    BUILTIN  — wraps a single existing tool from ``atlas.tools``.
    COMPOSED — wraps an ordered :class:`ToolChain` of multiple tools.
    LEARNED  — a composed skill whose chain was tuned by the
        :class:`ToolEffectivenessTracker` (effectiveness-optimized).
    """

    BUILTIN = auto()
    COMPOSED = auto()
    LEARNED = auto()


class SkillStatus(Enum):
    """Lifecycle state of a registered skill.

    DRAFT     — created but not yet activated.
    ACTIVE    — available for selection and execution.
    DEPRECATED — superseded or retired; kept for audit only.
    """

    DRAFT = auto()
    ACTIVE = auto()
    DEPRECATED = auto()


class ChainStrategy(Enum):
    """Execution strategy for a :class:`ToolChain`.

    SEQUENTIAL — steps run one-after-another in order.
    PARALLEL   — independent steps run concurrently (planning only;
        execution semantics are owned by a future executor).
    FALLBACK   — steps are tried in order; first success wins.
    CONDITIONAL — steps are selected based on prior step output
        (planning hint only; deterministic planning emits the full
        candidate list).
    """

    SEQUENTIAL = auto()
    PARALLEL = auto()
    FALLBACK = auto()
    CONDITIONAL = auto()


# ---------------------------------------------------------------------------
# Step / Chain
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolStep:
    """A single step within a :class:`ToolChain`.

    Attributes:
        step_id: Stable identifier unique within the chain.
        tool_name: Name of the registered tool to invoke.
        parameters: Parameters to pass to the tool handler.
        depends_on: Step IDs that must complete before this step.
        description: Human-readable explanation of the step's purpose.
    """

    step_id: str
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "parameters": dict(self.parameters),
            "depends_on": tuple(self.depends_on),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ToolChain:
    """An ordered sequence of :class:`ToolStep` objects realizing a goal.

    Attributes:
        chain_id: Stable unique identifier.
        goal: The high-level goal the chain accomplishes.
        steps: Ordered tuple of :class:`ToolStep`.
        strategy: Execution strategy (see :class:`ChainStrategy`).
        created_at: When the chain was created.
        metadata: Additional context.
    """

    chain_id: str
    goal: str
    steps: tuple[ToolStep, ...] = ()
    strategy: str = "sequential"
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested steps become dicts)."""
        return {
            "chain_id": self.chain_id,
            "goal": self.goal,
            "steps": tuple(s.to_dict() for s in self.steps),
            "strategy": self.strategy,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @property
    def step_count(self) -> int:
        """Number of steps in the chain."""
        return len(self.steps)

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Ordered tuple of tool names referenced by the chain."""
        return tuple(s.tool_name for s in self.steps)


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Skill:
    """A named, reusable capability built on tools or tool chains.

    A BUILTIN skill wraps a single tool (``tool_name`` set, ``chain`` is
    ``None``). A COMPOSED or LEARNED skill wraps a :class:`ToolChain`
    (``chain`` set, ``tool_name`` may be empty).

    Attributes:
        skill_id: Stable unique identifier.
        name: Human-readable skill name.
        description: What the skill does.
        kind: How the skill is realized (see :class:`SkillKind`).
        category: Functional category (e.g. "file", "search", "analysis").
        tool_name: For BUILTIN skills, the wrapped tool's name.
        chain: For COMPOSED/LEARNED skills, the wrapped :class:`ToolChain`.
        tags: Tags for discovery and matching.
        status: Lifecycle state (see :class:`SkillStatus`).
        created_at: When the skill was created.
        metadata: Additional context.
    """

    skill_id: str
    name: str
    description: str = ""
    kind: SkillKind = SkillKind.BUILTIN
    category: str = "utility"
    tool_name: str = ""
    chain: ToolChain | None = None
    tags: tuple[str, ...] = ()
    status: SkillStatus = SkillStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested chain becomes a dict)."""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "kind": self.kind.name,
            "category": self.category,
            "tool_name": self.tool_name,
            "chain": self.chain.to_dict() if self.chain is not None else None,
            "tags": tuple(self.tags),
            "status": self.status.name,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @property
    def is_builtin(self) -> bool:
        """True when the skill wraps a single tool."""
        return self.kind == SkillKind.BUILTIN

    @property
    def is_composed(self) -> bool:
        """True when the skill wraps a tool chain."""
        return self.kind in (SkillKind.COMPOSED, SkillKind.LEARNED)

    @property
    def is_active(self) -> bool:
        """True when the skill is available for selection."""
        return self.status == SkillStatus.ACTIVE


# ---------------------------------------------------------------------------
# Plan / Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolChainPlan:
    """Deterministic decomposition of a goal into a tool chain plan.

    Produced by :class:`~atlas.toolchain.planner.ToolChainPlanner`. The plan
    is a blueprint — it describes *what* tools to run in *what* order but
    does not execute them.

    Attributes:
        plan_id: Stable identifier (typically ``plan::{goal_hash}``).
        goal: The original goal string.
        steps: Ordered tuple of :class:`ToolStep`.
        strategy: Execution strategy name.
        max_depth: Maximum recursion / retry depth.
        created_at: When the plan was created.
        metadata: Additional planning context.
    """

    plan_id: str
    goal: str
    steps: tuple[ToolStep, ...] = ()
    strategy: str = "sequential"
    max_depth: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested steps become dicts)."""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": tuple(s.to_dict() for s in self.steps),
            "strategy": self.strategy,
            "max_depth": self.max_depth,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @property
    def step_count(self) -> int:
        """Number of steps in the plan."""
        return len(self.steps)

    @property
    def is_empty(self) -> bool:
        """True when the plan has no steps."""
        return len(self.steps) == 0


@dataclass(frozen=True, slots=True)
class ToolChainResult:
    """Outcome of executing a :class:`ToolChain` or :class:`ToolChainPlan`.

    Attributes:
        chain_id: Identifier of the chain that was executed.
        success: Whether the overall chain succeeded.
        step_results: Per-step result summaries (ordered).
        error: Error message if the chain failed.
        execution_time_ms: Total execution time in milliseconds.
        metadata: Additional execution context.
    """

    chain_id: str
    success: bool = False
    step_results: tuple[dict[str, Any], ...] = ()
    error: str = ""
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "chain_id": self.chain_id,
            "success": self.success,
            "step_results": tuple(self.step_results),
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Effectiveness
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolEffectivenessRecord:
    """A single observation of tool execution effectiveness.

    Accumulated by :class:`~atlas.toolchain.effectiveness.ToolEffectivenessTracker`
    to compute per-tool effectiveness scores.

    Attributes:
        record_id: Stable unique identifier.
        tool_name: Name of the tool that was executed.
        success: Whether the tool execution succeeded.
        execution_time_ms: Execution time in milliseconds.
        context_hash: Stable hash of the execution context (for grouping).
        skill_id: Optional skill that triggered the execution.
        recorded_at: When the observation was recorded.
        metadata: Additional observation context.
    """

    record_id: str
    tool_name: str
    success: bool = False
    execution_time_ms: float = 0.0
    context_hash: str = ""
    skill_id: str = ""
    recorded_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "record_id": self.record_id,
            "tool_name": self.tool_name,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
            "context_hash": self.context_hash,
            "skill_id": self.skill_id,
            "recorded_at": self.recorded_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ToolEffectivenessScore:
    """Aggregated effectiveness score for a single tool.

    Attributes:
        tool_name: The tool being scored.
        total_observations: Total number of recorded observations.
        success_count: Number of successful executions.
        failure_count: Number of failed executions.
        success_rate: success_count / total_observations (0.0–1.0).
        avg_execution_time_ms: Average execution time in milliseconds.
        effectiveness: Weighted effectiveness score (0.0–1.0).
        last_observed_at: When the most recent observation was recorded.
    """

    tool_name: str
    total_observations: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.0
    avg_execution_time_ms: float = 0.0
    effectiveness: float = 0.0
    last_observed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "tool_name": self.tool_name,
            "total_observations": self.total_observations,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
            "avg_execution_time_ms": self.avg_execution_time_ms,
            "effectiveness": self.effectiveness,
            "last_observed_at": (
                self.last_observed_at.isoformat()
                if self.last_observed_at is not None
                else None
            ),
        }