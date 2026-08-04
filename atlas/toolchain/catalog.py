"""Atlas Toolchain — Catalog & Constants (Phase 18.2).

Shared, pure constants describing the skill/toolchain ecosystem: skill
categories, tool-kind hints, chain-strategy names, and goal→category
keyword mappings. Imported by both the :class:`SkillRegistry` and the
:class:`ToolChainPlanner` so skill discovery and chain planning can never
drift apart.

No runtime dependencies beyond the standard library and the pure
``atlas.toolchain.models`` enums.
"""

from __future__ import annotations

from atlas.toolchain.models import ChainStrategy, SkillKind, SkillStatus


# ---------------------------------------------------------------------------
# Skill categories (functional grouping)
# ---------------------------------------------------------------------------

#: Categories a skill may belong to. Mirrors the ``Tool.category`` vocabulary
#: used by ``atlas.tools`` so builtin-skill wrapping stays consistent.
SKILL_CATEGORIES: frozenset[str] = frozenset(
    {
        "file",
        "search",
        "code",
        "network",
        "system",
        "utility",
        "analysis",
        "research",
        "memory",
        "knowledge",
        "planning",
        "reasoning",
    }
)

#: Default category when a skill does not declare one.
DEFAULT_SKILL_CATEGORY: str = "utility"


# ---------------------------------------------------------------------------
# Chain strategy names (stable string identifiers)
# ---------------------------------------------------------------------------

#: Stable string names for :class:`ChainStrategy` members, used in
#: serialized plans/chains and by the planner.
CHAIN_STRATEGY_NAMES: frozenset[str] = frozenset(
    {
        ChainStrategy.SEQUENTIAL.name.lower(),
        ChainStrategy.PARALLEL.name.lower(),
        ChainStrategy.FALLBACK.name.lower(),
        ChainStrategy.CONDITIONAL.name.lower(),
    }
)

#: Default chain strategy name.
DEFAULT_CHAIN_STRATEGY: str = ChainStrategy.SEQUENTIAL.name.lower()


# ---------------------------------------------------------------------------
# Skill kind / status names (stable string identifiers)
# ---------------------------------------------------------------------------

SKILL_KIND_NAMES: frozenset[str] = frozenset(
    {
        SkillKind.BUILTIN.name,
        SkillKind.COMPOSED.name,
        SkillKind.LEARNED.name,
    }
)

SKILL_STATUS_NAMES: frozenset[str] = frozenset(
    {
        SkillStatus.DRAFT.name,
        SkillStatus.ACTIVE.name,
        SkillStatus.DEPRECATED.name,
    }
)


# ---------------------------------------------------------------------------
# Goal → category keyword mapping (deterministic planning aid)
# ---------------------------------------------------------------------------

#: Maps goal keywords (lowercased) to the most likely skill category. The
#: planner consults this map when no explicit category is provided.
GOAL_CATEGORY_KEYWORDS: dict[str, str] = {
    "file": "file",
    "read": "file",
    "write": "file",
    "open": "file",
    "save": "file",
    "search": "search",
    "find": "search",
    "query": "search",
    "lookup": "search",
    "code": "code",
    "function": "code",
    "class": "code",
    "refactor": "code",
    "network": "network",
    "http": "network",
    "request": "network",
    "api": "network",
    "system": "system",
    "process": "system",
    "shell": "system",
    "command": "system",
    "analyze": "analysis",
    "analysis": "analysis",
    "report": "analysis",
    "statistics": "analysis",
    "research": "research",
    "investigate": "research",
    "study": "research",
    "memory": "memory",
    "recall": "memory",
    "remember": "memory",
    "knowledge": "knowledge",
    "learn": "knowledge",
    "plan": "planning",
    "decompose": "planning",
    "schedule": "planning",
    "reason": "reasoning",
    "infer": "reasoning",
    "deduce": "reasoning",
}


# ---------------------------------------------------------------------------
# Planning defaults
# ---------------------------------------------------------------------------

#: Maximum number of steps a planner will emit for a single goal.
MAX_PLAN_STEPS: int = 8

#: Default maximum recursion / retry depth for a plan.
DEFAULT_PLAN_DEPTH: int = 1

#: Maximum recursion / retry depth for a plan.
MAX_PLAN_DEPTH: int = 3

#: Minimum goal length (characters) for the planner to attempt decomposition.
MIN_GOAL_LENGTH: int = 1


# ---------------------------------------------------------------------------
# Effectiveness defaults
# ---------------------------------------------------------------------------

#: Weight applied to success rate when computing effectiveness.
EFFECTIVENESS_SUCCESS_WEIGHT: float = 0.7

#: Weight applied to speed (inverse of execution time) when computing
#: effectiveness. The two weights sum to 1.0.
EFFECTIVENESS_SPEED_WEIGHT: float = 0.3

#: Baseline execution time (ms) used to normalize speed into 0.0–1.0.
EFFECTIVENESS_BASELINE_MS: float = 1000.0

#: Minimum number of observations before an effectiveness score is
#: considered statistically meaningful (below this, effectiveness is
#: reported but flagged as low-confidence via metadata).
EFFECTIVENESS_MIN_OBSERVATIONS: int = 3

#: Default effectiveness score for a tool with no observations.
DEFAULT_EFFECTIVENESS: float = 0.5


# ---------------------------------------------------------------------------
# ID prefixes
# ---------------------------------------------------------------------------

SKILL_ID_PREFIX: str = "skill"
CHAIN_ID_PREFIX: str = "chain"
PLAN_ID_PREFIX: str = "plan"
STEP_ID_PREFIX: str = "step"
RECORD_ID_PREFIX: str = "eff"