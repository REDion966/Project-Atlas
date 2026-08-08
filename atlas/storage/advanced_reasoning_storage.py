"""Atlas Advanced Reasoning — SQLite Storage (Track D, Batch 2).

Persistence adapter for Track D advanced-reasoning artifacts. Additive
tables only (``reasoning_*``), appended to the shared
``atlas_data/atlas_experience.db`` via the migration framework (migration
v10). Idempotent upserts where the protocol requires them; append-only
logs where the protocol requires them.

Persistence ONLY: no business logic, no gateway, no kernel, no dispatcher.
This module is the ONLY Track D module importing ``sqlite3`` (ATLAS_STATE
§12; TRACK_D §3.2).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas.advanced_reasoning.models import (
    CausalPath,
    CounterfactualResult,
    Hypothesis,
    HypothesisSet,
    HypothesisSupport,
    MetaAssessment,
    ReasoningStrategy,
    ReasoningTrace,
    ReasoningTraceStep,
    StrategyScore,
    TraceStatus,
    VerificationFinding,
    VerificationReport,
    VerificationVerdict,
)
from atlas.advanced_reasoning.storage_protocol import AdvancedReasoningStorage
from atlas.storage import migration


logger = logging.getLogger(__name__)


class AdvancedReasoningSQLiteStorage(AdvancedReasoningStorage):
    """SQLite-backed persistence for Track D reasoning artifacts.

    Every write is fail-closed: on ``sqlite3`` error the adapter marks
    itself unavailable and re-raises so the in-memory repository path can
    degrade gracefully (the ``ReasoningTraceRepository`` dual-write model).
    """

    DEFAULT_DB_PATH = Path("atlas_data/atlas_experience.db")

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None
        self._available = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Open a connection and apply schema migrations (additive)."""
        if self.is_available():
            return
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            migration.apply_migrations(self._conn)
            self._available = True
        except Exception:
            logger.exception(
                "Failed to initialize advanced-reasoning storage at %s",
                self._db_path,
            )
            self._available = False
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def close(self) -> None:
        """Close the database connection cleanly."""
        self._available = False
        if self._conn is not None:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                logger.exception("Error closing advanced-reasoning storage")
            finally:
                self._conn = None

    def is_available(self) -> bool:
        """Return True when the adapter is initialized and usable."""
        return self._available and self._conn is not None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        conn = self._conn
        if conn is None:
            raise sqlite3.OperationalError("Storage connection is closed")
        try:
            return conn.execute(sql, params)
        except sqlite3.Error:
            self._available = False
            raise

    def _run_write(self, sql: str, params: tuple[Any, ...]) -> None:
        """Run a write in a transaction; mark unavailable on failure."""
        if not self.is_available():
            raise sqlite3.OperationalError("Storage is unavailable")
        conn = self._conn
        if conn is None:
            raise sqlite3.OperationalError("Storage connection is closed")
        try:
            with conn:
                conn.execute(sql, params)
        except sqlite3.Error:
            self._available = False
            raise

    @staticmethod
    def _to_json(value: Any) -> str:
        """Serialize a value to a JSON string (datetimes → isoformat)."""

        def _default(item: Any) -> Any:
            if hasattr(item, "isoformat"):
                return item.isoformat()
            return item

        return json.dumps(value, default=_default, ensure_ascii=False)

    @staticmethod
    def _from_json_dict(value: str | None) -> dict[str, Any]:
        try:
            parsed = json.loads(value) if value else {}
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _from_json_list(value: str | None) -> list[Any]:
        try:
            parsed = json.loads(value) if value else []
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    # ------------------------------------------------------------------
    # Reasoning traces (idempotent upsert by trace_id)
    # ------------------------------------------------------------------

    def store_trace(self, trace: ReasoningTrace) -> None:
        self._run_write(
            """
            INSERT OR REPLACE INTO reasoning_traces (
                trace_id, question, strategy, status, conclusion, confidence,
                evidence_refs, started_at, completed_at, reasoner_version, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.trace_id,
                trace.question,
                trace.strategy.name,
                trace.status.name,
                trace.conclusion,
                trace.confidence,
                self._to_json(list(trace.evidence_refs)),
                trace.started_at.isoformat(),
                trace.completed_at.isoformat() if trace.completed_at else None,
                trace.reasoner_version,
                self._to_json(trace.metadata),
            ),
        )
        for index, step in enumerate(trace.steps):
            self._store_trace_step_row(trace.trace_id, index, step)

    def load_traces(self) -> list[ReasoningTrace]:
        cursor = self._execute(
            "SELECT trace_id, question, strategy, status, conclusion, confidence, "
            "evidence_refs, started_at, completed_at, reasoner_version, metadata "
            "FROM reasoning_traces ORDER BY started_at ASC, trace_id ASC"
        )
        return [self._trace_from_row(row) for row in cursor.fetchall()]

    def load_trace(self, trace_id: str) -> ReasoningTrace | None:
        cursor = self._execute(
            "SELECT trace_id, question, strategy, status, conclusion, confidence, "
            "evidence_refs, started_at, completed_at, reasoner_version, metadata "
            "FROM reasoning_traces WHERE trace_id = ?",
            (trace_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._trace_from_row(row)

    # ------------------------------------------------------------------
    # Trace steps (append-only log)
    # ------------------------------------------------------------------

    def store_trace_step(self, step: ReasoningTraceStep) -> None:
        """Append a trace step (duplicates ignored).

        The step model carries no parent trace id, so standalone steps are
        logged under an empty parent. Steps nested inside a trace are
        persisted by :meth:`store_trace` under the trace's id.
        """
        self._store_trace_step_row("", 0, step)

    def load_trace_steps(self, trace_id: str) -> list[ReasoningTraceStep]:
        cursor = self._execute(
            "SELECT trace_id, step_id, sequence, description, premise_step_ids, "
            "evidence_refs, confidence, conclusion, metadata "
            "FROM reasoning_trace_steps WHERE trace_id = ? "
            "ORDER BY sequence ASC, step_id ASC",
            (trace_id,),
        )
        return [self._step_from_row(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Causal reasoning (idempotent upsert / append-only log)
    # ------------------------------------------------------------------

    def store_causal_path(self, path: CausalPath) -> None:
        self._run_write(
            """
            INSERT OR REPLACE INTO reasoning_causal_paths (
                path_id, source, target, entity_ids, relation_types,
                confidence, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path.path_id,
                path.source,
                path.target,
                self._to_json(list(path.entity_ids)),
                self._to_json(list(path.relation_types)),
                path.confidence,
                self._to_json(path.metadata),
            ),
        )

    def load_causal_paths(self) -> list[CausalPath]:
        cursor = self._execute(
            "SELECT path_id, source, target, entity_ids, relation_types, "
            "confidence, metadata FROM reasoning_causal_paths "
            "ORDER BY path_id ASC"
        )
        return [self._causal_path_from_row(row) for row in cursor.fetchall()]

    def store_counterfactual_result(self, result: CounterfactualResult) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO reasoning_counterfactual_results (
                result_id, source_event, assumption, paths_before, paths_after,
                changed, effect_summary, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.result_id,
                result.source_event,
                result.assumption,
                self._to_json([p.to_dict() for p in result.paths_before]),
                self._to_json([p.to_dict() for p in result.paths_after]),
                1 if result.changed else 0,
                result.effect_summary,
                self._to_json(result.metadata),
            ),
        )

    def load_counterfactual_results(self) -> list[CounterfactualResult]:
        cursor = self._execute(
            "SELECT result_id, source_event, assumption, paths_before, "
            "paths_after, changed, effect_summary, metadata "
            "FROM reasoning_counterfactual_results "
            "ORDER BY result_id ASC"
        )
        return [self._counterfactual_from_row(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Hypotheses (idempotent upsert by hypothesis_id / set_id)
    # ------------------------------------------------------------------

    def store_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Store or update a single hypothesis (no parent set)."""
        self._store_hypothesis_row(hypothesis, "")

    def store_hypothesis_set(self, hypothesis_set: HypothesisSet) -> None:
        self._run_write(
            """
            INSERT OR REPLACE INTO reasoning_hypothesis_sets (
                set_id, claim, top_hypothesis_id, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                hypothesis_set.set_id,
                hypothesis_set.claim,
                hypothesis_set.top_hypothesis_id,
                hypothesis_set.created_at.isoformat(),
                self._to_json(hypothesis_set.metadata),
            ),
        )
        for hypothesis in hypothesis_set.hypotheses:
            self._store_hypothesis_row(hypothesis, hypothesis_set.set_id)

    def load_hypothesis_sets(self) -> list[HypothesisSet]:
        cursor = self._execute(
            "SELECT set_id, claim, top_hypothesis_id, created_at, metadata "
            "FROM reasoning_hypothesis_sets ORDER BY created_at ASC, set_id ASC"
        )
        return [self._hypothesis_set_from_row(row) for row in cursor.fetchall()]

    def load_hypothesis_set(self, set_id: str) -> HypothesisSet | None:
        cursor = self._execute(
            "SELECT set_id, claim, top_hypothesis_id, created_at, metadata "
            "FROM reasoning_hypothesis_sets WHERE set_id = ?",
            (set_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._hypothesis_set_from_row(row)

    def load_hypotheses(self, set_id: str) -> list[Hypothesis]:
        cursor = self._execute(
            "SELECT hypothesis_id, set_id, claim, kind, support, score, "
            "evidence_refs, metadata FROM reasoning_hypotheses "
            "WHERE set_id = ? ORDER BY score DESC, hypothesis_id ASC",
            (set_id,),
        )
        return [self._hypothesis_from_row(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Verifications (append-only log)
    # ------------------------------------------------------------------

    def store_verification_report(self, report: VerificationReport) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO reasoning_verifications (
                report_id, target_id, verdict, confidence_before,
                confidence_after, verified_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.report_id,
                report.target_id,
                report.verdict.name,
                report.confidence_before,
                report.confidence_after,
                report.verified_at.isoformat(),
                self._to_json(report.metadata),
            ),
        )
        for finding in report.findings:
            self._store_finding_row(report.report_id, finding)

    def load_verification_reports(self) -> list[VerificationReport]:
        cursor = self._execute(
            "SELECT report_id, target_id, verdict, confidence_before, "
            "confidence_after, verified_at, metadata "
            "FROM reasoning_verifications ORDER BY verified_at ASC, report_id ASC"
        )
        return [self._report_from_row(row) for row in cursor.fetchall()]

    def load_verification_report(self, report_id: str) -> VerificationReport | None:
        cursor = self._execute(
            "SELECT report_id, target_id, verdict, confidence_before, "
            "confidence_after, verified_at, metadata "
            "FROM reasoning_verifications WHERE report_id = ?",
            (report_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._report_from_row(row)

    def load_verification_findings(self, report_id: str) -> list[VerificationFinding]:
        cursor = self._execute(
            "SELECT finding_id, report_id, check_type, passed, message, "
            "severity, metadata FROM reasoning_verification_findings "
            "WHERE report_id = ? ORDER BY finding_id ASC",
            (report_id,),
        )
        return [self._finding_from_row(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Meta assessments (append-only log)
    # ------------------------------------------------------------------

    def store_meta_assessment(self, assessment: MetaAssessment) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO reasoning_meta_assessments (
                assessment_id, recommended_strategy, recommendation_reason,
                assessed_at, metadata
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                assessment.assessment_id,
                assessment.recommended_strategy.name,
                assessment.recommendation_reason,
                assessment.assessed_at.isoformat(),
                self._to_json(assessment.metadata),
            ),
        )
        for score in assessment.strategy_scores:
            self._store_strategy_score_row(assessment.assessment_id, score)

    def load_meta_assessments(self) -> list[MetaAssessment]:
        cursor = self._execute(
            "SELECT assessment_id, recommended_strategy, recommendation_reason, "
            "assessed_at, metadata FROM reasoning_meta_assessments "
            "ORDER BY assessed_at ASC, assessment_id ASC"
        )
        return [self._assessment_from_row(row) for row in cursor.fetchall()]

    def load_strategy_scores(self, assessment_id: str) -> list[StrategyScore]:
        cursor = self._execute(
            "SELECT score_id, assessment_id, strategy, success_count, "
            "failure_count, total_count, success_rate, avg_verification_pass_rate, "
            "avg_steps, score, metadata FROM reasoning_strategy_scores "
            "WHERE assessment_id = ? ORDER BY score DESC, strategy ASC",
            (assessment_id,),
        )
        return [self._score_from_row(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Row writers
    # ------------------------------------------------------------------

    def _store_trace_step_row(self, trace_id: str, sequence: int, step: ReasoningTraceStep) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO reasoning_trace_steps (
                trace_id, step_id, sequence, description, premise_step_ids,
                evidence_refs, confidence, conclusion, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                step.step_id,
                sequence,
                step.description,
                self._to_json(list(step.premise_step_ids)),
                self._to_json(list(step.evidence_refs)),
                step.confidence,
                step.conclusion,
                self._to_json(step.metadata),
            ),
        )

    def _store_hypothesis_row(self, hypothesis: Hypothesis, set_id: str) -> None:
        self._run_write(
            """
            INSERT OR REPLACE INTO reasoning_hypotheses (
                hypothesis_id, set_id, claim, kind, support, score,
                evidence_refs, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hypothesis.hypothesis_id,
                set_id,
                hypothesis.claim,
                hypothesis.kind,
                hypothesis.support.name,
                hypothesis.score,
                self._to_json(list(hypothesis.evidence_refs)),
                self._to_json(hypothesis.metadata),
            ),
        )

    def _store_finding_row(self, report_id: str, finding: VerificationFinding) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO reasoning_verification_findings (
                finding_id, report_id, check_type, passed, message,
                severity, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.finding_id,
                report_id,
                finding.check_type,
                1 if finding.passed else 0,
                finding.message,
                finding.severity,
                self._to_json(finding.metadata),
            ),
        )

    def _store_strategy_score_row(self, assessment_id: str, score: StrategyScore) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO reasoning_strategy_scores (
                score_id, assessment_id, strategy, success_count, failure_count,
                total_count, success_rate, avg_verification_pass_rate, avg_steps,
                score, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{assessment_id}:{score.strategy.name}",
                assessment_id,
                score.strategy.name,
                score.success_count,
                score.failure_count,
                score.total_count,
                score.success_rate,
                score.avg_verification_pass_rate,
                score.avg_steps,
                score.score,
                self._to_json(score.metadata),
            ),
        )

    # ------------------------------------------------------------------
    # Row readers
    # ------------------------------------------------------------------

    def _trace_from_row(self, row: sqlite3.Row) -> ReasoningTrace:
        return ReasoningTrace(
            trace_id=row["trace_id"],
            question=row["question"],
            strategy=ReasoningStrategy[row["strategy"]],
            steps=tuple(self.load_trace_steps(row["trace_id"])),
            status=TraceStatus[row["status"]],
            conclusion=row["conclusion"],
            confidence=row["confidence"],
            evidence_refs=tuple(self._from_json_list(row["evidence_refs"])),
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            reasoner_version=row["reasoner_version"],
            metadata=self._from_json_dict(row["metadata"]),
        )

    @staticmethod
    def _step_from_row(row: sqlite3.Row) -> ReasoningTraceStep:
        return ReasoningTraceStep(
            step_id=row["step_id"],
            description=row["description"],
            premise_step_ids=tuple(json.loads(row["premise_step_ids"] or "[]")),
            evidence_refs=tuple(json.loads(row["evidence_refs"] or "[]")),
            confidence=row["confidence"],
            conclusion=row["conclusion"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    @staticmethod
    def _causal_path_from_row(row: sqlite3.Row) -> CausalPath:
        return CausalPath(
            path_id=row["path_id"],
            source=row["source"],
            target=row["target"],
            entity_ids=tuple(json.loads(row["entity_ids"] or "[]")),
            relation_types=tuple(json.loads(row["relation_types"] or "[]")),
            confidence=row["confidence"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def _counterfactual_from_row(self, row: sqlite3.Row) -> CounterfactualResult:
        before = self._causal_paths_from_json(self._from_json_list(row["paths_before"]))
        after = self._causal_paths_from_json(self._from_json_list(row["paths_after"]))
        return CounterfactualResult(
            result_id=row["result_id"],
            source_event=row["source_event"],
            assumption=row["assumption"],
            paths_before=before,
            paths_after=after,
            changed=bool(row["changed"]),
            effect_summary=row["effect_summary"],
            metadata=self._from_json_dict(row["metadata"]),
        )

    def _hypothesis_set_from_row(self, row: sqlite3.Row) -> HypothesisSet:
        return HypothesisSet(
            set_id=row["set_id"],
            claim=row["claim"],
            hypotheses=tuple(self.load_hypotheses(row["set_id"])),
            top_hypothesis_id=row["top_hypothesis_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=self._from_json_dict(row["metadata"]),
        )

    @staticmethod
    def _hypothesis_from_row(row: sqlite3.Row) -> Hypothesis:
        return Hypothesis(
            hypothesis_id=row["hypothesis_id"],
            claim=row["claim"],
            kind=row["kind"],
            support=HypothesisSupport[row["support"]],
            score=row["score"],
            evidence_refs=tuple(json.loads(row["evidence_refs"] or "[]")),
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def _report_from_row(self, row: sqlite3.Row) -> VerificationReport:
        return VerificationReport(
            report_id=row["report_id"],
            target_id=row["target_id"],
            verdict=VerificationVerdict[row["verdict"]],
            findings=tuple(self.load_verification_findings(row["report_id"])),
            confidence_before=row["confidence_before"],
            confidence_after=row["confidence_after"],
            verified_at=datetime.fromisoformat(row["verified_at"]),
            metadata=self._from_json_dict(row["metadata"]),
        )

    @staticmethod
    def _finding_from_row(row: sqlite3.Row) -> VerificationFinding:
        return VerificationFinding(
            finding_id=row["finding_id"],
            check_type=row["check_type"],
            passed=bool(row["passed"]),
            message=row["message"],
            severity=row["severity"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def _assessment_from_row(self, row: sqlite3.Row) -> MetaAssessment:
        return MetaAssessment(
            assessment_id=row["assessment_id"],
            strategy_scores=tuple(self.load_strategy_scores(row["assessment_id"])),
            recommended_strategy=ReasoningStrategy[row["recommended_strategy"]],
            recommendation_reason=row["recommendation_reason"],
            assessed_at=datetime.fromisoformat(row["assessed_at"]),
            metadata=self._from_json_dict(row["metadata"]),
        )

    @staticmethod
    def _score_from_row(row: sqlite3.Row) -> StrategyScore:
        return StrategyScore(
            strategy=ReasoningStrategy[row["strategy"]],
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            total_count=row["total_count"],
            success_rate=row["success_rate"],
            avg_verification_pass_rate=row["avg_verification_pass_rate"],
            avg_steps=row["avg_steps"],
            score=row["score"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    @staticmethod
    def _causal_paths_from_json(items: list[Any]) -> tuple[CausalPath, ...]:
        """Reconstruct CausalPath objects from serialized dicts (fail-soft)."""
        paths: list[CausalPath] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            paths.append(
                CausalPath(
                    path_id=str(item.get("path_id", "")),
                    source=str(item.get("source", "")),
                    target=str(item.get("target", "")),
                    entity_ids=tuple(item.get("entity_ids", ())),
                    relation_types=tuple(item.get("relation_types", ())),
                    confidence=float(item.get("confidence", 0.0)),
                    metadata=item.get("metadata", {}) or {},
                )
            )
        return tuple(paths)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_schema_version(self) -> int:
        """Return the current schema version without applying migrations."""
        if self._conn is None:
            return 0
        return migration.get_schema_version(self._conn)

    @property
    def db_path(self) -> Path:
        return self._db_path
