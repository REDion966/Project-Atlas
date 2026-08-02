"""
Atlas Autonomy SQLite Storage — Phase 16.4

Infrastructure adapter for the Phase 16 autonomous evolution persistence
layer. Implements the six additive tables described in the architecture:

- evolution_requests
- evolution_versions
- evolution_receipts
- evolution_snapshots
- evolution_outcomes
- staged_config

All data is exchanged as autonomy dataclasses. Nested fields are serialized
as JSON via ``atlas.evolution.autonomy.serialization``.

This module is the only place in the autonomy persistence layer that
imports sqlite3 directly.

Pure infrastructure. No business logic. No AI. No gateway.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas.evolution.autonomy.models import (
    AtlasStateVersion,
    AuthorizationMode,
    ChangeReceipt,
    EvolutionAuthorization,
    EvolutionOutcomeRecord,
    EvolutionRequest,
    EvolutionRequestStatus,
    EvolutionSchedule,
    RiskAssessment,
    RiskLevel,
    RollbackPlan,
    StagedConfigEntry,
    ValidationReport,
    VerificationResult,
    VersionTarget,
)
from atlas.evolution.autonomy.serialization import from_serializable, to_serializable
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel
from atlas.storage import migration


logger = logging.getLogger(__name__)


class AutonomySQLiteStorage:
    """
    SQLite-backed persistent storage for Phase 16 autonomous evolution.

    Reuses the existing atlas_data/atlas_experience.db database file and
    migration framework. All writes are committed inside SQLite transactions.

    Graceful degradation: any write or read failure marks the adapter as
    unavailable so callers can fall back to memory-only operation.
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
            logger.exception("Failed to initialize autonomy storage at %s", self._db_path)
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
                logger.exception("Error closing autonomy storage")
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

    @staticmethod
    def _to_json(value: Any) -> str:
        """Serialize a value to a JSON string."""
        return json.dumps(to_serializable(value), ensure_ascii=False)

    @staticmethod
    def _from_json(value: str | None) -> Any:
        """Deserialize a JSON string back to a Python object."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    # Evolution requests
    # ------------------------------------------------------------------

    def store_request(self, request: EvolutionRequest) -> None:
        """Persist an ``EvolutionRequest`` (insert or replace)."""
        sql = """
            INSERT OR REPLACE INTO evolution_requests (
                request_id, source, target_scope, change_payload, intended_level,
                status, validation, risk, authorization, schedule, version_target,
                rollback, receipt, verification, outcome, parent_request_ids,
                created_at, updated_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            request.request_id,
            request.source,
            request.target_scope.name,
            self._to_json(request.change_payload),
            request.intended_level.name,
            request.status.name,
            self._to_json(request.validation),
            self._to_json(request.risk),
            self._to_json(request.authorization),
            self._to_json(request.schedule),
            self._to_json(request.version_target),
            self._to_json(request.rollback),
            self._to_json(request.receipt),
            self._to_json(request.verification),
            self._to_json(request.outcome),
            self._to_json(request.parent_request_ids),
            request.created_at.isoformat(),
            request.updated_at.isoformat(),
            self._to_json(request.metadata),
        )
        self._run_write(sql, params)

    def load_request(self, request_id: str) -> EvolutionRequest | None:
        """Load a single ``EvolutionRequest`` by ID."""
        cursor = self._execute(
            "SELECT * FROM evolution_requests WHERE request_id = ?",
            (request_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_request(row)

    def load_requests(
        self,
        status: str | None = None,
        target_scope: str | None = None,
    ) -> list[EvolutionRequest]:
        """Load requests, optionally filtered by status and/or target scope."""
        conditions: list[str] = []
        params: list[Any] = []
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if target_scope is not None:
            conditions.append("target_scope = ?")
            params.append(target_scope)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM evolution_requests {where} ORDER BY updated_at ASC"
        cursor = self._execute(sql, tuple(params))
        return [self._row_to_request(row) for row in cursor.fetchall()]

    def delete_request(self, request_id: str) -> None:
        """Delete a request by ID (mainly for tests)."""
        self._run_write(
            "DELETE FROM evolution_requests WHERE request_id = ?",
            (request_id,),
        )

    def update_status(
        self,
        request_id: str,
        expected_status: str,
        new_status: str,
        updated_at: str,
    ) -> bool:
        """Atomic compare-and-swap status update.

        Returns True if the row existed with the expected status and was
        updated, False otherwise.
        """
        sql = """
            UPDATE evolution_requests
            SET status = ?, updated_at = ?
            WHERE request_id = ? AND status = ?
        """
        try:
            with self._conn:  # type: ignore[union-attr]
                cursor = self._conn.execute(sql, (new_status, updated_at, request_id, expected_status))  # type: ignore[union-attr]
                return cursor.rowcount == 1
        except sqlite3.Error:
            self._available = False
            raise

    def count_requests(
        self,
        status: str | None = None,
        authorization_mode: str | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
    ) -> int:
        """Count requests matching optional filters.

        ``window_start`` and ``window_end`` filter on ``updated_at``.
        """
        conditions: list[str] = []
        params: list[Any] = []
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if authorization_mode is not None:
            conditions.append("authorization LIKE ?")
            params.append(f'%"mode": "{authorization_mode}"%')
        if window_start is not None:
            conditions.append("updated_at >= ?")
            params.append(window_start)
        if window_end is not None:
            conditions.append("updated_at <= ?")
            params.append(window_end)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT COUNT(*) FROM evolution_requests {where}"
        cursor = self._execute(sql, tuple(params))
        row = cursor.fetchone()
        return row[0] if row else 0

    def _row_to_request(self, row: sqlite3.Row) -> EvolutionRequest:
        """Convert an SQLite row to an ``EvolutionRequest``."""
        outcome_data = self._from_json(row["outcome"])
        outcome: EvolutionOutcomeRecord | None = None
        if isinstance(outcome_data, dict):
            outcome = from_serializable(outcome_data, EvolutionOutcomeRecord)

        return EvolutionRequest(
            request_id=row["request_id"],
            source=row["source"],
            target_scope=ScopeType[row["target_scope"]],
            change_payload=self._from_json(row["change_payload"]) or {},
            intended_level=ExecutionLevel[row["intended_level"]],
            status=EvolutionRequestStatus[row["status"]],
            validation=from_serializable(self._from_json(row["validation"]), ValidationReport),
            risk=from_serializable(self._from_json(row["risk"]), RiskAssessment),
            authorization=from_serializable(self._from_json(row["authorization"]), EvolutionAuthorization),
            schedule=from_serializable(self._from_json(row["schedule"]), EvolutionSchedule),
            version_target=from_serializable(self._from_json(row["version_target"]), VersionTarget),
            rollback=from_serializable(self._from_json(row["rollback"]), RollbackPlan),
            receipt=from_serializable(self._from_json(row["receipt"]), ChangeReceipt),
            verification=from_serializable(self._from_json(row["verification"]), VerificationResult),
            outcome=outcome,
            parent_request_ids=self._from_json(row["parent_request_ids"]) or [],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=self._from_json(row["metadata"]) or {},
        )

    # ------------------------------------------------------------------
    # Versions
    # ------------------------------------------------------------------

    def store_version(self, version: AtlasStateVersion) -> None:
        """Persist an ``AtlasStateVersion`` manifest."""
        sql = """
            INSERT OR REPLACE INTO evolution_versions (
                manifest_id, major, minor, patch, applied_request_ids,
                parent_version, scope_versions, tags, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            version.manifest_id,
            version.major,
            version.minor,
            version.patch,
            self._to_json(version.applied_request_ids),
            version.parent_version,
            self._to_json(version.scope_versions),
            self._to_json(version.tags),
            version.created_at.isoformat(),
        )
        self._run_write(sql, params)

    def load_latest_version(self) -> AtlasStateVersion | None:
        """Load the most recently created ``AtlasStateVersion``."""
        cursor = self._execute(
            "SELECT * FROM evolution_versions ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return AtlasStateVersion(
            major=row["major"],
            minor=row["minor"],
            patch=row["patch"],
            manifest_id=row["manifest_id"],
            applied_request_ids=self._from_json(row["applied_request_ids"]) or [],
            parent_version=row["parent_version"],
            scope_versions=self._from_json(row["scope_versions"]) or {},
            tags=self._from_json(row["tags"]) or [],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ------------------------------------------------------------------
    # Receipts
    # ------------------------------------------------------------------

    def store_receipt(self, receipt: ChangeReceipt) -> None:
        """Persist a ``ChangeReceipt``."""
        sql = """
            INSERT OR REPLACE INTO evolution_receipts (
                receipt_id, request_id, changed_keys, before_refs, after_refs,
                version_delta, target_tags, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            f"rec-{receipt.request_id}",
            receipt.request_id,
            self._to_json(receipt.changed_keys),
            self._to_json(receipt.before_refs),
            self._to_json(receipt.after_refs),
            receipt.version_delta,
            self._to_json(receipt.target_tags),
            receipt.applied_at.isoformat(),
        )
        self._run_write(sql, params)

    def load_receipt(self, request_id: str) -> ChangeReceipt | None:
        """Load a ``ChangeReceipt`` by request ID."""
        cursor = self._execute(
            "SELECT * FROM evolution_receipts WHERE request_id = ?",
            (request_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ChangeReceipt(
            request_id=row["request_id"],
            changed_keys=self._from_json(row["changed_keys"]) or [],
            before_refs=self._from_json(row["before_refs"]) or {},
            after_refs=self._from_json(row["after_refs"]) or {},
            version_delta=row["version_delta"],
            target_tags=self._from_json(row["target_tags"]) or [],
            applied_at=datetime.fromisoformat(row["applied_at"]),
        )

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def store_snapshot(
        self,
        snapshot_id: str,
        request_id: str,
        snapshot_data: dict[str, Any],
        checksum: str,
        created_at: str,
    ) -> None:
        """Persist a store-level rollback snapshot artifact."""
        sql = """
            INSERT OR REPLACE INTO evolution_snapshots (
                snapshot_id, request_id, snapshot_data, checksum, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """
        params = (
            snapshot_id,
            request_id,
            self._to_json(snapshot_data),
            checksum,
            created_at,
        )
        self._run_write(sql, params)

    def load_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """Load a snapshot artifact by ID."""
        cursor = self._execute(
            "SELECT * FROM evolution_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._from_json(row["snapshot_data"]) or {}

    # ------------------------------------------------------------------
    # Outcomes
    # ------------------------------------------------------------------

    def store_outcome(self, outcome: EvolutionOutcomeRecord) -> None:
        """Persist an ``EvolutionOutcomeRecord``."""
        sql = """
            INSERT OR REPLACE INTO evolution_outcomes (
                outcome_record_id, request_id, scope, area, risk_level,
                intended_level, authorization_mode, outcome, verification_passed,
                rollback_occurred, effectiveness_proxy, started_at, finished_at,
                related_ids, strategy_key, strategy_name, planning_context_version,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            outcome.outcome_record_id,
            outcome.request_id,
            outcome.scope.name,
            outcome.area,
            outcome.risk_level.name,
            outcome.intended_level.name,
            outcome.authorization_mode.name,
            outcome.outcome,
            1 if outcome.verification_passed else 0,
            1 if outcome.rollback_occurred else 0,
            outcome.effectiveness_proxy,
            outcome.started_at.isoformat(),
            outcome.finished_at.isoformat(),
            self._to_json(outcome.related_ids),
            outcome.strategy_key,
            outcome.strategy_name,
            outcome.planning_context_version,
            self._to_json(outcome.metadata),
        )
        self._run_write(sql, params)

    def load_outcome(self, request_id: str) -> EvolutionOutcomeRecord | None:
        """Load an outcome record by request ID."""
        cursor = self._execute(
            "SELECT * FROM evolution_outcomes WHERE request_id = ?",
            (request_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return EvolutionOutcomeRecord(
            outcome_record_id=row["outcome_record_id"],
            request_id=row["request_id"],
            scope=ScopeType[row["scope"]],
            area=row["area"],
            risk_level=RiskLevel[row["risk_level"]],
            intended_level=ExecutionLevel[row["intended_level"]],
            authorization_mode=AuthorizationMode[row["authorization_mode"]],
            outcome=row["outcome"],
            verification_passed=bool(row["verification_passed"]),
            rollback_occurred=bool(row["rollback_occurred"]),
            effectiveness_proxy=row["effectiveness_proxy"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]),
            related_ids=self._from_json(row["related_ids"]) or [],
            strategy_key=row["strategy_key"],
            strategy_name=row["strategy_name"],
            planning_context_version=row["planning_context_version"],
            metadata=self._from_json(row["metadata"]) or {},
        )

    # ------------------------------------------------------------------
    # Staged config
    # ------------------------------------------------------------------

    def store_staged_config(self, entry: StagedConfigEntry) -> None:
        """Persist a ``StagedConfigEntry``."""
        sql = """
            INSERT OR REPLACE INTO staged_config (
                entry_id, request_id, key, value, schema_status,
                activated_at, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            entry.entry_id,
            entry.request_id,
            entry.key,
            self._to_json(entry.value),
            entry.schema_status,
            entry.activated_at.isoformat() if entry.activated_at else None,
            entry.applied_at.isoformat(),
        )
        self._run_write(sql, params)

    def load_staged_configs(self, request_id: str | None = None) -> list[StagedConfigEntry]:
        """Load staged config entries, optionally filtered by request ID."""
        if request_id is not None:
            sql = "SELECT * FROM staged_config WHERE request_id = ? ORDER BY applied_at ASC"
            params: tuple[Any, ...] = (request_id,)
        else:
            sql = "SELECT * FROM staged_config ORDER BY applied_at ASC"
            params = ()
        cursor = self._execute(sql, params)
        entries = []
        for row in cursor.fetchall():
            activated_at = row["activated_at"]
            entries.append(
                StagedConfigEntry(
                    entry_id=row["entry_id"],
                    request_id=row["request_id"],
                    key=row["key"],
                    value=self._from_json(row["value"]),
                    schema_status=row["schema_status"],
                    activated_at=datetime.fromisoformat(activated_at) if activated_at else None,
                    applied_at=datetime.fromisoformat(row["applied_at"]),
                )
            )
        return entries

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def schema_version(self) -> int:
        """Return the current schema version."""
        if not self.is_available() or self._conn is None:
            raise sqlite3.OperationalError("Storage is unavailable")
        return migration.get_schema_version(self._conn)
