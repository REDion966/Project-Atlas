"""Phase 13.7 — Repetition & failure learning: evidence contract.

Validation result: after every kind of outcome, the next invocation sees an
explicit, honest state — success, failure, rejection, blocked/deferred,
requires-new-evidence, retryable or non-retryable — and known non-attemptable
subjects are gated out. No arbitrary retry policy, backoff, or counter exists.
"""

from __future__ import annotations

from atlas.evolution.evolution_continuity import (
    EvolutionOpportunityState,
    continuation_view,
    gate_candidates,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from tests.phase13_support import candidate, record_outcome

#: The twelve required outcome cases -> the Phase-11 terminal that records them.
_CASES: dict[str, tuple[str, EvolutionOpportunityState, bool]] = {
    "successful evolution": ("activated", EvolutionOpportunityState.COMPLETED, False),
    "failed implementation": (
        "sandbox_failed",
        EvolutionOpportunityState.EVIDENCE_REQUIRED,
        True,
    ),
    "failed tests": (
        "sandbox_failed",
        EvolutionOpportunityState.EVIDENCE_REQUIRED,
        True,
    ),
    "failed verification": (
        "verification_failed",
        EvolutionOpportunityState.EVIDENCE_REQUIRED,
        True,
    ),
    "insufficient evidence": (
        "rejected_candidate",
        EvolutionOpportunityState.REJECTED,
        False,
    ),
    "governance denial": (
        "stopped_at_approval",
        EvolutionOpportunityState.DEFERRED,
        False,
    ),
    "unavailable dependency": ("ineligible", EvolutionOpportunityState.BLOCKED, False),
    "invalid objective": (
        "invalid_objective",
        EvolutionOpportunityState.EVIDENCE_REQUIRED,
        True,
    ),
    "stale target": ("promotion_failed", EvolutionOpportunityState.REJECTED, False),
    "rejected candidate": (
        "rejected_candidate",
        EvolutionOpportunityState.REJECTED,
        False,
    ),
    "promotion failure": (
        "promotion_failed",
        EvolutionOpportunityState.REJECTED,
        False,
    ),
    "activation failure": (
        "self_model_inconsistent",
        EvolutionOpportunityState.BLOCKED,
        False,
    ),
}


def _memory(case: str, terminal: str) -> EvolutionMemory:
    memory = EvolutionMemory()
    record_outcome(
        memory,
        cycle_id="SEV-1",
        subject="cap.subject",
        terminal=terminal,
        outcome_kind="x",
    )
    return memory


class TestPhase137RepetitionFailureLearning:
    def test_every_required_outcome_case_is_distinguished(self):
        for case, (terminal, expected, retryable) in _CASES.items():
            view = continuation_view(_memory(case, terminal))
            opportunity = view.for_subject("cap.subject")
            assert opportunity.state is expected, case
            assert opportunity.retry_eligible is retryable, case
            assert opportunity.rationale, case

    def test_the_next_invocation_cannot_blindly_repeat(self):
        for case, (terminal, expected, _retryable) in _CASES.items():
            allowed, reason = continuation_view(
                _memory(case, terminal)
            ).may_attempt("cap.subject")
            assert allowed is (expected is EvolutionOpportunityState.READY), case
            assert reason, case

    def test_known_failures_are_gated_out_of_new_candidates(self):
        for case, (terminal, _expected, _retryable) in _CASES.items():
            view = continuation_view(_memory(case, terminal))
            gate = gate_candidates([candidate("cap.subject")[0]], view)
            assert gate.admitted == (), case
            assert gate.excluded_subjects == ("cap.subject",), case

    def test_a_retry_requires_new_evidence_not_a_blind_repeat(self):
        view = continuation_view(_memory("failed implementation", "sandbox_failed"))
        opportunity = view.for_subject("cap.subject")
        assert opportunity.requires_new_evidence is True
        assert opportunity.attemptable is False
        # The refusal is explicit and explains the requirement.
        allowed, reason = view.may_attempt("cap.subject")
        assert allowed is False
        assert "new or corrected evidence" in reason

    def test_no_arbitrary_retry_policy_was_introduced(self):
        import atlas.evolution.evolution_continuity as module

        for banned in (
            "retry_budget",
            "max_retries",
            "backoff",
            "attempts_remaining",
            "sleep",
            "cooldown_until",
        ):
            assert not hasattr(module, banned), banned
