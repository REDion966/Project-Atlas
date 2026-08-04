"""Atlas Toolchain Package (Phase 18.1–18.4, Track B Batch 1).

Toolchain data models, skill catalog constants, skill registry, tool chain
planner, tool effectiveness tracker, and lightweight wiring metadata for
Capability Track B.

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
    # Planner (18.4)
    "ToolChainPlanner",
    "ToolProvider",
    # Effectiveness tracker
    "ToolEffectivenessTracker",
    # Wiring
    "register_toolchain_component",
    "toolchain_component",
    "toolchain_components",
]
