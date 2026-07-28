"""
Atlas Storage Migration Framework — Phase 9.1 / 9.2b / 11.3

Simple additive migration system for SQLite-backed storage. Each migration
is a tuple of (sql_statement, description). Migrations are applied in
ascending version order inside a transaction.

No destructive migrations are permitted.
"""

from __future__ import annotations

import sqlite3
from typing import Any


CURRENT_SCHEMA_VERSION = 3

# Migration chain: version -> list of (sql, description)
MIGRATIONS: dict[int, list[tuple[str, str]]] = {
    2: [
        ("""
            CREATE TABLE IF NOT EXISTS understanding_concepts (
                concept_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                domain TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                source TEXT DEFAULT '',
                frequency INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """, "Create understanding_concepts table"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_understanding_concepts_label
                ON understanding_concepts(label)
        """, "Index on understanding concept label"),
        ("""
            CREATE TABLE IF NOT EXISTS understanding_relationships (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 0.5,
                confidence REAL NOT NULL DEFAULT 0.5,
                observed_count INTEGER NOT NULL DEFAULT 1,
                first_observed TEXT NOT NULL,
                last_observed TEXT NOT NULL,
                PRIMARY KEY (source_id, target_id, relationship_type)
            )
        """, "Create understanding_relationships table with composite PK"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_understanding_relationships_source
                ON understanding_relationships(source_id)
        """, "Index on understanding relationship source"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_understanding_relationships_target
                ON understanding_relationships(target_id)
        """, "Index on understanding relationship target"),
        ("""
            CREATE TABLE IF NOT EXISTS understanding_patterns (
                pattern_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                related_concept_ids TEXT DEFAULT '[]',
                frequency INTEGER NOT NULL DEFAULT 1,
                first_observed TEXT NOT NULL,
                last_observed TEXT NOT NULL
            )
        """, "Create understanding_patterns table"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_understanding_patterns_label
                ON understanding_patterns(label)
        """, "Index on understanding pattern label"),
        ("""
            CREATE TABLE IF NOT EXISTS understanding_insights (
                insight_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                detail TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                related_concept_ids TEXT DEFAULT '[]',
                related_pattern_ids TEXT DEFAULT '[]',
                source TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """, "Create understanding_insights table"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_understanding_insights_category
                ON understanding_insights(category)
        """, "Index on understanding insight category"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_understanding_insights_timestamp
                ON understanding_insights(timestamp DESC)
        """, "Index on understanding insight timestamp"),
        ("""
            CREATE TABLE IF NOT EXISTS understanding_signals (
                signal_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                description TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                related_concept_ids TEXT DEFAULT '[]',
                source TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            )
        """, "Create understanding_signals table"),
    ],
    3: [
        ("""
            CREATE TABLE IF NOT EXISTS evolution_proposals (
                proposal_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                rationale TEXT NOT NULL,
                expected_benefit TEXT NOT NULL,
                risks TEXT NOT NULL,
                impact_analysis TEXT NOT NULL,
                implementation_approach TEXT NOT NULL,
                plan_id TEXT DEFAULT '',
                plan_title TEXT DEFAULT '',
                plan_description TEXT DEFAULT '',
                plan_priority TEXT DEFAULT '',
                plan_weaknesses TEXT DEFAULT '[]',
                plan_expected_benefit TEXT DEFAULT '',
                plan_complexity TEXT DEFAULT 'medium',
                plan_target_components TEXT DEFAULT '[]',
                status TEXT NOT NULL,
                rejection_reason TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                approved_at TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_proposals table"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_proposals_status
                ON evolution_proposals(status)
        """, "Index on evolution proposal status"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_approval_requests (
                request_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                rationale TEXT NOT NULL,
                risks TEXT NOT NULL,
                expected_benefit TEXT NOT NULL,
                decision TEXT NOT NULL,
                decision_comment TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                decided_at TEXT
            )
        """, "Create evolution_approval_requests table"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_approval_proposal
                ON evolution_approval_requests(proposal_id)
        """, "Index on approval request proposal_id"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_records (
                record_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                related_ids TEXT DEFAULT '[]',
                timestamp TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_records table"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_records_event_type
                ON evolution_records(event_type)
        """, "Index on evolution record event type"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_records_timestamp
                ON evolution_records(timestamp DESC)
        """, "Index on evolution record timestamp"),
    ],
}


def _create_initial_schema() -> list[str]:
    """Return the initial schema DDL for version 1."""
    return [
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS experiences (
            experience_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            pipeline_path TEXT NOT NULL,
            outcome TEXT NOT NULL,
            user_input TEXT DEFAULT '',
            conversation_history_length INTEGER DEFAULT 0,
            understanding_insights_count INTEGER DEFAULT 0,
            concepts_extracted TEXT DEFAULT '[]',
            world_model_entities INTEGER DEFAULT 0,
            world_model_relations INTEGER DEFAULT 0,
            reasoning_goal TEXT DEFAULT '',
            reasoning_capabilities TEXT DEFAULT '[]',
            reasoning_success_count INTEGER DEFAULT 0,
            reasoning_total_count INTEGER DEFAULT 0,
            planning_goal TEXT DEFAULT '',
            planning_step_count INTEGER DEFAULT 0,
            planning_validation_errors INTEGER DEFAULT 0,
            tool_name TEXT DEFAULT '',
            tool_success INTEGER DEFAULT 0,
            learning_insights_count INTEGER DEFAULT 0,
            reflection_suggestions_count INTEGER DEFAULT 0,
            goal_recommendations_count INTEGER DEFAULT 0,
            identity_version INTEGER DEFAULT 0,
            identity_belief_count INTEGER DEFAULT 0,
            identity_capability_count INTEGER DEFAULT 0
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_experiences_timestamp
            ON experiences(timestamp DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_experiences_outcome
            ON experiences(outcome)
        """,
        """
        CREATE TABLE IF NOT EXISTS trend_analyses (
            analysis_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            window_size INTEGER NOT NULL,
            overall_success_rate REAL DEFAULT 0,
            success_rate_trend TEXT DEFAULT 'stable',
            avg_understanding_insights REAL DEFAULT 0,
            understanding_trend TEXT DEFAULT 'stable',
            avg_reasoning_success REAL DEFAULT 0,
            reasoning_trend TEXT DEFAULT 'stable',
            avg_planning_errors REAL DEFAULT 0,
            planning_trend TEXT DEFAULT 'stable',
            tool_success_rate REAL DEFAULT 0,
            tool_trend TEXT DEFAULT 'stable',
            learning_insight_rate REAL DEFAULT 0,
            learning_trend TEXT DEFAULT 'stable',
            identity_stability REAL DEFAULT 0,
            capability_trends TEXT DEFAULT '{}'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tracked_goals (
            goal_id TEXT PRIMARY KEY,
            recommendation_id TEXT DEFAULT '',
            goal_title TEXT DEFAULT '',
            proposed_at TEXT NOT NULL,
            outcome TEXT NOT NULL,
            outcome_reason TEXT DEFAULT '',
            related_experience_ids TEXT DEFAULT '[]',
            last_evaluated TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS self_model_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            total_experiences INTEGER NOT NULL,
            overall_success_rate REAL NOT NULL,
            capability_assessments TEXT DEFAULT '{}',
            belief_evidence TEXT DEFAULT '{}',
            trend_summary TEXT DEFAULT '',
            identity_version INTEGER DEFAULT 0,
            last_trend_analysis TEXT,
            recent_improvement_evidence TEXT DEFAULT '[]',
            persistent_challenges TEXT DEFAULT '[]'
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
            ON self_model_snapshots(timestamp DESC)
        """,
    ]


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    """Create the schema_version table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _get_current_version(conn: sqlite3.Connection) -> int:
    """Return the currently recorded schema version, or 0 if unset."""
    _ensure_schema_version_table(conn)
    cursor = conn.execute("SELECT MAX(version) FROM schema_version")
    row = cursor.fetchone()
    return row[0] or 0


def _record_version(conn: sqlite3.Connection, version: int) -> None:
    """Record that a schema version has been applied."""
    from datetime import datetime

    conn.execute(
        "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
        (version, datetime.now().isoformat()),
    )


def apply_migrations(conn: sqlite3.Connection) -> int:
    """
    Apply all pending migrations to reach CURRENT_SCHEMA_VERSION.

    The initial schema (version 1) is created automatically if no
    schema_version row exists. Subsequent migrations are loaded from
    MIGRATIONS and applied transactionally.

    Args:
        conn: An open sqlite3 connection.

    Returns:
        The final schema version.

    Raises:
        sqlite3.Error: If a migration fails. The transaction is rolled back.
    """
    current = _get_current_version(conn)

    # Create the initial schema if we are at version 0.
    if current == 0:
        for ddl in _create_initial_schema():
            conn.execute(ddl)
        _record_version(conn, 1)
        current = 1

    # Apply any pending migrations from MIGRATIONS.
    for version in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
        steps = MIGRATIONS.get(version)
        if not steps:
            # No migration steps recorded for this version; just record it.
            _record_version(conn, version)
            continue

        with conn:
            for sql, _description in steps:
                conn.execute(sql)
            _record_version(conn, version)

    return _get_current_version(conn)


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version without applying migrations."""
    return _get_current_version(conn)
