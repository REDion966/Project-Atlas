"""Track C — Long-Term Learning catalog constants tests (Batch 1)."""

from atlas.longterm.catalog import (
    CONSOLIDATION_ID_PREFIX,
    CONSOLIDATION_OPERATIONS,
    CONSOLIDATION_STATUS_NAMES,
    DEFAULT_CONSOLIDATION_ENABLED,
    DEFAULT_CONSOLIDATION_OPERATION,
    DEFAULT_CONSOLIDATION_THRESHOLD,
    DEFAULT_EPISODE_CATEGORY,
    DEFAULT_EPISODE_TTL_DAYS,
    DEFAULT_MAX_EPISODES,
    DEFAULT_MAX_PROCEDURES,
    DEFAULT_MIN_IMPORTANCE,
    DEFAULT_PROCEDURE_CATEGORY,
    DEFAULT_PROCEDURE_TTL_DAYS,
    EPISODE_CATEGORIES,
    EPISODE_ID_PREFIX,
    EPISODE_KIND_NAMES,
    EVENT_ID_PREFIX,
    PROCEDURE_CATEGORIES,
    PROCEDURE_ID_PREFIX,
    PROCEDURE_KIND_NAMES,
    STEP_ID_PREFIX,
)
from atlas.longterm.models import (
    ConsolidationStatus,
    EpisodeKind,
    ProcedureKind,
)


class TestEpisodeCategories:
    def test_categories_is_frozenset(self):
        assert isinstance(EPISODE_CATEGORIES, frozenset)

    def test_contains_expected_categories(self):
        for cat in ("pipeline", "session", "task", "conversation", "system"):
            assert cat in EPISODE_CATEGORIES

    def test_default_category_in_set(self):
        assert DEFAULT_EPISODE_CATEGORY in EPISODE_CATEGORIES

    def test_default_category_is_pipeline(self):
        assert DEFAULT_EPISODE_CATEGORY == "pipeline"


class TestProcedureCategories:
    def test_categories_is_frozenset(self):
        assert isinstance(PROCEDURE_CATEGORIES, frozenset)

    def test_contains_expected_categories(self):
        for cat in ("analysis", "research", "tool", "utility", "system"):
            assert cat in PROCEDURE_CATEGORIES

    def test_default_category_in_set(self):
        assert DEFAULT_PROCEDURE_CATEGORY in PROCEDURE_CATEGORIES

    def test_default_category_is_utility(self):
        assert DEFAULT_PROCEDURE_CATEGORY == "utility"


class TestEpisodeKindNames:
    def test_contains_all_kind_names(self):
        for kind in EpisodeKind:
            assert kind.name in EPISODE_KIND_NAMES


class TestProcedureKindNames:
    def test_contains_all_kind_names(self):
        for kind in ProcedureKind:
            assert kind.name in PROCEDURE_KIND_NAMES


class TestConsolidationStatusNames:
    def test_contains_all_status_names(self):
        for status in ConsolidationStatus:
            assert status.name in CONSOLIDATION_STATUS_NAMES


class TestConsolidationOperations:
    def test_operations_is_frozenset(self):
        assert isinstance(CONSOLIDATION_OPERATIONS, frozenset)

    def test_contains_expected_operations(self):
        for op in ("merge", "dedup", "forget", "distill"):
            assert op in CONSOLIDATION_OPERATIONS

    def test_default_operation_in_set(self):
        assert DEFAULT_CONSOLIDATION_OPERATION in CONSOLIDATION_OPERATIONS

    def test_default_operation_is_merge(self):
        assert DEFAULT_CONSOLIDATION_OPERATION == "merge"


class TestDecayPolicyDefaults:
    def test_max_episodes(self):
        assert DEFAULT_MAX_EPISODES == 10_000

    def test_max_procedures(self):
        assert DEFAULT_MAX_PROCEDURES == 1_000

    def test_episode_ttl_days(self):
        assert DEFAULT_EPISODE_TTL_DAYS == 0

    def test_procedure_ttl_days(self):
        assert DEFAULT_PROCEDURE_TTL_DAYS == 0

    def test_min_importance(self):
        assert DEFAULT_MIN_IMPORTANCE == 0.1

    def test_consolidation_threshold(self):
        assert DEFAULT_CONSOLIDATION_THRESHOLD == 3

    def test_enabled(self):
        assert DEFAULT_CONSOLIDATION_ENABLED is True


class TestIdPrefixes:
    def test_episode_prefix(self):
        assert EPISODE_ID_PREFIX == "episode"

    def test_event_prefix(self):
        assert EVENT_ID_PREFIX == "event"

    def test_procedure_prefix(self):
        assert PROCEDURE_ID_PREFIX == "procedure"

    def test_step_prefix(self):
        assert STEP_ID_PREFIX == "pstep"

    def test_consolidation_prefix(self):
        assert CONSOLIDATION_ID_PREFIX == "consol"