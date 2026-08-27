"""
Atlas SQLite Evolution Storage — Phase 11.3 / 12.3 / 13.5

Infrastructure adapter implementing the EvolutionStorage interface with
SQLite. Reuses the existing atlas_experience.db database and migration
framework. Owns connection lifecycle, serialization, and graceful failure.

This module is the only place in the evolution persistence layer that
imports sqlite3.

Phase 12.3 — Added store_insight() and load_insights() for evolution
insight persistence.
Phase 13.5 — Added store_observation()/load_observations() and the
evolution knowledge persistence methods (patterns, strategies,
capabilities, bottlenecks, snapshots) for the Persistent Evolution
Knowledge layer.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from atlas.evolution.storage_interface import EvolutionStorage
from atlas.storage import migration


logger = logging.getLogger(__name__)


class SQLiteEvolutionStorage(EvolutionStorage):
    """
    SQLite-backed persistent storage for evolution proposals, approval
    requests, and evolution records.

    Reuses the existing atlas_data/atlas_experience.db database file.
    All data is exchanged as plain dictionaries. Nested fields are stored
    as JSON strings.

    Graceful degradation: any write or read failure marks the adapter as
    unavailable so Atlas can fall back to memory-only operation.
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
        """Create the database directory, open a connection, and apply schema."""
        if self.is_available():
            return
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            migration.apply_migrations(self._conn)
            self._available = True
        except Exception:
            logger.exception("Failed to initialize SQLite evolution storage at %s", self._db_path)
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
                logger.exception("Error closing SQLite evolution storage")
            finally:
                self._conn = None

    def is_available(self) -> bool:
        """Return True if the adapter is initialized and usable."""
        return self._available and self._conn is not None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _execute(
        self,
        sql: str,
        params: tuple[Any, ...] | list[tuple[Any, ...]] | None = None,
    ) -> sqlite3.Cursor:
        """Execute SQL safely; mark unavailable on failure."""
        conn = self._conn
        if conn is None:
            raise sqlite3.OperationalError("Storage connection is closed")
        try:
            if params is not None and isinstance(params, list):
                return conn.executemany(sql, params)
            return conn.execute(sql, params or ())
        except sqlite3.Error:
            self._available = False
            raise

    @staticmethod
    def _to_json(value: Any) -> str:
        """Serialize a value to a JSON string."""
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _from_json(value: str | None) -> Any:
        """Deserialize a JSON string back to a Python object."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def _run_write(self, sql: str, params: tuple[Any, ...]) -> None:
        """Run a write statement and commit inside a transaction."""
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

    # ------------------------------------------------------------------
    # Proposals
    # ------------------------------------------------------------------

    def store_proposal(self, data: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO evolution_proposals (
                proposal_id, title, summary, rationale, expected_benefit,
                risks, impact_analysis, implementation_approach,
                plan_id, plan_title, plan_description, plan_priority,
                plan_weaknesses, plan_expected_benefit, plan_complexity,
                plan_target_components, status, rejection_reason,
                created_at, approved_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        plan = data.get("plan", {})
        params = (
            data.get("proposal_id"),
            data.get("title", ""),
            data.get("summary", ""),
            data.get("rationale", ""),
            data.get("expected_benefit", ""),
            data.get("risks", ""),
            data.get("impact_analysis", ""),
            data.get("implementation_approach", ""),
            plan.get("plan_id", ""),
            plan.get("title", ""),
            plan.get("description", ""),
            plan.get("priority", ""),
            self._to_json(plan.get("weaknesses", [])),
            plan.get("expected_benefit", ""),
            plan.get("complexity_estimate", "medium"),
            self._to_json(plan.get("target_components", [])),
            data.get("status", ""),
            data.get("rejection_reason", ""),
            data.get("created_at", ""),
            data.get("approved_at"),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_proposals(self) -> list[dict]:
        cursor = self._execute(
            "SELECT * FROM evolution_proposals ORDER BY created_at ASC"
        )
        return [self._row_to_proposal(row) for row in cursor.fetchall()]

    def _row_to_proposal(self, row: sqlite3.Row) -> dict:
        return {
            "proposal_id": row["proposal_id"],
            "title": row["title"],
            "summary": row["summary"],
            "rationale": row["rationale"],
            "expected_benefit": row["expected_benefit"],
            "risks": row["risks"],
            "impact_analysis": row["impact_analysis"],
            "implementation_approach": row["implementation_approach"],
            "plan": {
                "plan_id": row["plan_id"],
                "title": row["plan_title"],
                "description": row["plan_description"],
                "priority": row["plan_priority"],
                "weaknesses": self._from_json(row["plan_weaknesses"]) or [],
                "expected_benefit": row["plan_expected_benefit"],
                "complexity_estimate": row["plan_complexity"],
                "target_components": self._from_json(row["plan_target_components"]) or [],
            },
            "status": row["status"],
            "rejection_reason": row["rejection_reason"],
            "created_at": row["created_at"],
            "approved_at": row["approved_at"],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    # ------------------------------------------------------------------
    # Approval requests
    # ------------------------------------------------------------------

    def store_approval_request(self, data: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO evolution_approval_requests (
                request_id, proposal_id, title, description, rationale,
                risks, expected_benefit, decision, decision_comment,
                created_at, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("request_id"),
            data.get("proposal_id"),
            data.get("title", ""),
            data.get("description", ""),
            data.get("rationale", ""),
            data.get("risks", ""),
            data.get("expected_benefit", ""),
            data.get("decision", ""),
            data.get("decision_comment", ""),
            data.get("created_at", ""),
            data.get("decided_at"),
        )
        self._run_write(sql, params)

    def load_approval_requests(self) -> list[dict]:
        cursor = self._execute(
            "SELECT * FROM evolution_approval_requests ORDER BY created_at ASC"
        )
        return [self._row_to_approval_request(row) for row in cursor.fetchall()]

    def _row_to_approval_request(self, row: sqlite3.Row) -> dict:
        return {
            "request_id": row["request_id"],
            "proposal_id": row["proposal_id"],
            "title": row["title"],
            "description": row["description"],
            "rationale": row["rationale"],
            "risks": row["risks"],
            "expected_benefit": row["expected_benefit"],
            "decision": row["decision"],
            "decision_comment": row["decision_comment"],
            "created_at": row["created_at"],
            "decided_at": row["decided_at"],
        }

    # ------------------------------------------------------------------
    # Evolution records
    # ------------------------------------------------------------------

    def store_record(self, data: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO evolution_records (
                record_id, event_type, description, related_ids,
                timestamp, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("record_id"),
            data.get("event_type", ""),
            data.get("description", ""),
            self._to_json(data.get("related_ids", [])),
            data.get("timestamp", ""),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_records(self) -> list[dict]:
        cursor = self._execute(
            "SELECT * FROM evolution_records ORDER BY timestamp ASC"
        )
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def _row_to_record(self, row: sqlite3.Row) -> dict:
        return {
            "record_id": row["record_id"],
            "event_type": row["event_type"],
            "description": row["description"],
            "related_ids": self._from_json(row["related_ids"]) or [],
            "timestamp": row["timestamp"],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    # ------------------------------------------------------------------
    # Evolution insights (Phase 12.3+)
    # ------------------------------------------------------------------

    def store_insight(self, data: dict) -> None:
        """Persist a single evolution insight dictionary."""
        sql = """
            INSERT OR REPLACE INTO evolution_insights (
                insight_id, proposal_id, execution_record_id,
                tracked_goal_id, outcome, confidence,
                effectiveness_score, evidence_summary, evidence_count,
                evidence_quality, regression_risk, analyzed_at,
                proposal_title, proposal_summary, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("insight_id"),
            data.get("proposal_id"),
            data.get("execution_record_id"),
            data.get("tracked_goal_id", ""),
            data.get("outcome", "inconclusive"),
            data.get("confidence", 0.0),
            data.get("effectiveness_score", 0.0),
            data.get("evidence_summary", ""),
            data.get("evidence_count", 0),
            data.get("evidence_quality", 0.0),
            data.get("regression_risk", 0.0),
            data.get("analyzed_at", ""),
            data.get("proposal_title", ""),
            data.get("proposal_summary", ""),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_insights(
        self,
        proposal_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Load persisted evolution insights, newest first."""
        if proposal_id is not None:
            cursor = self._execute(
                """
                SELECT * FROM evolution_insights
                WHERE proposal_id = ?
                ORDER BY analyzed_at DESC
                LIMIT ?
                """,
                (proposal_id, limit),
            )
        else:
            cursor = self._execute(
                """
                SELECT * FROM evolution_insights
                ORDER BY analyzed_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [self._row_to_insight(row) for row in cursor.fetchall()]

    def _row_to_insight(self, row: sqlite3.Row) -> dict:
        """Convert a database row to an insight dictionary."""
        return {
            "insight_id": row["insight_id"],
            "proposal_id": row["proposal_id"],
            "execution_record_id": row["execution_record_id"],
            "tracked_goal_id": row["tracked_goal_id"],
            "outcome": row["outcome"],
            "confidence": row["confidence"],
            "effectiveness_score": row["effectiveness_score"],
            "evidence_summary": row["evidence_summary"],
            "evidence_count": row["evidence_count"],
            "evidence_quality": row["evidence_quality"],
            "regression_risk": row["regression_risk"],
            "analyzed_at": row["analyzed_at"],
            "proposal_title": row["proposal_title"],
            "proposal_summary": row["proposal_summary"],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    # ------------------------------------------------------------------
    # Evolution observations (Phase 13.5+)
    # ------------------------------------------------------------------

    def store_observation(self, data: dict) -> None:
        """Persist a single evolution observation dictionary."""
        sql = """
            INSERT OR REPLACE INTO evolution_observations (
                observation_id, category, metric_name, value, unit,
                description, timestamp, source, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("observation_id", ""),
            data.get("category", ""),
            data.get("metric_name", ""),
            self._to_json(data.get("value", {})),
            data.get("unit", ""),
            data.get("description", ""),
            data.get("timestamp", ""),
            data.get("source", ""),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_observations(self) -> list[dict]:
        """Load all stored evolution observations, oldest first."""
        cursor = self._execute(
            "SELECT * FROM evolution_observations ORDER BY timestamp ASC"
        )
        return [self._row_to_observation(row) for row in cursor.fetchall()]

    def _row_to_observation(self, row: sqlite3.Row) -> dict:
        """Convert a database row to an observation dictionary."""
        return {
            "observation_id": row["observation_id"],
            "category": row["category"],
            "metric_name": row["metric_name"],
            "value": self._from_json(row["value"]) or {},
            "unit": row["unit"],
            "description": row["description"],
            "timestamp": row["timestamp"],
            "source": row["source"],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    # ------------------------------------------------------------------
    # Evolution knowledge (Phase 13.5+)
    # ------------------------------------------------------------------

    def store_knowledge_pattern(self, data: dict) -> None:
        """Persist a single recurring outcome pattern dictionary."""
        sql = """
            INSERT OR REPLACE INTO evolution_knowledge_patterns (
                pattern_id, area, outcome, occurrence_count,
                success_count, partial_count, failure_count,
                inconclusive_count, confidence, first_seen, last_seen,
                related_ids, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("pattern_id"),
            data.get("area", ""),
            data.get("outcome", "inconclusive"),
            data.get("occurrence_count", 0),
            data.get("success_count", 0),
            data.get("partial_count", 0),
            data.get("failure_count", 0),
            data.get("inconclusive_count", 0),
            data.get("confidence", 0.0),
            data.get("first_seen", ""),
            data.get("last_seen", ""),
            self._to_json(data.get("related_ids", [])),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_knowledge_patterns(self) -> list[dict]:
        """Load all stored knowledge patterns, oldest first."""
        cursor = self._execute(
            "SELECT * FROM evolution_knowledge_patterns ORDER BY first_seen ASC"
        )
        return [self._row_to_knowledge_pattern(row) for row in cursor.fetchall()]

    def _row_to_knowledge_pattern(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a knowledge pattern dictionary."""
        return {
            "pattern_id": row["pattern_id"],
            "area": row["area"],
            "outcome": row["outcome"],
            "occurrence_count": row["occurrence_count"],
            "success_count": row["success_count"],
            "partial_count": row["partial_count"],
            "failure_count": row["failure_count"],
            "inconclusive_count": row["inconclusive_count"],
            "confidence": row["confidence"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "related_ids": self._from_json(row["related_ids"]) or [],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    def store_knowledge_strategy(self, data: dict) -> None:
        """Persist a single strategy knowledge dictionary."""
        sql = """
            INSERT OR REPLACE INTO evolution_knowledge_strategies (
                strategy_key, strategy_name, success_count, failure_count,
                occurrence_count, effectiveness, confidence,
                avg_regression_risk, first_seen, last_seen,
                related_ids, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("strategy_key"),
            data.get("strategy_name", ""),
            data.get("success_count", 0),
            data.get("failure_count", 0),
            data.get("occurrence_count", 0),
            data.get("effectiveness", 0.0),
            data.get("confidence", 0.0),
            data.get("avg_regression_risk", 0.0),
            data.get("first_seen", ""),
            data.get("last_seen", ""),
            self._to_json(data.get("related_ids", [])),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_knowledge_strategies(self) -> list[dict]:
        """Load all stored knowledge strategies, oldest first."""
        cursor = self._execute(
            "SELECT * FROM evolution_knowledge_strategies ORDER BY first_seen ASC"
        )
        return [self._row_to_knowledge_strategy(row) for row in cursor.fetchall()]

    def _row_to_knowledge_strategy(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a strategy knowledge dictionary."""
        return {
            "strategy_key": row["strategy_key"],
            "strategy_name": row["strategy_name"],
            "success_count": row["success_count"],
            "failure_count": row["failure_count"],
            "occurrence_count": row["occurrence_count"],
            "effectiveness": row["effectiveness"],
            "confidence": row["confidence"],
            "avg_regression_risk": row["avg_regression_risk"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "related_ids": self._from_json(row["related_ids"]) or [],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    def store_knowledge_capability(self, data: dict) -> None:
        """Persist a single capability evolution dictionary."""
        sql = """
            INSERT OR REPLACE INTO evolution_knowledge_capabilities (
                capability_name, assessments, observed_count,
                first_seen, last_seen, related_ids, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("capability_name"),
            self._to_json(data.get("assessments", [])),
            data.get("observed_count", 0),
            data.get("first_seen", ""),
            data.get("last_seen", ""),
            self._to_json(data.get("related_ids", [])),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_knowledge_capabilities(self) -> list[dict]:
        """Load all stored knowledge capabilities, oldest first."""
        cursor = self._execute(
            "SELECT * FROM evolution_knowledge_capabilities ORDER BY first_seen ASC"
        )
        return [self._row_to_knowledge_capability(row) for row in cursor.fetchall()]

    def _row_to_knowledge_capability(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a capability evolution dictionary."""
        return {
            "capability_name": row["capability_name"],
            "assessments": self._from_json(row["assessments"]) or [],
            "observed_count": row["observed_count"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "related_ids": self._from_json(row["related_ids"]) or [],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    def store_knowledge_bottleneck(self, data: dict) -> None:
        """Persist a single bottleneck profile dictionary."""
        sql = """
            INSERT OR REPLACE INTO evolution_knowledge_bottlenecks (
                bottleneck_id, area, description, recurrence_count,
                first_seen, last_seen, related_ids, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("bottleneck_id"),
            data.get("area", ""),
            data.get("description", ""),
            data.get("recurrence_count", 1),
            data.get("first_seen", ""),
            data.get("last_seen", ""),
            self._to_json(data.get("related_ids", [])),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_knowledge_bottlenecks(self) -> list[dict]:
        """Load all stored knowledge bottlenecks, oldest first."""
        cursor = self._execute(
            "SELECT * FROM evolution_knowledge_bottlenecks ORDER BY first_seen ASC"
        )
        return [self._row_to_knowledge_bottleneck(row) for row in cursor.fetchall()]

    def _row_to_knowledge_bottleneck(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a bottleneck profile dictionary."""
        return {
            "bottleneck_id": row["bottleneck_id"],
            "area": row["area"],
            "description": row["description"],
            "recurrence_count": row["recurrence_count"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "related_ids": self._from_json(row["related_ids"]) or [],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    def store_knowledge_snapshot(self, data: dict) -> None:
        """Persist a single knowledge snapshot dictionary."""
        sql = """
            INSERT OR REPLACE INTO evolution_knowledge_snapshots (
                snapshot_id, timestamp, pattern_count, strategy_count,
                capability_count, bottleneck_count, summary_text, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("snapshot_id"),
            data.get("timestamp", ""),
            data.get("pattern_count", 0),
            data.get("strategy_count", 0),
            data.get("capability_count", 0),
            data.get("bottleneck_count", 0),
            data.get("summary_text", ""),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_knowledge_snapshots(self) -> list[dict]:
        """Load all stored knowledge snapshots, oldest first."""
        cursor = self._execute(
            "SELECT * FROM evolution_knowledge_snapshots ORDER BY timestamp ASC"
        )
        return [self._row_to_knowledge_snapshot(row) for row in cursor.fetchall()]

    def _row_to_knowledge_snapshot(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a knowledge snapshot dictionary."""
        return {
            "snapshot_id": row["snapshot_id"],
            "timestamp": row["timestamp"],
            "pattern_count": row["pattern_count"],
            "strategy_count": row["strategy_count"],
            "capability_count": row["capability_count"],
            "bottleneck_count": row["bottleneck_count"],
            "summary_text": row["summary_text"],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    # ------------------------------------------------------------------
    # Persistent learning insights (Persistent Learning)
    # ------------------------------------------------------------------

    def store_learning_insight(self, data: dict) -> None:
        """Persist a single reusable learning insight dictionary."""
        sql = """
            INSERT OR REPLACE INTO learning_insights (
                insight_id, category, title, description, importance,
                confidence, observation_count, source_pipeline_ids,
                reusable, applicable_areas, created_at, last_updated, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("insight_id"),
            data.get("category", ""),
            data.get("title", ""),
            data.get("description", ""),
            data.get("importance", "MEDIUM"),
            data.get("confidence", 0.5),
            data.get("observation_count", 1),
            self._to_json(data.get("source_pipeline_ids", [])),
            1 if data.get("reusable", True) else 0,
            self._to_json(data.get("applicable_areas", [])),
            data.get("created_at", ""),
            data.get("last_updated", ""),
            self._to_json(data.get("metadata", {})),
        )
        self._run_write(sql, params)

    def load_learning_insights(self) -> list[dict]:
        """Load all stored learning insights, oldest first."""
        cursor = self._execute(
            "SELECT * FROM learning_insights ORDER BY created_at ASC"
        )
        return [self._row_to_learning_insight(row) for row in cursor.fetchall()]

    def _row_to_learning_insight(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a learning insight dictionary."""
        return {
            "insight_id": row["insight_id"],
            "category": row["category"],
            "title": row["title"],
            "description": row["description"],
            "importance": row["importance"],
            "confidence": row["confidence"],
            "observation_count": row["observation_count"],
            "source_pipeline_ids": self._from_json(row["source_pipeline_ids"]) or [],
            "reusable": bool(row["reusable"]),
            "applicable_areas": self._from_json(row["applicable_areas"]) or [],
            "created_at": row["created_at"],
            "last_updated": row["last_updated"],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    # ------------------------------------------------------------------
    # Administration
    # ------------------------------------------------------------------

    def clear_all(self) -> None:
        """Remove all persisted evolution data. Use with caution, mainly for tests."""
        if not self.is_available():
            return
        conn = self._conn
        if conn is None:
            return
        try:
            with conn:
                conn.execute("DELETE FROM evolution_proposals")
                conn.execute("DELETE FROM evolution_approval_requests")
                conn.execute("DELETE FROM evolution_records")
                conn.execute("DELETE FROM evolution_insights")
                conn.execute("DELETE FROM evolution_observations")
                conn.execute("DELETE FROM evolution_knowledge_patterns")
                conn.execute("DELETE FROM evolution_knowledge_strategies")
                conn.execute("DELETE FROM evolution_knowledge_capabilities")
                conn.execute("DELETE FROM evolution_knowledge_bottlenecks")
                conn.execute("DELETE FROM evolution_knowledge_snapshots")
                conn.execute("DELETE FROM learning_insights")
        except sqlite3.Error:
            self._available = False
            raise

    def get_schema_version(self) -> int:
        if self._conn is None:
            return 0
        return migration.get_schema_version(self._conn)

    # ------------------------------------------------------------------
    # Properties (for diagnostics)
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self._db_path
