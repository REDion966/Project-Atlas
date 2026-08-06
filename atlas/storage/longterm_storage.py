"""Atlas Long-Term Learning — SQLite Storage (Track C, Batch 5).

Persistence adapter for Track C long-term learning artifacts. Additive
tables only (``episodic_*``, ``procedural_*``, ``memory_consolidation_records``),
appended to the shared ``atlas_data/atlas_experience.db`` via the migration
framework. Append-only where appropriate.

Persistence ONLY: no business logic, no gateway, no kernel, no dispatcher.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas.longterm.models import (
    ConsolidationRecord,
    ConsolidationStatus,
    Episode,
    EpisodeEvent,
    EpisodeKind,
    Procedure,
    ProcedureKind,
    ProcedureStep,
)
from atlas.longterm.storage_protocol import LongTermStorage
from atlas.storage import migration


logger = logging.getLogger(__name__)


class LongTermSQLiteStorage(LongTermStorage):
    """SQLite-backed persistence for Track C long-term artifacts."""

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
            logger.exception("Failed to initialize long-term storage at %s", self._db_path)
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
                logger.exception("Error closing long-term storage")
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
    # Episodes (idempotent upsert by episode_id)
    # ------------------------------------------------------------------

    def store_episode(self, episode: Episode) -> None:
        self._run_write(
            """
            INSERT OR REPLACE INTO episodic_episodes (
                episode_id, kind, title, summary, outcome,
                source_experience_id, started_at, ended_at, importance,
                tags, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode.episode_id,
                episode.kind.name,
                episode.title,
                episode.summary,
                episode.outcome,
                episode.source_experience_id,
                episode.started_at.isoformat(),
                episode.ended_at.isoformat() if episode.ended_at else None,
                episode.importance,
                self._to_json(list(episode.tags)),
                self._to_json(episode.metadata),
            ),
        )
        for event in episode.events:
            self.store_episode_event(event)

    def load_episodes(self) -> list[Episode]:
        cursor = self._execute(
            "SELECT episode_id, kind, title, summary, outcome, "
            "source_experience_id, started_at, ended_at, importance, tags, metadata "
            "FROM episodic_episodes ORDER BY started_at ASC, episode_id ASC"
        )
        events_by_episode: dict[str, list[EpisodeEvent]] = {}
        for event in self.load_episode_events_for_all():
            events_by_episode.setdefault(event.episode_id, []).append(event)
        return [
            Episode(
                episode_id=row["episode_id"],
                kind=EpisodeKind[row["kind"]],
                title=row["title"],
                summary=row["summary"],
                events=tuple(
                    sorted(
                        events_by_episode.get(row["episode_id"], []),
                        key=lambda e: e.sequence,
                    )
                ),
                outcome=row["outcome"],
                source_experience_id=row["source_experience_id"],
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=(
                    datetime.fromisoformat(row["ended_at"])
                    if row["ended_at"]
                    else None
                ),
                importance=row["importance"],
                tags=tuple(self._from_json_list(row["tags"])),
                metadata=self._from_json_dict(row["metadata"]),
            )
            for row in cursor.fetchall()
        ]

    def load_episode(self, episode_id: str) -> Episode | None:
        cursor = self._execute(
            "SELECT episode_id, kind, title, summary, outcome, "
            "source_experience_id, started_at, ended_at, importance, tags, metadata "
            "FROM episodic_episodes WHERE episode_id = ?",
            (episode_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        events: list[EpisodeEvent] = [
            e
            for e in self.load_episode_events(episode_id)
            if e.episode_id == episode_id
        ]
        return Episode(
            episode_id=row["episode_id"],
            kind=EpisodeKind[row["kind"]],
            title=row["title"],
            summary=row["summary"],
            events=tuple(sorted(events, key=lambda e: e.sequence)),
            outcome=row["outcome"],
            source_experience_id=row["source_experience_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=(
                datetime.fromisoformat(row["ended_at"])
                if row["ended_at"]
                else None
            ),
            importance=row["importance"],
            tags=tuple(self._from_json_list(row["tags"])),
            metadata=self._from_json_dict(row["metadata"]),
        )

    # ------------------------------------------------------------------
    # Episode events (append-only log)
    # ------------------------------------------------------------------

    def store_episode_event(self, event: EpisodeEvent) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO episodic_episode_events (
                event_id, episode_id, sequence, event_type, summary,
                occurred_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.episode_id,
                event.sequence,
                event.event_type,
                event.summary,
                event.occurred_at.isoformat(),
                self._to_json(event.metadata),
            ),
        )

    def load_episode_events(self, episode_id: str) -> list[EpisodeEvent]:
        cursor = self._execute(
            "SELECT event_id, episode_id, sequence, event_type, summary, "
            "occurred_at, metadata "
            "FROM episodic_episode_events WHERE episode_id = ? "
            "ORDER BY sequence ASC, event_id ASC",
            (episode_id,),
        )
        return [self._event_from_row(row) for row in cursor.fetchall()]

    def load_episode_events_for_all(self) -> list[EpisodeEvent]:
        """Load all episode events (used by :meth:`load_episodes`)."""
        cursor = self._execute(
            "SELECT event_id, episode_id, sequence, event_type, summary, "
            "occurred_at, metadata FROM episodic_episode_events "
            "ORDER BY sequence ASC, event_id ASC"
        )
        return [self._event_from_row(row) for row in cursor.fetchall()]

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> EpisodeEvent:
        return EpisodeEvent(
            event_id=row["event_id"],
            episode_id=row["episode_id"],
            sequence=row["sequence"],
            event_type=row["event_type"],
            summary=row["summary"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    # ------------------------------------------------------------------
    # Procedures (idempotent upsert by procedure_id)
    # ------------------------------------------------------------------

    def store_procedure(self, procedure: Procedure) -> None:
        self._run_write(
            """
            INSERT OR REPLACE INTO procedural_procedures (
                procedure_id, name, description, kind, category,
                source_episode_ids, success_count, failure_count, confidence,
                created_at, last_used_at, tags, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                procedure.procedure_id,
                procedure.name,
                procedure.description,
                procedure.kind.name,
                procedure.category,
                self._to_json(list(procedure.source_episode_ids)),
                procedure.success_count,
                procedure.failure_count,
                procedure.confidence,
                procedure.created_at.isoformat(),
                procedure.last_used_at.isoformat() if procedure.last_used_at else None,
                self._to_json(list(procedure.tags)),
                self._to_json(procedure.metadata),
            ),
        )
        for step in procedure.steps:
            self.store_procedure_step(procedure.procedure_id, step)

    def store_procedure_step(self, procedure_id: str, step: ProcedureStep) -> None:
        """Persist one step for a procedure (idempotent upsert)."""
        self._run_write(
            """
            INSERT OR REPLACE INTO procedural_procedure_steps (
                procedure_id, step_id, description, tool_name, parameters, depends_on
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                procedure_id,
                step.step_id,
                step.description,
                step.tool_name,
                self._to_json(step.parameters),
                self._to_json(list(step.depends_on)),
            ),
        )

    def load_procedures(self) -> list[Procedure]:
        cursor = self._execute(
            "SELECT procedure_id, name, description, kind, category, "
            "source_episode_ids, success_count, failure_count, confidence, "
            "created_at, last_used_at, tags, metadata "
            "FROM procedural_procedures ORDER BY created_at ASC, procedure_id ASC"
        )
        steps_by_procedure: dict[str, list[ProcedureStep]] = (
            self._load_all_steps_grouped()
        )
        return [

            Procedure(
                procedure_id=row["procedure_id"],
                name=row["name"],
                description=row["description"],
                kind=ProcedureKind[row["kind"]],
                category=row["category"],
                steps=tuple(
                    sorted(
                        steps_by_procedure.get(row["procedure_id"], []),
                        key=lambda s: s.step_id,
                    )
                ),
                source_episode_ids=tuple(
                    self._from_json_list(row["source_episode_ids"])
                ),
                success_count=row["success_count"],
                failure_count=row["failure_count"],
                confidence=row["confidence"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_used_at=(
                    datetime.fromisoformat(row["last_used_at"])
                    if row["last_used_at"]
                    else None
                ),
                tags=tuple(self._from_json_list(row["tags"])),
                metadata=self._from_json_dict(row["metadata"]),
            )
            for row in cursor.fetchall()
        ]

    def load_procedure(self, procedure_id: str) -> Procedure | None:
        cursor = self._execute(
            "SELECT procedure_id, name, description, kind, category, "
            "source_episode_ids, success_count, failure_count, confidence, "
            "created_at, last_used_at, tags, metadata "
            "FROM procedural_procedures WHERE procedure_id = ?",
            (procedure_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        steps = self._load_all_steps_grouped().get(procedure_id, [])

        return Procedure(
            procedure_id=row["procedure_id"],
            name=row["name"],
            description=row["description"],
            kind=ProcedureKind[row["kind"]],
            category=row["category"],
            steps=tuple(sorted(steps, key=lambda s: s.step_id)),
            source_episode_ids=tuple(
                self._from_json_list(row["source_episode_ids"])
            ),
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_used_at=(
                datetime.fromisoformat(row["last_used_at"])
                if row["last_used_at"]
                else None
            ),
            tags=tuple(self._from_json_list(row["tags"])),
            metadata=self._from_json_dict(row["metadata"]),
        )

    def _load_all_steps_grouped(self) -> dict[str, list[ProcedureStep]]:
        """Load all steps grouped by procedure id (deterministic)."""
        cursor = self._execute(
            "SELECT procedure_id, step_id, description, tool_name, parameters, "
            "depends_on FROM procedural_procedure_steps "
            "ORDER BY step_id ASC, procedure_id ASC"
        )
        grouped: dict[str, list[ProcedureStep]] = {}
        for row in cursor.fetchall():
            grouped.setdefault(
                row["procedure_id"],
                [],
            ).append(
                ProcedureStep(
                    step_id=row["step_id"],
                    description=row["description"],
                    tool_name=row["tool_name"],
                    parameters=self._from_json_dict(row["parameters"]),
                    depends_on=tuple(self._from_json_list(row["depends_on"])),
                )
            )
        return grouped

    # ------------------------------------------------------------------
    # Consolidation records (append-only log)
    # ------------------------------------------------------------------


    def store_consolidation_record(self, record: ConsolidationRecord) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO memory_consolidation_records (
                record_id, status, operation, target_type, target_ids,
                reason, created_at, applied_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.record_id,
                record.status.name,
                record.operation,
                record.target_type,
                self._to_json(list(record.target_ids)),
                record.reason,
                record.created_at.isoformat(),
                record.applied_at.isoformat() if record.applied_at else None,
                self._to_json(record.metadata),
            ),
        )

    def load_consolidation_records(self) -> list[ConsolidationRecord]:
        cursor = self._execute(
            "SELECT record_id, status, operation, target_type, target_ids, "
            "reason, created_at, applied_at, metadata "
            "FROM memory_consolidation_records "
            "ORDER BY created_at ASC, record_id ASC"
        )
        return [
            ConsolidationRecord(
                record_id=row["record_id"],
                status=ConsolidationStatus[row["status"]],
                operation=row["operation"],
                target_type=row["target_type"],
                target_ids=tuple(self._from_json_list(row["target_ids"])),
                reason=row["reason"],
                created_at=datetime.fromisoformat(row["created_at"]),
                applied_at=(
                    datetime.fromisoformat(row["applied_at"])
                    if row["applied_at"]
                    else None
                ),
                metadata=self._from_json_dict(row["metadata"]),
            )
            for row in cursor.fetchall()
        ]

    def get_schema_version(self) -> int:
        """Return the current schema version without applying migrations."""
        if self._conn is None:
            return 0
        return migration.get_schema_version(self._conn)

    @property
    def db_path(self) -> Path:
        return self._db_path
