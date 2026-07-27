"""
Atlas SQLite Experience Storage — Phase 9.1

Infrastructure adapter implementing the ExperienceStorage interface with
SQLite. Owns connection lifecycle, schema management via migration.py,
serialization of nested fields to JSON, and graceful failure handling.

This module is the only place in Phase 9.1 that imports sqlite3.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from atlas.experience.storage_interface import ExperienceStorage
from atlas.storage import migration


logger = logging.getLogger(__name__)


class SQLiteExperienceStorage(ExperienceStorage):
    """
    SQLite-backed persistent storage for experiences, trend analyses,
    tracked goals, and self-model snapshots.

    All data is exchanged as plain dictionaries. Nested lists and dicts are
    stored as JSON strings inside the SQLite tables.

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
            logger.exception("Failed to initialize SQLite experience storage at %s", self._db_path)
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
                logger.exception("Error closing SQLite experience storage")
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

    def _commit(self) -> None:
        """Commit current transaction; mark unavailable on failure."""
        conn = self._conn
        if conn is None:
            return
        try:
            conn.commit()
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
    # Experiences
    # ------------------------------------------------------------------

    def store_experience(self, data: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO experiences (
                experience_id, timestamp, duration_ms, pipeline_path, outcome,
                user_input, conversation_history_length, understanding_insights_count,
                concepts_extracted, world_model_entities, world_model_relations,
                reasoning_goal, reasoning_capabilities, reasoning_success_count,
                reasoning_total_count, planning_goal, planning_step_count,
                planning_validation_errors, tool_name, tool_success,
                learning_insights_count, reflection_suggestions_count,
                goal_recommendations_count, identity_version, identity_belief_count,
                identity_capability_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("experience_id"),
            data.get("timestamp"),
            data.get("duration_ms"),
            self._to_json(data.get("pipeline_path", [])),
            data.get("outcome"),
            data.get("user_input", ""),
            data.get("conversation_history_length", 0),
            data.get("understanding_insights_count", 0),
            self._to_json(data.get("concepts_extracted", [])),
            data.get("world_model_entities", 0),
            data.get("world_model_relations", 0),
            data.get("reasoning_goal", ""),
            self._to_json(data.get("reasoning_capabilities", [])),
            data.get("reasoning_success_count", 0),
            data.get("reasoning_total_count", 0),
            data.get("planning_goal", ""),
            data.get("planning_step_count", 0),
            data.get("planning_validation_errors", 0),
            data.get("tool_name", ""),
            1 if data.get("tool_success") else 0,
            data.get("learning_insights_count", 0),
            data.get("reflection_suggestions_count", 0),
            data.get("goal_recommendations_count", 0),
            data.get("identity_version", 0),
            data.get("identity_belief_count", 0),
            data.get("identity_capability_count", 0),
        )
        self._run_write(sql, params)

    def load_experiences(self, limit: int = 10000) -> list[dict]:
        cursor = self._execute(
            "SELECT * FROM experiences ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        )
        return [self._row_to_experience(row) for row in cursor.fetchall()]

    def load_experience(self, experience_id: str) -> dict | None:
        cursor = self._execute(
            "SELECT * FROM experiences WHERE experience_id = ?",
            (experience_id,),
        )
        row = cursor.fetchone()
        return self._row_to_experience(row) if row else None

    def load_experiences_since(self, iso_timestamp: str) -> list[dict]:
        cursor = self._execute(
            "SELECT * FROM experiences WHERE timestamp >= ? ORDER BY timestamp ASC",
            (iso_timestamp,),
        )
        return [self._row_to_experience(row) for row in cursor.fetchall()]

    def load_experiences_by_outcome(self, outcome: str, limit: int = 100) -> list[dict]:
        cursor = self._execute(
            "SELECT * FROM experiences WHERE outcome = ? ORDER BY timestamp ASC LIMIT ?",
            (outcome, limit),
        )
        return [self._row_to_experience(row) for row in cursor.fetchall()]

    def get_max_experience_id(self) -> int | None:
        cursor = self._execute(
            "SELECT MAX(CAST(SUBSTR(experience_id, 5) AS INTEGER)) FROM experiences"
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    def _row_to_experience(self, row: sqlite3.Row) -> dict:
        return {
            "experience_id": row["experience_id"],
            "timestamp": row["timestamp"],
            "duration_ms": row["duration_ms"],
            "pipeline_path": self._from_json(row["pipeline_path"]) or [],
            "outcome": row["outcome"],
            "user_input": row["user_input"],
            "conversation_history_length": row["conversation_history_length"],
            "understanding_insights_count": row["understanding_insights_count"],
            "concepts_extracted": self._from_json(row["concepts_extracted"]) or [],
            "world_model_entities": row["world_model_entities"],
            "world_model_relations": row["world_model_relations"],
            "reasoning_goal": row["reasoning_goal"],
            "reasoning_capabilities": self._from_json(row["reasoning_capabilities"]) or [],
            "reasoning_success_count": row["reasoning_success_count"],
            "reasoning_total_count": row["reasoning_total_count"],
            "planning_goal": row["planning_goal"],
            "planning_step_count": row["planning_step_count"],
            "planning_validation_errors": row["planning_validation_errors"],
            "tool_name": row["tool_name"],
            "tool_success": bool(row["tool_success"]),
            "learning_insights_count": row["learning_insights_count"],
            "reflection_suggestions_count": row["reflection_suggestions_count"],
            "goal_recommendations_count": row["goal_recommendations_count"],
            "identity_version": row["identity_version"],
            "identity_belief_count": row["identity_belief_count"],
            "identity_capability_count": row["identity_capability_count"],
        }

    # ------------------------------------------------------------------
    # Trend analyses
    # ------------------------------------------------------------------

    def store_analysis(self, data: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO trend_analyses (
                analysis_id, timestamp, window_size, overall_success_rate,
                success_rate_trend, avg_understanding_insights, understanding_trend,
                avg_reasoning_success, reasoning_trend, avg_planning_errors,
                planning_trend, tool_success_rate, tool_trend, learning_insight_rate,
                learning_trend, identity_stability, capability_trends
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("analysis_id"),
            data.get("timestamp"),
            data.get("window_size"),
            data.get("overall_success_rate", 0.0),
            data.get("success_rate_trend", "stable"),
            data.get("avg_understanding_insights", 0.0),
            data.get("understanding_trend", "stable"),
            data.get("avg_reasoning_success", 0.0),
            data.get("reasoning_trend", "stable"),
            data.get("avg_planning_errors", 0.0),
            data.get("planning_trend", "stable"),
            data.get("tool_success_rate", 0.0),
            data.get("tool_trend", "stable"),
            data.get("learning_insight_rate", 0.0),
            data.get("learning_trend", "stable"),
            data.get("identity_stability", 0.0),
            self._to_json(data.get("capability_trends", {})),
        )
        self._run_write(sql, params)

    def load_latest_analysis(self) -> dict | None:
        cursor = self._execute(
            "SELECT * FROM trend_analyses ORDER BY timestamp DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return self._row_to_analysis(row) if row else None

    def load_analyses(self, limit: int = 50) -> list[dict]:
        cursor = self._execute(
            "SELECT * FROM trend_analyses ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        )
        return [self._row_to_analysis(row) for row in cursor.fetchall()]

    def _row_to_analysis(self, row: sqlite3.Row) -> dict:
        return {
            "analysis_id": row["analysis_id"],
            "timestamp": row["timestamp"],
            "window_size": row["window_size"],
            "overall_success_rate": row["overall_success_rate"],
            "success_rate_trend": row["success_rate_trend"],
            "avg_understanding_insights": row["avg_understanding_insights"],
            "understanding_trend": row["understanding_trend"],
            "avg_reasoning_success": row["avg_reasoning_success"],
            "reasoning_trend": row["reasoning_trend"],
            "avg_planning_errors": row["avg_planning_errors"],
            "planning_trend": row["planning_trend"],
            "tool_success_rate": row["tool_success_rate"],
            "tool_trend": row["tool_trend"],
            "learning_insight_rate": row["learning_insight_rate"],
            "learning_trend": row["learning_trend"],
            "identity_stability": row["identity_stability"],
            "capability_trends": self._from_json(row["capability_trends"]) or {},
        }

    # ------------------------------------------------------------------
    # Tracked goals
    # ------------------------------------------------------------------

    def store_tracked_goal(self, data: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO tracked_goals (
                goal_id, recommendation_id, goal_title, proposed_at, outcome,
                outcome_reason, related_experience_ids, last_evaluated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        proposed = data.get("proposed_at") or data.get("timestamp") or ""
        evaluated = data.get("last_evaluated") or data.get("proposed_at") or data.get("timestamp") or ""
        params = (
            data.get("goal_id"),
            data.get("recommendation_id", ""),
            data.get("goal_title", ""),
            proposed,
            data.get("outcome"),
            data.get("outcome_reason", ""),
            self._to_json(data.get("related_experience_ids", [])),
            evaluated,
        )
        self._run_write(sql, params)

    def load_tracked_goals(self) -> list[dict]:
        cursor = self._execute("SELECT * FROM tracked_goals ORDER BY proposed_at ASC")
        return [self._row_to_goal(row) for row in cursor.fetchall()]

    def _row_to_goal(self, row: sqlite3.Row) -> dict:
        return {
            "goal_id": row["goal_id"],
            "recommendation_id": row["recommendation_id"],
            "goal_title": row["goal_title"],
            "proposed_at": row["proposed_at"],
            "outcome": row["outcome"],
            "outcome_reason": row["outcome_reason"],
            "related_experience_ids": self._from_json(row["related_experience_ids"]) or [],
            "last_evaluated": row["last_evaluated"],
        }

    # ------------------------------------------------------------------
    # Self-model snapshots
    # ------------------------------------------------------------------

    def store_snapshot(self, data: dict) -> None:
        sql = """
            INSERT OR REPLACE INTO self_model_snapshots (
                snapshot_id, timestamp, total_experiences, overall_success_rate,
                capability_assessments, belief_evidence, trend_summary,
                identity_version, last_trend_analysis, recent_improvement_evidence,
                persistent_challenges
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("snapshot_id"),
            data.get("timestamp"),
            data.get("total_experiences"),
            data.get("overall_success_rate"),
            self._to_json(data.get("capability_assessments", {})),
            self._to_json(data.get("belief_evidence", {})),
            data.get("trend_summary", ""),
            data.get("identity_version", 0),
            data.get("last_trend_analysis"),
            self._to_json(data.get("recent_improvement_evidence", [])),
            self._to_json(data.get("persistent_challenges", [])),
        )
        self._run_write(sql, params)

    def load_latest_snapshot(self) -> dict | None:
        cursor = self._execute(
            "SELECT * FROM self_model_snapshots ORDER BY timestamp DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return self._row_to_snapshot(row) if row else None

    def load_snapshots(self, limit: int = 20) -> list[dict]:
        cursor = self._execute(
            "SELECT * FROM self_model_snapshots ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        )
        return [self._row_to_snapshot(row) for row in cursor.fetchall()]

    def get_max_snapshot_id(self) -> int | None:
        cursor = self._execute(
            "SELECT MAX(CAST(SUBSTR(snapshot_id, 6) AS INTEGER)) FROM self_model_snapshots"
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    def _row_to_snapshot(self, row: sqlite3.Row) -> dict:
        return {
            "snapshot_id": row["snapshot_id"],
            "timestamp": row["timestamp"],
            "total_experiences": row["total_experiences"],
            "overall_success_rate": row["overall_success_rate"],
            "capability_assessments": self._from_json(row["capability_assessments"]) or {},
            "belief_evidence": self._from_json(row["belief_evidence"]) or {},
            "trend_summary": row["trend_summary"],
            "identity_version": row["identity_version"],
            "last_trend_analysis": row["last_trend_analysis"],
            "recent_improvement_evidence": self._from_json(row["recent_improvement_evidence"]) or [],
            "persistent_challenges": self._from_json(row["persistent_challenges"]) or [],
        }

    # ------------------------------------------------------------------
    # Administration
    # ------------------------------------------------------------------

    def clear_all(self) -> None:
        """Drop all data tables. Useful mainly for tests."""
        if not self.is_available():
            return
        conn = self._conn
        if conn is None:
            return
        try:
            with conn:
                conn.execute("DELETE FROM experiences")
                conn.execute("DELETE FROM trend_analyses")
                conn.execute("DELETE FROM tracked_goals")
                conn.execute("DELETE FROM self_model_snapshots")
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
