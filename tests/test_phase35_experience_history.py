"""Phase 3.5 — Experience/history representation: evidence contract.

Investigation result (evidence, not aspiration): Atlas already retains a durable,
structured representation of its own experiences/history, so no new history
database was introduced.

* ``atlas/experience/models.py::StructuredExperience`` — a structured record of
  one cognitive pipeline execution (outcome, pipeline path, reasoning/planning/
  tool/learning evidence, identity snapshot).
* ``atlas/experience/experience_repository.py::ExperienceRepository`` — bounded
  retention + retrieval (by id, recency, outcome, window) with best-effort
  persistence and ``restore()``.
* ``atlas/storage/experience_storage.py::SQLiteExperienceStorage`` — durable
  storage (``atlas_data/atlas_experience.db``).
* ``OutcomeTracker`` / ``SelfModelEngine`` / ``TrendAnalyzer`` — history is used
  to track goals and produce self-model snapshots.
* ``atlas/evolution/evolution_memory.py`` — the evolution/history ledger of
  ``EvolutionRecord`` rows (e.g. ``event_type="development"``) for completed
  development/execution work.
* ``atlas/longterm/`` (Track C) — episodic/procedural memory of what happened.

These tests pin: structured history records, ordered retrieval, durability
across a genuine process boundary, and the semantic separation of
experience/history from conversation/context and factual knowledge.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.storage.experience_storage import SQLiteExperienceStorage

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _experience(exp_id: str, outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS):
    return StructuredExperience(
        experience_id=exp_id,
        timestamp=datetime.now(),
        duration_ms=12.0,
        pipeline_path=["understanding", "reasoning", "planning"],
        outcome=outcome,
        user_input="do a thing",
        reasoning_goal="respond: do a thing",
        reasoning_capabilities=["conversation"],
        reasoning_success_count=1,
        reasoning_total_count=1,
    )


class TestPhase35ExperienceHistoryEvidence:
    def test_structured_experience_is_a_history_record(self):
        experience = _experience("EXP-P35-A")
        assert experience.experience_id == "EXP-P35-A"
        assert experience.outcome is ExperienceOutcome.SUCCESS
        assert experience.pipeline_path == ["understanding", "reasoning", "planning"]
        assert experience.reasoning_goal
        # Immutable value object (frozen/slots).
        assert not hasattr(experience, "__dict__")

    def test_repository_retains_ordered_and_filterable_history(self):
        repo = ExperienceRepository()
        repo.store_experience(_experience("EXP-P35-1", ExperienceOutcome.SUCCESS))
        repo.store_experience(_experience("EXP-P35-2", ExperienceOutcome.FAILURE))

        assert repo.experience_count == 2
        assert repo.get_experience("EXP-P35-1") is not None
        # Newest first.
        assert [e.experience_id for e in repo.get_experiences(2)] == [
            "EXP-P35-2",
            "EXP-P35-1",
        ]
        failures = repo.get_experiences_by_outcome(ExperienceOutcome.FAILURE)
        assert [e.experience_id for e in failures] == ["EXP-P35-2"]

    def test_experience_history_survives_process_boundary(self, tmp_path):
        driver = tmp_path / "driver.py"
        driver.write_text(_DRIVER, encoding="utf-8")
        db = tmp_path / "experience.db"
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT))

        proc_a = subprocess.run(
            [sys.executable, str(driver), "write", str(db)],
            cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120,
        )
        assert proc_a.returncode == 0, proc_a.stderr
        assert "WROTE" in proc_a.stdout

        proc_b = subprocess.run(
            [sys.executable, str(driver), "read", str(db)],
            cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120,
        )
        assert proc_b.returncode == 0, proc_b.stderr
        assert "READ:EXP-P35-1" in proc_b.stdout

    def test_development_history_is_recorded_as_evidence_ledger(self):
        memory = EvolutionMemory()
        memory.store_record(
            EvolutionRecord(
                record_id="DEV-P35-0001",
                event_type="development",
                description="Self-development run for proposal 'PROP-P35'.",
                related_ids=["PROP-P35", "PLAN-P35"],
                metadata={"terminal_status": "SUCCESS", "success": True},
            )
        )
        development = memory.get_records_by_type("development")
        assert len(development) == 1
        assert development[0].related_ids == ["PROP-P35", "PLAN-P35"]
        assert development[0].metadata["terminal_status"] == "SUCCESS"

    def test_experience_history_is_separate_from_other_domains(self):
        # Experience lives in its own module/store, distinct from conversation,
        # factual knowledge, and self-knowledge.
        import atlas.experience.models as experience_models

        assert "experience" in experience_models.__name__
        assert not hasattr(StructuredExperience, "citations")  # not research knowledge
        assert not hasattr(StructuredExperience, "messages")  # not conversation history
        assert not hasattr(StructuredExperience, "provided_capabilities")  # not self-knowledge

        from atlas.storage.conversation_storage import ConversationStorage
        from atlas.memory.storage.json_storage import Storage as MemoryStorage

        assert str(SQLiteExperienceStorage.DEFAULT_DB_PATH) != str(
            ConversationStorage.STORAGE_DIR
        )
        assert str(SQLiteExperienceStorage.DEFAULT_DB_PATH) != str(
            MemoryStorage.MEMORY_FILE
        )


#: Two-process driver: ``write`` stores an experience durably; ``read`` (a fresh
#: interpreter) restores it through the Atlas-owned repository.
_DRIVER = """
import sys
from datetime import datetime
from pathlib import Path

from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.storage.experience_storage import SQLiteExperienceStorage

mode = sys.argv[1]
storage = SQLiteExperienceStorage(db_path=Path(sys.argv[2]))
storage.initialize()
try:
    repo = ExperienceRepository(storage=storage)
    if mode == "write":
        repo.store_experience(
            StructuredExperience(
                experience_id="EXP-P35-1",
                timestamp=datetime.now(),
                duration_ms=5.0,
                pipeline_path=["understanding", "reasoning"],
                outcome=ExperienceOutcome.SUCCESS,
                user_input="persist me",
            )
        )
        print("WROTE")
    else:
        repo.restore()
        got = repo.get_experience("EXP-P35-1")
        assert got is not None, "experience lost across process boundary"
        assert got.outcome is ExperienceOutcome.SUCCESS
        assert "reasoning" in got.pipeline_path
        assert got.user_input == "persist me"
        print("READ:" + got.experience_id)
finally:
    storage.close()
"""
