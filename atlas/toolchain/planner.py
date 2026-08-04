"""Atlas Toolchain — Tool Chain Planner (Phase 18.4).

Deterministically decomposes a goal into a :class:`ToolChainPlan`: an
ordered sequence of :class:`ToolStep` objects referencing registered tools,
plus an execution strategy and depth bound.

Pure logic. No AI. No storage. No gateway. No dispatcher. The planner is
stateless — identical inputs always produce identical plans (timestamps
aside, the plan content is byte-for-byte stable).

Planning strategy:
  1. Resolve the goal's category from keywords (or accept an explicit hint).
  2. Select candidate tools from the injected :class:`ToolRegistry`-shaped
     provider (protocol-injected; the planner imports no registry class).
  3. Rank candidates by goal keyword relevance (deterministic).
  4. Emit one :class:`ToolStep` per selected tool, up to ``max_steps``.
  5. Choose a chain strategy from goal markers (fallback / sequential).
  6. Compute a depth bound from goal complexity.

The planner never executes tools — it only produces a plan artifact.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol, runtime_checkable

from atlas.toolchain.catalog import (
    DEFAULT_CHAIN_STRATEGY,
    DEFAULT_PLAN_DEPTH,
    DEFAULT_SKILL_CATEGORY,
    GOAL_CATEGORY_KEYWORDS,
    MAX_PLAN_DEPTH,
    MAX_PLAN_STEPS,
    MIN_GOAL_LENGTH,
    PLAN_ID_PREFIX,
    STEP_ID_PREFIX,
)
from atlas.toolchain.models import ToolChainPlan, ToolStep


# ---------------------------------------------------------------------------
# Protocol — tool provider (dependency injection)
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolProvider(Protocol):
    """Read-only tool surface the planner consults.

    Decouples the planner from :class:`~atlas.tools.registry.ToolRegistry`
    so the planner stays pure and testable with fakes. Any object exposing
    ``list()`` returning a list of tool-like objects with ``name``,
    ``description``, ``category``, and ``tags`` attributes satisfies this
    protocol.
    """

    def list(self) -> list: ...


# ---------------------------------------------------------------------------
# Deterministic constants
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "and",
        "or",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "how",
        "what",
        "when",
        "who",
        "which",
        "does",
        "do",
        "can",
        "we",
        "us",
        "our",
        "should",
        "must",
        "its",
        "it",
        "this",
        "that",
        "then",
        "into",
        "from",
    }
)

# Goal markers that select a fallback strategy (try alternatives in order).
_FALLBACK_MARKERS: frozenset[str] = frozenset(
    {"fallback", "try", "attempt", "alternative", "or"}
)

# Goal markers that select a parallel strategy (independent steps).
_PARALLEL_MARKERS: frozenset[str] = frozenset(
    {"parallel", "concurrent", "simultaneous", "batch"}
)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class ToolChainPlanner:
    """Stateless, deterministic tool-chain planner.

    The planner is constructed with a :class:`ToolProvider` (protocol-
    injected) and produces :class:`ToolChainPlan` artifacts for goals. It
    never executes tools and never mutates any state.
    """

    def __init__(self, tool_provider: ToolProvider | None = None) -> None:
        """Initialise the planner with an optional tool provider.

        Args:
            tool_provider: A :class:`ToolProvider`-shaped object. If
                ``None``, the planner produces empty plans (no tools to
                reference). This keeps the planner usable in tests and
                in environments where the tool registry is not yet wired.
        """
        self._provider: ToolProvider | None = tool_provider

    @property
    def has_provider(self) -> bool:
        """True when a tool provider is wired."""
        return self._provider is not None

    # ------------------------------------------------------------------
    # Public planning
    # ------------------------------------------------------------------

    def plan(
        self,
        goal: str,
        *,
        category: str = "",
        max_steps: int = MAX_PLAN_STEPS,
        max_depth: int | None = None,
    ) -> ToolChainPlan:
        """Build a :class:`ToolChainPlan` for the given goal.

        Deterministic: the same goal + provider state always yields the
        same plan content (the ``created_at`` timestamp varies, but the
        steps, strategy, and depth are stable).

        Args:
            goal: The high-level goal to decompose.
            category: Optional explicit category hint. When empty, the
                planner infers one from goal keywords.
            max_steps: Maximum number of steps to emit.
            max_depth: Optional explicit depth bound. When ``None``, the
                planner computes one from goal complexity.

        Returns:
            A :class:`ToolChainPlan`. If the goal is empty or no tools
            match, the plan has zero steps (``is_empty == True``).
        """
        normalized_goal: str = (goal or "").strip()
        if len(normalized_goal) < MIN_GOAL_LENGTH:
            return self._empty_plan(goal or "")

        resolved_category: str = category or self.infer_category(normalized_goal)
        candidates: list = self._candidate_tools(resolved_category)
        ranked: list = self.rank_tools(normalized_goal, candidates)
        limited: list = ranked[: max(0, min(max_steps, MAX_PLAN_STEPS))]

        steps: tuple[ToolStep, ...] = tuple(
            self._build_step(tool, index)
            for index, tool in enumerate(limited)
        )

        strategy: str = self.infer_strategy(normalized_goal)
        depth: int = max_depth if max_depth is not None else self.infer_depth(normalized_goal)

        return ToolChainPlan(
            plan_id=self._plan_id(normalized_goal),
            goal=goal or "",
            steps=steps,
            strategy=strategy,
            max_depth=depth,
            metadata={
                "category": resolved_category,
                "candidate_count": len(candidates),
                "ranked_count": len(ranked),
            },
        )

    # ------------------------------------------------------------------
    # Decomposition steps (public for testability)
    # ------------------------------------------------------------------

    def infer_category(self, goal: str) -> str:
        """Infer a skill category from goal keywords.

        Args:
            goal: The goal string.

        Returns:
            A category name from :data:`SKILL_CATEGORIES`, or
            :data:`DEFAULT_SKILL_CATEGORY` when no keyword matches.
        """
        normalized: str = goal.lower()
        tokens: list[str] = _tokenize(normalized)
        for token in tokens:
            if token in GOAL_CATEGORY_KEYWORDS:
                return GOAL_CATEGORY_KEYWORDS[token]
        return DEFAULT_SKILL_CATEGORY

    def infer_strategy(self, goal: str) -> str:
        """Infer a chain strategy from goal markers.

        Args:
            goal: The goal string.

        Returns:
            A strategy name from :data:`CHAIN_STRATEGY_NAMES`.
        """
        normalized: str = goal.lower()
        tokens: set[str] = set(_tokenize(normalized))
        if tokens & _FALLBACK_MARKERS:
            return "fallback"
        if tokens & _PARALLEL_MARKERS:
            return "parallel"
        return DEFAULT_CHAIN_STRATEGY

    def infer_depth(self, goal: str) -> int:
        """Infer a recursion/retry depth bound from goal complexity.

        Args:
            goal: The goal string.

        Returns:
            An integer depth between :data:`DEFAULT_PLAN_DEPTH` and
            :data:`MAX_PLAN_DEPTH`.
        """
        token_count: int = len((goal or "").split())
        if token_count <= 8:
            return DEFAULT_PLAN_DEPTH
        if token_count <= 24:
            return 2
        return MAX_PLAN_DEPTH

    def rank_tools(self, goal: str, tools: list) -> list:
        """Rank tools by keyword relevance to the goal.

        Scoring (deterministic):
        - +2 if the goal contains the tool name.
        - +1 if the goal contains any tag of the tool.
        - +1 if the goal contains any word from the tool description.
        Ties are broken by tool name (alphabetical).

        Args:
            goal: The goal string.
            tools: A list of tool-like objects (must have ``name``,
                ``description``, ``tags`` attributes).

        Returns:
            Tools sorted by relevance score (highest first).
        """
        if not goal or not tools:
            return list(tools)

        goal_lower: str = goal.lower()
        goal_words: set[str] = set(goal_lower.split())

        scored: list[tuple[int, str, object]] = []
        for tool in tools:
            score: int = 0
            name: str = getattr(tool, "name", "")
            description: str = getattr(tool, "description", "")
            tags: list[str] = list(getattr(tool, "tags", []))

            if name and name.lower() in goal_lower:
                score += 2
            for tag in tags:
                if tag.lower() in goal_lower:
                    score += 1
            desc_words: set[str] = set(description.lower().split())
            if goal_words & desc_words:
                score += 1

            scored.append((score, name, tool))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [item[2] for item in scored]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _candidate_tools(self, category: str) -> list:
        """Return tools from the provider, optionally filtered by category."""
        provider: ToolProvider | None = self._provider
        if provider is None:
            return []
        try:
            available: list = provider.list()
        except Exception:
            return []
        if not category:
            return list(available)
        filtered: list = [
            t for t in available if getattr(t, "category", "") == category
        ]
        return filtered if filtered else list(available)

    @staticmethod
    def _build_step(tool: object, index: int) -> ToolStep:
        """Build a :class:`ToolStep` from a tool-like object."""
        name: str = getattr(tool, "name", f"tool_{index}")
        return ToolStep(
            step_id=f"{STEP_ID_PREFIX}:{index:04d}",
            tool_name=name,
            description=getattr(tool, "description", ""),
        )

    @staticmethod
    def _plan_id(goal: str) -> str:
        """Deterministic plan id from the goal string (sha256[:16])."""
        digest: str = hashlib.sha256(goal.encode("utf-8")).hexdigest()[:16]
        return f"{PLAN_ID_PREFIX}::{digest}"

    @staticmethod
    def _empty_plan(goal: str) -> ToolChainPlan:
        """Build an empty plan for trivial / empty goals."""
        return ToolChainPlan(
            plan_id=f"{PLAN_ID_PREFIX}::empty",
            goal=goal,
            steps=(),
            strategy=DEFAULT_CHAIN_STRATEGY,
            max_depth=DEFAULT_PLAN_DEPTH,
            metadata={"empty": True},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tokenize(value: str) -> list[str]:
    """Split a string into lowercase alphanumeric tokens."""
    return [t for t in re.split(r"[^a-zA-Z0-9_]+", value) if t]