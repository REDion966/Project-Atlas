"""Atlas Advanced Reasoning — Catalog & Constants (Track D, Batch 1).

Shared, pure constants describing the advanced-reasoning ecosystem:
strategy names, hypothesis template families, verification check types,
trace status names, and default config values. Imported by the reasoners,
verifier, meta-reasoning engine, and capability handlers so discovery and
configuration can never drift apart.

No runtime dependencies beyond the standard library and the pure
``atlas.advanced_reasoning.models`` enums.
"""

from __future__ import annotations

from atlas.advanced_reasoning.models import (
    HypothesisSupport,
    ReasoningStrategy,
    TraceStatus,
    VerificationVerdict,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

#: Strategies supported by the multi-step reasoner.
STRATEGIES: frozenset[str] = frozenset(
    {
        "decompose",
        "causal",
        "hypothesis",
        "verify",
        "meta",
    }
)

#: Strategy names derived from the :class:`ReasoningStrategy` enum.
STRATEGY_NAMES: frozenset[str] = frozenset(
    {
        ReasoningStrategy.DECOMPOSE.name,
        ReasoningStrategy.CAUSAL.name,
        ReasoningStrategy.HYPOTHESIS.name,
        ReasoningStrategy.VERIFY.name,
        ReasoningStrategy.META.name,
    }
)

#: Default strategy when a caller does not specify one.
DEFAULT_STRATEGY: str = "decompose"
DEFAULT_STRATEGY_ENUM: ReasoningStrategy = ReasoningStrategy.DECOMPOSE


# ---------------------------------------------------------------------------
# Trace status names
# ---------------------------------------------------------------------------

#: Trace status names derived from the :class:`TraceStatus` enum.
TRACE_STATUS_NAMES: frozenset[str] = frozenset(
    {
        TraceStatus.DRAFT.name,
        TraceStatus.COMPLETED.name,
        TraceStatus.RAN_OUT_OF_BUDGET.name,
        TraceStatus.FAILED.name,
    }
)


# ---------------------------------------------------------------------------
# Hypothesis template families
# ---------------------------------------------------------------------------

#: Template families used by the hypothesis generator.
HYPOTHESIS_FAMILIES: frozenset[str] = frozenset(
    {
        "direct",
        "inverse",
        "alternative_cause",
        "mediating_cause",
    }
)

#: Default template family.
DEFAULT_HYPOTHESIS_FAMILY: str = "direct"


# ---------------------------------------------------------------------------
# Hypothesis support names
# ---------------------------------------------------------------------------

#: Hypothesis support names derived from the :class:`HypothesisSupport` enum.
HYPOTHESIS_SUPPORT_NAMES: frozenset[str] = frozenset(
    {
        HypothesisSupport.SUPPORTED.name,
        HypothesisSupport.CONTRADICTED.name,
        HypothesisSupport.UNVERIFIED.name,
    }
)


# ---------------------------------------------------------------------------
# Verification check types
# ---------------------------------------------------------------------------

#: Check types supported by the self-verifier.
VERIFICATION_CHECK_TYPES: frozenset[str] = frozenset(
    {
        "premise_usage",
        "circularity",
        "contradiction",
        "evidence_support",
        "calibration",
    }
)

#: Default verification check types.
DEFAULT_VERIFICATION_CHECK_TYPES: tuple[str, ...] = (
    "premise_usage",
    "circularity",
    "contradiction",
    "evidence_support",
    "calibration",
)


# ---------------------------------------------------------------------------
# Verification verdict names
# ---------------------------------------------------------------------------

#: Verdict names derived from the :class:`VerificationVerdict` enum.
VERIFICATION_VERDICT_NAMES: frozenset[str] = frozenset(
    {
        VerificationVerdict.PASSED.name,
        VerificationVerdict.FAILED.name,
        VerificationVerdict.INCONCLUSIVE.name,
    }
)


# ---------------------------------------------------------------------------
# Default config values
# ---------------------------------------------------------------------------

#: Default maximum inference steps per multi-step trace.
DEFAULT_MAX_STEPS: int = 20

#: Default maximum causal path depth / decomposition depth.
DEFAULT_MAX_DEPTH: int = 5

#: Default maximum hypotheses generated per set.
DEFAULT_MAX_HYPOTHESES: int = 5

#: Default minimum final confidence for a trace conclusion.
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.6

#: Default value for whether self-verification runs by default.
DEFAULT_VERIFICATION_ENABLED: bool = True

#: Default number of recent traces scored by meta-reasoning.
DEFAULT_META_WINDOW_SIZE: int = 100

#: Default maximum evidence references bound per step.
DEFAULT_EVIDENCE_LIMIT: int = 10

#: Default enabled state for the advanced-reasoning track.
DEFAULT_REASONING_ENABLED: bool = True


# ---------------------------------------------------------------------------
# ID prefixes
# ---------------------------------------------------------------------------

TRACE_ID_PREFIX: str = "trace"
STEP_ID_PREFIX: str = "step"
CAUSAL_PATH_ID_PREFIX: str = "cpath"
COUNTERFACTUAL_ID_PREFIX: str = "cfact"
HYPOTHESIS_ID_PREFIX: str = "hyp"
HYPOTHESIS_SET_ID_PREFIX: str = "hset"
FINDING_ID_PREFIX: str = "finding"
VERIFICATION_ID_PREFIX: str = "verify"
STRATEGY_SCORE_ID_PREFIX: str = "sscore"
META_ASSESSMENT_ID_PREFIX: str = "meta"


# ---------------------------------------------------------------------------
# Reasoner version
# ---------------------------------------------------------------------------

#: Version of the deterministic reasoning engines (Batch 1 foundation).
REASONER_VERSION: str = "0.1.0"
