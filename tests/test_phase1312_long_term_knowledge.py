"""Phase 13.12 — Long-term evolution knowledge: evidence contract.

Validation result: the EXISTING `EvolutionRecord`/`EvolutionMemory` evidence,
projected deterministically, already answers the long-term questions (what was
missing, why, what supported it, what was attempted, what happened, what
remains open, whether a revisit is justified). No separate "self-learning
brain" was created.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.evolution_continuity import (
    EvolutionOpportunityState,
    continuation_view,
    subject_history,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from tests.phase13_support import record_outcome

_MODULE = Path(__file__).resolve().parents[1] / "atlas/evolution/evolution_continuity.py"


class TestPhase1312LongTermKnowledge:
    def test_history_answers_the_long_term_questions(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-000001",
            subject="cap.longterm",
            terminal="sandbox_failed",
            outcome_kind="unsuccessful_attempt",
            proposal_id="DEV-LT-1",
            related=("disc:cap.longterm",),
        )
        record_outcome(
            memory,
            cycle_id="SEV-000002",
            subject="cap.longterm",
            terminal="activated",
            outcome_kind="successful_evolution",
            proposal_id="DEV-LT-2",
            related=("disc:cap.longterm",),
        )

        facts = subject_history(memory, "cap.longterm")
        assert [f.terminal for f in facts] == ["sandbox_failed", "activated"]
        assert [f.cycle_id for f in facts] == ["SEV-000001", "SEV-000002"]
        assert [f.outcome_kind for f in facts] == [
            "unsuccessful_attempt",
            "successful_evolution",
        ]
        # evidence/provenance survives the projection
        assert "DEV-LT-1" in facts[0].evidence_ids
        assert "disc:cap.longterm" in facts[0].evidence_ids

        opportunity = continuation_view(memory).for_subject("cap.longterm")
        # "what capability was missing / what outcome occurred / is a revisit
        # justified" — all answerable from durable evidence.
        assert opportunity.state is EvolutionOpportunityState.COMPLETED
        assert opportunity.attempts == 2
        assert opportunity.last_terminal == "activated"
        assert opportunity.retry_eligible is False
        assert opportunity.rationale == "capability already activated; do not repeat"

    def test_an_open_limitation_remains_visible_and_explained(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.open",
            terminal="verification_failed",
            outcome_kind="verification_failure",
        )
        opportunity = continuation_view(memory).for_subject("cap.open")
        assert opportunity.state is EvolutionOpportunityState.EVIDENCE_REQUIRED
        assert opportunity.requires_new_evidence is True
        assert "new or corrected evidence" in opportunity.rationale

    def test_no_separate_learning_store_was_created(self):
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert "Brain" not in node.name
                assert "Store" not in node.name
                assert "Database" not in node.name
                assert "Memory" not in node.name  # reuses EvolutionMemory instead

    def test_projection_is_read_only_over_the_existing_memory(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.ro",
            terminal="activated",
            outcome_kind="successful_evolution",
        )
        before = [r.record_id for r in memory.get_records(200)]
        continuation_view(memory)
        subject_history(memory, "cap.ro")
        after = [r.record_id for r in memory.get_records(200)]
        assert before == after
        assert memory.record_count == 1
