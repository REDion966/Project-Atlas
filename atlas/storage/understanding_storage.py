"""
Atlas SQLite Understanding Storage — Phase 9.2b

Infrastructure adapter implementing the UnderstandingStorage interface with
SQLite. Owns connection lifecycle, schema management via migration.py,
serialization of nested fields to JSON, and graceful failure handling.

This module is the only place in Phase 9.2b that imports sqlite3.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from atlas.storage import migration
from atlas.understanding.storage_interface import UnderstandingStorage


logger = logging.getLogger(__name__)


class SQLiteUnderstandingStorage(UnderstandingStorage):
    """
    SQLite-backed persistent storage for understanding data.

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
            logger.exception("Failed to initialize SQLite understanding storage at %s", self._db_path)
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
                logger.exception("Error closing SQLite understanding storage")
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
    def _clamp_int(value: Any, default: int) -> int:
        """Clamp an integer to SQLite's signed 64-bit range.

        Post-Core Hardening — understanding counters (concept/pattern
        frequency, relationship observed_count) are unbounded ``+=``
        accumulators that compound across restore+merge cycles. Without a
        clamp, a persisted counter that converges on 2**63 - 1 overflows
        SQLite's INTEGER column and aborts the batch write. Saturation
        preserves the counter's meaning — more observations than can be
        represented — while keeping writes deterministic and loss-free.

        Non-numeric or missing values fall back to ``default``, matching the
        previous ``get(key, default)`` behavior.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            return default
        max_int64 = 2**63 - 1
        return value if value <= max_int64 else max_int64

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
    # Concepts
    # ------------------------------------------------------------------

    def store_concepts(self, concepts: list[dict]) -> None:
        """Persist a batch of concept dictionaries."""
        if not concepts:
            return
        sql = """
            INSERT OR REPLACE INTO understanding_concepts (
                concept_id, label, domain, confidence, source, frequency,
                first_seen, last_seen, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (
                c.get("concept_id"),
                c.get("label", ""),
                c.get("domain", "GENERAL"),
                c.get("confidence", 0.5),
                c.get("source", ""),
                self._clamp_int(c.get("frequency", 1), 1),
                c.get("first_seen"),
                c.get("last_seen"),
                self._to_json(c.get("metadata", {})),
            )
            for c in concepts
        ]
        if not self.is_available():
            raise sqlite3.OperationalError("Storage is unavailable")
        conn = self._conn
        if conn is None:
            raise sqlite3.OperationalError("Storage connection is closed")
        try:
            with conn:
                conn.executemany(sql, params)
        except sqlite3.Error:
            self._available = False
            raise

    def load_all_concepts(self) -> list[dict]:
        """Load all stored concept dictionaries."""
        cursor = self._execute(
            "SELECT * FROM understanding_concepts ORDER BY first_seen ASC"
        )
        return [self._row_to_concept(row) for row in cursor.fetchall()]

    def _row_to_concept(self, row: sqlite3.Row) -> dict:
        return {
            "concept_id": row["concept_id"],
            "label": row["label"],
            "domain": row["domain"],
            "confidence": row["confidence"],
            "source": row["source"],
            "frequency": row["frequency"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    def store_relationships(self, relationships: list[dict]) -> None:
        """Persist a batch of relationship dictionaries."""
        if not relationships:
            return
        sql = """
            INSERT OR REPLACE INTO understanding_relationships (
                source_id, target_id, relationship_type, weight, confidence,
                observed_count, first_observed, last_observed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (
                r.get("source_id"),
                r.get("target_id"),
                r.get("relationship_type"),
                r.get("weight", 0.5),
                r.get("confidence", 0.5),
                self._clamp_int(r.get("observed_count", 1), 1),
                r.get("first_observed"),
                r.get("last_observed"),
            )
            for r in relationships
        ]
        if not self.is_available():
            raise sqlite3.OperationalError("Storage is unavailable")
        conn = self._conn
        if conn is None:
            raise sqlite3.OperationalError("Storage connection is closed")
        try:
            with conn:
                conn.executemany(sql, params)
        except sqlite3.Error:
            self._available = False
            raise

    def load_all_relationships(self) -> list[dict]:
        """Load all stored relationship dictionaries."""
        cursor = self._execute(
            "SELECT * FROM understanding_relationships ORDER BY first_observed ASC"
        )
        return [self._row_to_relationship(row) for row in cursor.fetchall()]

    def _row_to_relationship(self, row: sqlite3.Row) -> dict:
        return {
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "relationship_type": row["relationship_type"],
            "weight": row["weight"],
            "confidence": row["confidence"],
            "observed_count": row["observed_count"],
            "first_observed": row["first_observed"],
            "last_observed": row["last_observed"],
        }

    # ------------------------------------------------------------------
    # Patterns
    # ------------------------------------------------------------------

    def store_patterns(self, patterns: list[dict]) -> None:
        """Persist a batch of pattern dictionaries."""
        if not patterns:
            return
        sql = """
            INSERT OR REPLACE INTO understanding_patterns (
                pattern_id, label, description, confidence,
                related_concept_ids, frequency, first_observed, last_observed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (
                p.get("pattern_id"),
                p.get("label", ""),
                p.get("description", ""),
                p.get("confidence", 0.5),
                self._to_json(p.get("related_concept_ids", [])),
                self._clamp_int(p.get("frequency", 1), 1),
                p.get("first_observed"),
                p.get("last_observed"),
            )
            for p in patterns
        ]
        if not self.is_available():
            raise sqlite3.OperationalError("Storage is unavailable")
        conn = self._conn
        if conn is None:
            raise sqlite3.OperationalError("Storage connection is closed")
        try:
            with conn:
                conn.executemany(sql, params)
        except sqlite3.Error:
            self._available = False
            raise

    def load_all_patterns(self) -> list[dict]:
        """Load all stored pattern dictionaries."""
        cursor = self._execute(
            "SELECT * FROM understanding_patterns ORDER BY first_observed ASC"
        )
        return [self._row_to_pattern(row) for row in cursor.fetchall()]

    def _row_to_pattern(self, row: sqlite3.Row) -> dict:
        return {
            "pattern_id": row["pattern_id"],
            "label": row["label"],
            "description": row["description"],
            "confidence": row["confidence"],
            "related_concept_ids": self._from_json(row["related_concept_ids"]) or [],
            "frequency": row["frequency"],
            "first_observed": row["first_observed"],
            "last_observed": row["last_observed"],
        }

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def store_insights(self, insights: list[dict]) -> None:
        """Persist a batch of insight dictionaries."""
        if not insights:
            return
        sql = """
            INSERT OR REPLACE INTO understanding_insights (
                insight_id, category, summary, detail, confidence,
                related_concept_ids, related_pattern_ids, source,
                timestamp, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (
                i.get("insight_id"),
                i.get("category"),
                i.get("summary", ""),
                i.get("detail", ""),
                i.get("confidence", 0.5),
                self._to_json(i.get("related_concept_ids", [])),
                self._to_json(i.get("related_pattern_ids", [])),
                i.get("source", ""),
                i.get("timestamp"),
                self._to_json(i.get("metadata", {})),
            )
            for i in insights
        ]
        if not self.is_available():
            raise sqlite3.OperationalError("Storage is unavailable")
        conn = self._conn
        if conn is None:
            raise sqlite3.OperationalError("Storage connection is closed")
        try:
            with conn:
                conn.executemany(sql, params)
        except sqlite3.Error:
            self._available = False
            raise

    def load_all_insights(self) -> list[dict]:
        """Load all stored insight dictionaries."""
        cursor = self._execute(
            "SELECT * FROM understanding_insights ORDER BY timestamp ASC"
        )
        return [self._row_to_insight(row) for row in cursor.fetchall()]

    def _row_to_insight(self, row: sqlite3.Row) -> dict:
        return {
            "insight_id": row["insight_id"],
            "category": row["category"],
            "summary": row["summary"],
            "detail": row["detail"],
            "confidence": row["confidence"],
            "related_concept_ids": self._from_json(row["related_concept_ids"]) or [],
            "related_pattern_ids": self._from_json(row["related_pattern_ids"]) or [],
            "source": row["source"],
            "timestamp": row["timestamp"],
            "metadata": self._from_json(row["metadata"]) or {},
        }

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def store_signals(self, signals: list[dict]) -> None:
        """Persist a batch of behavioral signal dictionaries."""
        if not signals:
            return
        sql = """
            INSERT OR REPLACE INTO understanding_signals (
                signal_id, domain, description, confidence,
                related_concept_ids, source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (
                s.get("signal_id"),
                s.get("domain"),
                s.get("description", ""),
                s.get("confidence", 0.5),
                self._to_json(s.get("related_concept_ids", [])),
                s.get("source", ""),
                s.get("timestamp"),
            )
            for s in signals
        ]
        if not self.is_available():
            raise sqlite3.OperationalError("Storage is unavailable")
        conn = self._conn
        if conn is None:
            raise sqlite3.OperationalError("Storage connection is closed")
        try:
            with conn:
                conn.executemany(sql, params)
        except sqlite3.Error:
            self._available = False
            raise

    def load_all_signals(self) -> list[dict]:
        """Load all stored behavioral signal dictionaries."""
        cursor = self._execute(
            "SELECT * FROM understanding_signals ORDER BY timestamp ASC"
        )
        return [self._row_to_signal(row) for row in cursor.fetchall()]

    def _row_to_signal(self, row: sqlite3.Row) -> dict:
        return {
            "signal_id": row["signal_id"],
            "domain": row["domain"],
            "description": row["description"],
            "confidence": row["confidence"],
            "related_concept_ids": self._from_json(row["related_concept_ids"]) or [],
            "source": row["source"],
            "timestamp": row["timestamp"],
        }

    # ------------------------------------------------------------------
    # Administration
    # ------------------------------------------------------------------

    def clear_all(self) -> None:
        """Remove all persisted understanding data. Use with caution, mainly for tests."""
        if not self.is_available():
            return
        conn = self._conn
        if conn is None:
            return
        try:
            with conn:
                conn.execute("DELETE FROM understanding_concepts")
                conn.execute("DELETE FROM understanding_relationships")
                conn.execute("DELETE FROM understanding_patterns")
                conn.execute("DELETE FROM understanding_insights")
                conn.execute("DELETE FROM understanding_signals")
        except sqlite3.Error:
            self._available = False
            raise

    def get_max_insight_id(self) -> int | None:
        """
        Return the maximum numeric insight ID, or None if empty.

        Only counts IDs matching the 'INS-%' pattern to avoid counting
        bridge-generated IDs (e.g., 'EXP-INS-%').
        """
        cursor = self._execute(
            "SELECT MAX(CAST(SUBSTR(insight_id, 5) AS INTEGER)) "
            "FROM understanding_insights WHERE insight_id LIKE 'INS-%'"
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    # ------------------------------------------------------------------
    # Properties (for diagnostics)
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self._db_path
