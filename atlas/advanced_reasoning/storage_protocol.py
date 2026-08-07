"""Atlas Advanced Reasoning — Storage Protocol (Track D, Batch 1).

Pure persistence interface for Track D reasoning artifacts. Implemented by
an additive SQLite adapter in a later batch (following the Track C
``LongTermSQLiteStorage`` pattern, e.g. ``reasoning_*`` tables via migration
v10). The adapter — not this module — is the only place that imports
``sqlite3``.

Persistence ONLY: reasoning traces, trace steps, causal paths, counterfactual
results, hypothesis sets, verification reports, and meta assessments.
No business logic. No gateway. No kernel.

Mirrors :mod:`atlas.longterm.storage_protocol` (Track C), :mod:`atlas.toolchain.storage_protocol`
(Track B), and :mod:`atlas.research.storage_protocol` (Track A).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from atlas.advanced_reasoning.models import (
    CausalPath,
    CounterfactualResult,
    Hypothesis,
    HypothesisSet,
    MetaAssessment,
    ReasoningTrace,
    ReasoningTraceStep,
    StrategyScore,
    VerificationFinding,
    VerificationReport,
)


@runtime_checkable
class AdvancedReasoningStorage(Protocol):
    """Persistence surface for Track D advanced-reasoning artifacts.

    All methods are fail-closed: if the adapter is unavailable, write
    methods raise ``sqlite3.OperationalError`` and read methods return
    empty collections (or the adapter marks itself unavailable).
    """

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        """Open the connection and apply additive migrations."""
        ...

    def close(self) -> None:
        """Close the connection cleanly."""
        ...

    def is_available(self) -> bool:
        """Return True when the adapter is initialized and usable."""
        ...

    # -- reasoning traces (idempotent upsert by trace_id) ------------------

    def store_trace(self, trace: ReasoningTrace) -> None:
        """Store or update a reasoning trace."""
        ...

    def load_traces(self) -> list[ReasoningTrace]:
        """Load all reasoning traces sorted by started_at."""
        ...

    def load_trace(self, trace_id: str) -> ReasoningTrace | None:
        """Load a single reasoning trace by its ID."""
        ...

    # -- trace steps (append-only log) ------------------------------------

    def store_trace_step(self, step: ReasoningTraceStep) -> None:
        """Append a trace step (duplicates ignored)."""
        ...

    def load_trace_steps(self, trace_id: str) -> list[ReasoningTraceStep]:
        """Load all steps for a trace, ordered by step_id."""
        ...

    # -- causal reasoning (idempotent upsert / append-only log) ------------

    def store_causal_path(self, path: CausalPath) -> None:
        """Store or update a causal path."""
        ...

    def load_causal_paths(self) -> list[CausalPath]:
        """Load all causal paths."""
        ...

    def store_counterfactual_result(self, result: CounterfactualResult) -> None:
        """Append a counterfactual result (duplicates ignored)."""
        ...

    def load_counterfactual_results(self) -> list[CounterfactualResult]:
        """Load all counterfactual results sorted by result_id."""
        ...

    # -- hypotheses (idempotent upsert by hypothesis_id) -------------------

    def store_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Store or update a hypothesis."""
        ...

    def store_hypothesis_set(self, hypothesis_set: HypothesisSet) -> None:
        """Store or update a hypothesis set."""
        ...

    def load_hypothesis_sets(self) -> list[HypothesisSet]:
        """Load all hypothesis sets sorted by created_at."""
        ...

    def load_hypothesis_set(self, set_id: str) -> HypothesisSet | None:
        """Load a single hypothesis set by its ID."""
        ...

    def load_hypotheses(self, set_id: str) -> list[Hypothesis]:
        """Load all hypotheses for a set, ranked best first."""
        ...

    # -- verifications (append-only log) -----------------------------------

    def store_verification_report(self, report: VerificationReport) -> None:
        """Append a verification report (duplicates ignored)."""
        ...

    def load_verification_reports(self) -> list[VerificationReport]:
        """Load all verification reports sorted by verified_at."""
        ...

    def load_verification_report(self, report_id: str) -> VerificationReport | None:
        """Load a single verification report by its ID."""
        ...

    def load_verification_findings(self, report_id: str) -> list[VerificationFinding]:
        """Load all findings for a report."""
        ...

    # -- meta assessments (append-only log) --------------------------------

    def store_meta_assessment(self, assessment: MetaAssessment) -> None:
        """Append a meta assessment (duplicates ignored)."""
        ...

    def load_meta_assessments(self) -> list[MetaAssessment]:
        """Load all meta assessments sorted by assessed_at."""
        ...

    def load_strategy_scores(self, assessment_id: str) -> list[StrategyScore]:
        """Load all strategy scores for an assessment."""
        ...
