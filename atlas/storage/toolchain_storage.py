"""Atlas Toolchain — SQLite Storage (Phase 18.8).

Persistence adapter for Track B toolchain artifacts. Additive tables only
(``toolchain_*``), appended to the shared ``atlas_data/atlas_experience.db``
via the migration framework. Append-only where appropriate.

Persistence ONLY: no business logic, no gateway, no kernel, no dispatcher.

Mirrors :mod:`atlas.storage.research_storage` (Track A) lifecycle exactly:
``initialize()`` opens the connection and applies migrations; ``close()``
shuts down cleanly; ``is_available()`` reports readiness; write methods
run in transactions and mark the adapter unavailable on failure.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas.storage import migration
from atlas.toolchain.models import (
    Skill,
    SkillKind,
    SkillStatus,
    ToolChain,
    ToolChainPlan,
    ToolChainResult,
    ToolEffectivenessRecord,
    ToolStep,
)
from atlas.toolchain.storage_protocol import ToolchainStorage

logger = logging.getLogger(__name__)


class ToolchainSQLiteStorage(ToolchainStorage):
    """SQLite-backed persistence for Track B toolchain artifacts.

    Implements the :class:`~atlas.toolchain.storage_protocol.ToolchainStorage`
    protocol. Lifecycle mirrors :class:`ResearchSQLiteStorage`:

      * ``initialize()`` — open connection, WAL + FK pragmas, apply migrations.
      * ``close()`` — commit + close, mark unavailable.
      * ``is_available()`` — True when connection is live.
      * ``_run_write()`` — transactional write; marks unavailable on error.
      * ``_execute()`` — read query; marks unavailable on error.

    All nested fields (steps, metadata, tags, step_results) are JSON-serialized.
    Datetimes are stored as ISO-format strings and reconstructed on load.
    """

    DEFAULT_DB_PATH = Path("atlas_data/atlas_experience.db")

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialise the adapter with an optional database path.

        Args:
            db_path: Path to the SQLite database file. If ``None``, uses
                the default shared path ``atlas_data/atlas_experience.db``.
        """
        self._db_path: Path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None
        self._available: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Open a connection and apply schema migrations (additive).

        Idempotent: calling ``initialize()`` on an already-open adapter
        is a no-op. On failure, the adapter is marked unavailable and
        the connection (if any) is closed.
        """
        if self.is_available():
            return
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            migration.apply_migrations(self._conn)
            self._available = True
        except Exception:
            logger.exception(
                "Failed to initialize toolchain storage at %s", self._db_path
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
                logger.exception("Error closing toolchain storage")
            finally:
                self._conn = None

    def is_available(self) -> bool:
        """Return True when the adapter is initialized and usable."""
        return self._available and self._conn is not None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _execute(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> sqlite3.Cursor:
        """Run a read query; mark unavailable on error."""
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
        """Parse a JSON string into a dict (empty dict on failure)."""
        try:
            parsed = json.loads(value) if value else {}
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _from_json_list(value: str | None) -> list[Any]:
        """Parse a JSON string into a list (empty list on failure)."""
        try:
            parsed = json.loads(value) if value else []
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _from_json_or_none(value: str | None) -> Any:
        """Parse a JSON string; return None if value is NULL or invalid."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime:
        """Parse an ISO-format string; fall back to now if invalid."""
        if not value:
            return datetime.now()
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return datetime.now()

    # ------------------------------------------------------------------
    # Deserialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _step_from_dict(data: dict[str, Any]) -> ToolStep:
        """Reconstruct a :class:`ToolStep` from a serialized dict."""
        return ToolStep(
            step_id=data.get("step_id", ""),
            tool_name=data.get("tool_name", ""),
            parameters=data.get("parameters", {}),
            depends_on=tuple(data.get("depends_on", ())),
            description=data.get("description", ""),
        )

    def _steps_from_json(self, value: str | None) -> tuple[ToolStep, ...]:
        """Reconstruct a tuple of steps from a JSON string."""
        data: list[Any] = self._from_json_list(value)
        return tuple(self._step_from_dict(s) for s in data if isinstance(s, dict))

    def _chain_from_dict(self, data: dict[str, Any]) -> ToolChain:
        """Reconstruct a :class:`ToolChain` from a serialized dict."""
        steps_raw: Any = data.get("steps", [])
        steps: tuple[ToolStep, ...] = tuple(
            self._step_from_dict(s)
            for s in steps_raw
            if isinstance(s, dict)
        )
        created_at_raw: Any = data.get("created_at")
        if isinstance(created_at_raw, str):
            created_at: datetime = self._parse_datetime(created_at_raw)
        elif isinstance(created_at_raw, datetime):
            created_at = created_at_raw
        else:
            created_at = datetime.now()
        return ToolChain(
            chain_id=data.get("chain_id", ""),
            goal=data.get("goal", ""),
            steps=steps,
            strategy=data.get("strategy", "sequential"),
            created_at=created_at,
            metadata=data.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Skills (idempotent upsert by skill_id)
    # ------------------------------------------------------------------

    def store_skill(self, skill: Skill) -> None:
        """Store or update a skill (INSERT OR REPLACE by skill_id).

        If the skill has a chain, it is serialized as a JSON blob in the
        ``chain`` column. The chain is also stored independently in the
        ``toolchain_chains`` table for standalone queries.
        """
        chain_json: str | None = None
        if skill.chain is not None:
            chain_json = self._to_json(skill.chain.to_dict())
            self.store_chain(skill.chain)

        self._run_write(
            """
            INSERT OR REPLACE INTO toolchain_skills (
                skill_id, name, description, kind, category, tool_name,
                chain, tags, status, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                skill.skill_id,
                skill.name,
                skill.description,
                skill.kind.name,
                skill.category,
                skill.tool_name,
                chain_json,
                self._to_json(list(skill.tags)),
                skill.status.name,
                skill.created_at.isoformat(),
                self._to_json(skill.metadata),
            ),
        )

    def load_skills(self) -> list[Skill]:
        """Load all skills sorted by skill_id."""
        cursor = self._execute(
            "SELECT skill_id, name, description, kind, category, tool_name, "
            "chain, tags, status, created_at, metadata "
            "FROM toolchain_skills ORDER BY skill_id ASC"
        )
        skills: list[Skill] = []
        for row in cursor.fetchall():
            chain_data = self._from_json_or_none(row["chain"])
            chain: ToolChain | None = (
                self._chain_from_dict(chain_data) if isinstance(chain_data, dict) else None
            )
            skills.append(
                Skill(
                    skill_id=row["skill_id"],
                    name=row["name"],
                    description=row["description"],
                    kind=SkillKind[row["kind"]],
                    category=row["category"],
                    tool_name=row["tool_name"],
                    chain=chain,
                    tags=tuple(self._from_json_list(row["tags"])),
                    status=SkillStatus[row["status"]],
                    created_at=self._parse_datetime(row["created_at"]),
                    metadata=self._from_json_dict(row["metadata"]),
                )
            )
        return skills

    # ------------------------------------------------------------------
    # Chains (idempotent upsert by chain_id)
    # ------------------------------------------------------------------

    def store_chain(self, chain: ToolChain) -> None:
        """Store or update a tool chain (INSERT OR REPLACE by chain_id)."""
        self._run_write(
            """
            INSERT OR REPLACE INTO toolchain_chains (
                chain_id, goal, steps, strategy, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chain.chain_id,
                chain.goal,
                self._to_json([s.to_dict() for s in chain.steps]),
                chain.strategy,
                chain.created_at.isoformat(),
                self._to_json(chain.metadata),
            ),
        )

    def load_chains(self) -> list[ToolChain]:
        """Load all chains sorted by created_at."""
        cursor = self._execute(
            "SELECT chain_id, goal, steps, strategy, created_at, metadata "
            "FROM toolchain_chains ORDER BY created_at ASC, chain_id ASC"
        )
        chains: list[ToolChain] = []
        for row in cursor.fetchall():
            chains.append(
                ToolChain(
                    chain_id=row["chain_id"],
                    goal=row["goal"],
                    steps=self._steps_from_json(row["steps"]),
                    strategy=row["strategy"],
                    created_at=self._parse_datetime(row["created_at"]),
                    metadata=self._from_json_dict(row["metadata"]),
                )
            )
        return chains

    # ------------------------------------------------------------------
    # Effectiveness records (append-only log)
    # ------------------------------------------------------------------

    def store_effectiveness_record(self, record: ToolEffectivenessRecord) -> None:
        """Append an effectiveness observation (INSERT OR IGNORE)."""
        self._run_write(
            """
            INSERT OR IGNORE INTO toolchain_effectiveness_records (
                record_id, tool_name, success, execution_time_ms,
                context_hash, skill_id, recorded_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.record_id,
                record.tool_name,
                int(record.success),
                record.execution_time_ms,
                record.context_hash,
                record.skill_id,
                record.recorded_at.isoformat(),
                self._to_json(record.metadata),
            ),
        )

    def load_effectiveness_records(self) -> list[ToolEffectivenessRecord]:
        """Load all effectiveness records sorted by recorded_at."""
        cursor = self._execute(
            "SELECT record_id, tool_name, success, execution_time_ms, "
            "context_hash, skill_id, recorded_at, metadata "
            "FROM toolchain_effectiveness_records "
            "ORDER BY recorded_at ASC, record_id ASC"
        )
        records: list[ToolEffectivenessRecord] = []
        for row in cursor.fetchall():
            records.append(
                ToolEffectivenessRecord(
                    record_id=row["record_id"],
                    tool_name=row["tool_name"],
                    success=bool(row["success"]),
                    execution_time_ms=row["execution_time_ms"],
                    context_hash=row["context_hash"],
                    skill_id=row["skill_id"],
                    recorded_at=self._parse_datetime(row["recorded_at"]),
                    metadata=self._from_json_dict(row["metadata"]),
                )
            )
        return records

    # ------------------------------------------------------------------
    # Plans (idempotent upsert by plan_id)
    # ------------------------------------------------------------------

    def store_plan(self, plan: ToolChainPlan) -> None:
        """Store or update a tool chain plan (INSERT OR REPLACE by plan_id)."""
        self._run_write(
            """
            INSERT OR REPLACE INTO toolchain_plans (
                plan_id, goal, steps, strategy, max_depth, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.plan_id,
                plan.goal,
                self._to_json([s.to_dict() for s in plan.steps]),
                plan.strategy,
                plan.max_depth,
                plan.created_at.isoformat(),
                self._to_json(plan.metadata),
            ),
        )

    def load_plans(self) -> list[ToolChainPlan]:
        """Load all plans sorted by created_at."""
        cursor = self._execute(
            "SELECT plan_id, goal, steps, strategy, max_depth, created_at, metadata "
            "FROM toolchain_plans ORDER BY created_at ASC, plan_id ASC"
        )
        plans: list[ToolChainPlan] = []
        for row in cursor.fetchall():
            plans.append(
                ToolChainPlan(
                    plan_id=row["plan_id"],
                    goal=row["goal"],
                    steps=self._steps_from_json(row["steps"]),
                    strategy=row["strategy"],
                    max_depth=row["max_depth"],
                    created_at=self._parse_datetime(row["created_at"]),
                    metadata=self._from_json_dict(row["metadata"]),
                )
            )
        return plans

    # ------------------------------------------------------------------
    # Results / reports (append-only log)
    # ------------------------------------------------------------------

    def store_result(self, result: ToolChainResult) -> None:
        """Append an execution result to the report log.

        A unique ``result_id`` is generated from the chain_id and the
        current timestamp. ``INSERT OR IGNORE`` prevents exact duplicates.
        """
        stored_at: str = datetime.now().isoformat()
        result_id: str = f"result::{result.chain_id}::{stored_at}"
        self._run_write(
            """
            INSERT OR IGNORE INTO toolchain_reports (
                result_id, chain_id, success, step_results, error,
                execution_time_ms, metadata, stored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id,
                result.chain_id,
                int(result.success),
                self._to_json(list(result.step_results)),
                result.error,
                result.execution_time_ms,
                self._to_json(result.metadata),
                stored_at,
            ),
        )

    def load_results(self) -> list[ToolChainResult]:
        """Load all execution results sorted by stored_at."""
        cursor = self._execute(
            "SELECT result_id, chain_id, success, step_results, error, "
            "execution_time_ms, metadata, stored_at "
            "FROM toolchain_reports ORDER BY stored_at ASC, result_id ASC"
        )
        results: list[ToolChainResult] = []
        for row in cursor.fetchall():
            step_results_raw: list[Any] = self._from_json_list(row["step_results"])
            results.append(
                ToolChainResult(
                    chain_id=row["chain_id"],
                    success=bool(row["success"]),
                    step_results=tuple(step_results_raw),
                    error=row["error"],
                    execution_time_ms=row["execution_time_ms"],
                    metadata=self._from_json_dict(row["metadata"]),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def get_schema_version(self) -> int:
        """Return the current schema version without applying migrations."""
        if self._conn is None:
            return 0
        return migration.get_schema_version(self._conn)

    @property
    def db_path(self) -> Path:
        """The database file path."""
        return self._db_path