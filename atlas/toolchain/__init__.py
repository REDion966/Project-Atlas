"""Atlas Toolchain Package (Phase 18.1–18.6, Track B Batch 1–2).

Toolchain data models, skill catalog constants, skill registry, tool chain
planner, tool effectiveness tracker, safe execution, tool learning, and
lightweight wiring metadata for Capability Track B.

Pure logic: no kernel, runtime, AI, events, storage, providers, gateway,
dispatcher, or scheduler imports.
"""

from atlas.toolchain.catalog import (
    CHAIN_STRATEGY_NAMES,
    DEFAULT_CHAIN_STRATEGY,
    DEFAULT_EFFECTIVENESS,
    DEFAULT_PLAN_DEPTH,
    DEFAULT_SKILL_CATEGORY,
    EFFECTIVENESS_BASELINE_MS,
    EFFECTIVENESS_MIN_OBSERVATIONS,
    EFFECTIVENESS_SPEED_WEIGHT,
    EFFECTIVENESS_SUCCESS_WEIGHT,
    GOAL_CATEGORY_KEYWORDS,
    MAX_PLAN_DEPTH,
    MAX_PLAN_STEPS,
    SKILL_CATEGORIES,
    SKILL_KIND_NAMES,
    SKILL_STATUS_NAMES,
)
from atlas.toolchain.effectiveness import ToolEffectivenessTracker
from atlas.toolchain.executor import (
    RiskPolicy,
    SUPPORTED_STRATEGIES,
    ToolChainExecutor,
    ToolInvoker,
    UNSUPPORTED_STRATEGIES,
)
from atlas.toolchain.learner import (
    ToolLearner,
    ToolLearningRecommendation,
)
from atlas.toolchain.models import (
    ChainStrategy,
    Skill,
    SkillKind,
    SkillStatus,
    ToolChain,
    ToolChainPlan,
    ToolChainResult,
    ToolEffectivenessRecord,
    ToolEffectivenessScore,
    ToolStep,
)
from atlas.toolchain.planner import ToolChainPlanner, ToolProvider
from atlas.toolchain.registry import SkillRegistry
from atlas.toolchain.skill_author import (
    CANDIDATE_ID_PREFIX,
    LearnedSkillCandidate,
    LearnedSkillPromoter,
    PROMOTION_REQUEST_ID_PREFIX,
    SkillPromotionRequest,
    ToolSkillAuthor,
)
from atlas.toolchain.wiring import (
    register_toolchain_component,
    toolchain_component,
    toolchain_components,
)

__all__ = [
    # Models (18.1)
    "ChainStrategy",
    "Skill",
    "SkillKind",
    "SkillStatus",
    "ToolChain",
    "ToolChainPlan",
    "ToolChainResult",
    "ToolEffectivenessRecord",
    "ToolEffectivenessScore",
    "ToolStep",
    # Catalog (18.2)
    "CHAIN_STRATEGY_NAMES",
    "DEFAULT_CHAIN_STRATEGY",
    "DEFAULT_EFFECTIVENESS",
    "DEFAULT_PLAN_DEPTH",
    "DEFAULT_SKILL_CATEGORY",
    "EFFECTIVENESS_BASELINE_MS",
    "EFFECTIVENESS_MIN_OBSERVATIONS",
    "EFFECTIVENESS_SPEED_WEIGHT",
    "EFFECTIVENESS_SUCCESS_WEIGHT",
    "GOAL_CATEGORY_KEYWORDS",
    "MAX_PLAN_DEPTH",
    "MAX_PLAN_STEPS",
    "SKILL_CATEGORIES",
    "SKILL_KIND_NAMES",
    "SKILL_STATUS_NAMES",
    # Registry (18.3)
    "SkillRegistry",
    # Author / Promotion (22.3)
    "CANDIDATE_ID_PREFIX",
    "LearnedSkillCandidate",
    "LearnedSkillPromoter",
    "PROMOTION_REQUEST_ID_PREFIX",
    "SkillPromotionRequest",
    "ToolSkillAuthor",
    # Planner (18.4)
    "ToolChainPlanner",
    "ToolProvider",
    # Effectiveness tracker
    "ToolEffectivenessTracker",
    # Executor (18.5)
    "RiskPolicy",
    "SUPPORTED_STRATEGIES",
    "ToolChainExecutor",
    "ToolInvoker",
    "UNSUPPORTED_STRATEGIES",
    # Learner (18.6)
    "ToolLearner",
    "ToolLearningRecommendation",
    # Wiring
    "register_toolchain_component",
    "toolchain_component",
    "toolchain_components",
]
