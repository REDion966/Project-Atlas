"""Track D — Advanced Reasoning catalog constants tests (Batch 1)."""

from atlas.advanced_reasoning.catalog import (
    CAUSAL_PATH_ID_PREFIX,
    COUNTERFACTUAL_ID_PREFIX,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_EVIDENCE_LIMIT,
    DEFAULT_HYPOTHESIS_FAMILY,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_HYPOTHESES,
    DEFAULT_MAX_STEPS,
    DEFAULT_META_WINDOW_SIZE,
    DEFAULT_REASONING_ENABLED,
    DEFAULT_STRATEGY,
    DEFAULT_STRATEGY_ENUM,
    DEFAULT_VERIFICATION_CHECK_TYPES,
    DEFAULT_VERIFICATION_ENABLED,
    FINDING_ID_PREFIX,
    HYPOTHESIS_FAMILIES,
    HYPOTHESIS_ID_PREFIX,
    HYPOTHESIS_SET_ID_PREFIX,
    HYPOTHESIS_SUPPORT_NAMES,
    META_ASSESSMENT_ID_PREFIX,
    REASONER_VERSION,
    STEP_ID_PREFIX,
    STRATEGIES,
    STRATEGY_NAMES,
    STRATEGY_SCORE_ID_PREFIX,
    TRACE_ID_PREFIX,
    TRACE_STATUS_NAMES,
    VERIFICATION_CHECK_TYPES,
    VERIFICATION_ID_PREFIX,
    VERIFICATION_VERDICT_NAMES,
)
from atlas.advanced_reasoning.models import (
    HypothesisSupport,
    ReasoningStrategy,
    TraceStatus,
    VerificationVerdict,
)


class TestStrategies:
    def test_strategies_is_frozenset(self):
        assert isinstance(STRATEGIES, frozenset)

    def test_contains_expected_strategies(self):
        for strategy in ("decompose", "causal", "hypothesis", "verify", "meta"):
            assert strategy in STRATEGIES

    def test_default_strategy_in_set(self):
        assert DEFAULT_STRATEGY in STRATEGIES

    def test_default_strategy_is_decompose(self):
        assert DEFAULT_STRATEGY == "decompose"

    def test_default_strategy_enum(self):
        assert DEFAULT_STRATEGY_ENUM == ReasoningStrategy.DECOMPOSE


class TestStrategyNames:
    def test_contains_all_strategy_names(self):
        for strategy in ReasoningStrategy:
            assert strategy.name in STRATEGY_NAMES


class TestTraceStatusNames:
    def test_contains_all_status_names(self):
        for status in TraceStatus:
            assert status.name in TRACE_STATUS_NAMES


class TestHypothesisFamilies:
    def test_families_is_frozenset(self):
        assert isinstance(HYPOTHESIS_FAMILIES, frozenset)

    def test_contains_expected_families(self):
        for family in ("direct", "inverse", "alternative_cause", "mediating_cause"):
            assert family in HYPOTHESIS_FAMILIES

    def test_default_family_in_set(self):
        assert DEFAULT_HYPOTHESIS_FAMILY in HYPOTHESIS_FAMILIES

    def test_default_family_is_direct(self):
        assert DEFAULT_HYPOTHESIS_FAMILY == "direct"


class TestHypothesisSupportNames:
    def test_contains_all_support_names(self):
        for support in HypothesisSupport:
            assert support.name in HYPOTHESIS_SUPPORT_NAMES


class TestVerificationCheckTypes:
    def test_check_types_is_frozenset(self):
        assert isinstance(VERIFICATION_CHECK_TYPES, frozenset)

    def test_contains_expected_check_types(self):
        for check in (
            "premise_usage",
            "circularity",
            "contradiction",
            "evidence_support",
            "calibration",
        ):
            assert check in VERIFICATION_CHECK_TYPES

    def test_default_check_types_in_set(self):
        for check in DEFAULT_VERIFICATION_CHECK_TYPES:
            assert check in VERIFICATION_CHECK_TYPES

    def test_default_check_types_subset(self):
        assert set(DEFAULT_VERIFICATION_CHECK_TYPES) <= set(VERIFICATION_CHECK_TYPES)


class TestVerificationVerdictNames:
    def test_contains_all_verdict_names(self):
        for verdict in VerificationVerdict:
            assert verdict.name in VERIFICATION_VERDICT_NAMES


class TestConfigDefaults:
    def test_max_steps(self):
        assert DEFAULT_MAX_STEPS == 20

    def test_max_depth(self):
        assert DEFAULT_MAX_DEPTH == 5

    def test_max_hypotheses(self):
        assert DEFAULT_MAX_HYPOTHESES == 5

    def test_confidence_threshold(self):
        assert DEFAULT_CONFIDENCE_THRESHOLD == 0.6

    def test_verification_enabled(self):
        assert DEFAULT_VERIFICATION_ENABLED is True

    def test_meta_window_size(self):
        assert DEFAULT_META_WINDOW_SIZE == 100

    def test_evidence_limit(self):
        assert DEFAULT_EVIDENCE_LIMIT == 10

    def test_enabled(self):
        assert DEFAULT_REASONING_ENABLED is True


class TestIdPrefixes:
    def test_trace_prefix(self):
        assert TRACE_ID_PREFIX == "trace"

    def test_step_prefix(self):
        assert STEP_ID_PREFIX == "step"

    def test_causal_path_prefix(self):
        assert CAUSAL_PATH_ID_PREFIX == "cpath"

    def test_counterfactual_prefix(self):
        assert COUNTERFACTUAL_ID_PREFIX == "cfact"

    def test_hypothesis_prefix(self):
        assert HYPOTHESIS_ID_PREFIX == "hyp"

    def test_hypothesis_set_prefix(self):
        assert HYPOTHESIS_SET_ID_PREFIX == "hset"

    def test_finding_prefix(self):
        assert FINDING_ID_PREFIX == "finding"

    def test_verification_prefix(self):
        assert VERIFICATION_ID_PREFIX == "verify"

    def test_strategy_score_prefix(self):
        assert STRATEGY_SCORE_ID_PREFIX == "sscore"

    def test_meta_assessment_prefix(self):
        assert META_ASSESSMENT_ID_PREFIX == "meta"


class TestReasonerVersion:
    def test_version(self):
        assert REASONER_VERSION == "0.1.0"
