"""Phase 18.2 — Toolchain catalog constants tests."""

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
    MIN_GOAL_LENGTH,
    SKILL_CATEGORIES,
    SKILL_KIND_NAMES,
    SKILL_STATUS_NAMES,
)
from atlas.toolchain.models import ChainStrategy, SkillKind, SkillStatus


class TestSkillCategories:
    def test_categories_is_frozenset(self):
        assert isinstance(SKILL_CATEGORIES, frozenset)

    def test_contains_expected_categories(self):
        for cat in ("file", "search", "code", "network", "system", "utility"):
            assert cat in SKILL_CATEGORIES

    def test_default_category_in_set(self):
        assert DEFAULT_SKILL_CATEGORY in SKILL_CATEGORIES

    def test_default_category_is_utility(self):
        assert DEFAULT_SKILL_CATEGORY == "utility"


class TestChainStrategyNames:
    def test_names_is_frozenset(self):
        assert isinstance(CHAIN_STRATEGY_NAMES, frozenset)

    def test_contains_all_strategy_lower_names(self):
        for strategy in ChainStrategy:
            assert strategy.name.lower() in CHAIN_STRATEGY_NAMES

    def test_default_strategy_in_set(self):
        assert DEFAULT_CHAIN_STRATEGY in CHAIN_STRATEGY_NAMES

    def test_default_strategy_is_sequential(self):
        assert DEFAULT_CHAIN_STRATEGY == "sequential"


class TestSkillKindNames:
    def test_contains_all_kind_names(self):
        for kind in SkillKind:
            assert kind.name in SKILL_KIND_NAMES


class TestSkillStatusNames:
    def test_contains_all_status_names(self):
        for status in SkillStatus:
            assert status.name in SKILL_STATUS_NAMES


class TestGoalCategoryKeywords:
    def test_is_dict(self):
        assert isinstance(GOAL_CATEGORY_KEYWORDS, dict)

    def test_file_keywords(self):
        for kw in ("file", "read", "write", "open", "save"):
            assert GOAL_CATEGORY_KEYWORDS[kw] == "file"

    def test_search_keywords(self):
        for kw in ("search", "find", "query", "lookup"):
            assert GOAL_CATEGORY_KEYWORDS[kw] == "search"

    def test_all_values_in_categories(self):
        for value in GOAL_CATEGORY_KEYWORDS.values():
            assert value in SKILL_CATEGORIES


class TestPlanningDefaults:
    def test_max_plan_steps_positive(self):
        assert MAX_PLAN_STEPS > 0

    def test_default_plan_depth_positive(self):
        assert DEFAULT_PLAN_DEPTH > 0

    def test_max_plan_depth_geq_default(self):
        assert MAX_PLAN_DEPTH >= DEFAULT_PLAN_DEPTH

    def test_min_goal_length_positive(self):
        assert MIN_GOAL_LENGTH >= 1


class TestEffectivenessDefaults:
    def test_weights_sum_to_one(self):
        assert (
            EFFECTIVENESS_SUCCESS_WEIGHT + EFFECTIVENESS_SPEED_WEIGHT == 1.0
        )

    def test_baseline_positive(self):
        assert EFFECTIVENESS_BASELINE_MS > 0

    def test_min_observations_positive(self):
        assert EFFECTIVENESS_MIN_OBSERVATIONS > 0

    def test_default_effectiveness_in_range(self):
        assert 0.0 <= DEFAULT_EFFECTIVENESS <= 1.0