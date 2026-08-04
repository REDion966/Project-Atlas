"""
Atlas Storage Migration Framework — Phase 9.1 / 9.2b / 11.3 / 12.3 / 13.5 / 16.4 / 17.6 / 18.8

Simple additive migration system for SQLite-backed storage. Each migration
is a tuple of (sql_statement, description). Migrations are applied in
ascending version order inside a transaction.

No destructive migrations are permitted.

Phase 12.3 — Added evolution_insights table (schema version 4).
Phase 13.5 — Added evolution_observations and evolution_knowledge_*
tables for the Persistent Evolution Knowledge layer (schema version 5).
Phase 16.4 — Added evolution_requests, evolution_versions, evolution_receipts,
evolution_snapshots, evolution_outcomes, and staged_config tables for the
Governed Autonomous Evolution persistence layer (schema version 6).
Phase 17.6 — Added research_* tables for Track A research storage (schema version 7).
Phase 18.8 — Added toolchain_* tables for Track B toolchain storage (schema version 8).
"""

from __future__ import annotations

import sqlite3
from typing import Any


CURRENT_SCHEMA_VERSION = 8

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
    4: [
        ("""
            CREATE TABLE IF NOT EXISTS evolution_insights (
                insight_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                execution_record_id TEXT NOT NULL,
                tracked_goal_id TEXT NOT NULL,

                outcome TEXT NOT NULL,

                confidence REAL NOT NULL,
                effectiveness_score REAL NOT NULL,

                evidence_summary TEXT NOT NULL,
                evidence_count INTEGER NOT NULL DEFAULT 0,

                evidence_quality REAL NOT NULL,
                regression_risk REAL NOT NULL DEFAULT 0.0,

                analyzed_at TEXT NOT NULL,

                proposal_title TEXT DEFAULT '',
                proposal_summary TEXT DEFAULT '',

                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_insights table for Phase 12.3 evolution outcome analysis"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_insights_proposal
                ON evolution_insights(proposal_id)
        """, "Index on evolution insight proposal_id"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_insights_analyzed_at
                ON evolution_insights(analyzed_at DESC)
        """, "Index on evolution insight analyzed_at"),
    ],
    5: [
        ("""
            CREATE TABLE IF NOT EXISTS evolution_observations (
                observation_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value TEXT DEFAULT '{}',
                unit TEXT DEFAULT '',
                description TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                source TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_observations table for Phase 13.5"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_observations_timestamp
                ON evolution_observations(timestamp DESC)
        """, "Index on evolution observation timestamp"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_knowledge_patterns (
                pattern_id TEXT PRIMARY KEY,
                area TEXT NOT NULL,
                outcome TEXT NOT NULL,
                occurrence_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                partial_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                inconclusive_count INTEGER NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0.0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                related_ids TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_knowledge_patterns table for Phase 13.5"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_knowledge_patterns_area
                ON evolution_knowledge_patterns(area)
        """, "Index on knowledge pattern area"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_knowledge_strategies (
                strategy_key TEXT PRIMARY KEY,
                strategy_name TEXT DEFAULT '',
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                occurrence_count INTEGER NOT NULL DEFAULT 0,
                effectiveness REAL NOT NULL DEFAULT 0.0,
                confidence REAL NOT NULL DEFAULT 0.0,
                avg_regression_risk REAL NOT NULL DEFAULT 0.0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                related_ids TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_knowledge_strategies table for Phase 13.5"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_knowledge_capabilities (
                capability_name TEXT PRIMARY KEY,
                assessments TEXT DEFAULT '[]',
                observed_count INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                related_ids TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_knowledge_capabilities table for Phase 13.5"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_knowledge_bottlenecks (
                bottleneck_id TEXT PRIMARY KEY,
                area TEXT NOT NULL,
                description TEXT DEFAULT '',
                recurrence_count INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                related_ids TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_knowledge_bottlenecks table for Phase 13.5"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_knowledge_bottlenecks_area
                ON evolution_knowledge_bottlenecks(area)
        """, "Index on knowledge bottleneck area"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_knowledge_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                pattern_count INTEGER NOT NULL DEFAULT 0,
                strategy_count INTEGER NOT NULL DEFAULT 0,
                capability_count INTEGER NOT NULL DEFAULT 0,
                bottleneck_count INTEGER NOT NULL DEFAULT 0,
                summary_text TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}'
            )
        """, "Create evolution_knowledge_snapshots table for Phase 13.5"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_knowledge_snapshots_timestamp
                ON evolution_knowledge_snapshots(timestamp DESC)
        """, "Index on knowledge snapshot timestamp"),
    ],
    7: [
        ("""
            CREATE TABLE IF NOT EXISTS research_sources (
                uri TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                retrieved_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create research_sources table for Phase 17.6 research storage"),
        ("""
            CREATE TABLE IF NOT EXISTS research_claims (
                claim_id TEXT PRIMARY KEY,
                statement TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.0,
                extracted_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                citations TEXT NOT NULL DEFAULT '[]'
            )
        """, "Create research_claims table for Phase 17.6 research storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_research_claims_extracted_at
                ON research_claims(extracted_at DESC)
        """, "Index on research claim extracted_at"),
        ("""
            CREATE TABLE IF NOT EXISTS research_verifications (
                verification_id TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL,
                status TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0.0,
                evidence_summary TEXT NOT NULL DEFAULT '',
                verified_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create research_verifications table for Phase 17.6 research storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_research_verifications_claim
                ON research_verifications(claim_id)
        """, "Index on research verification claim_id"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_research_verifications_verified_at
                ON research_verifications(verified_at DESC)
        """, "Index on research verification verified_at"),
        ("""
            CREATE TABLE IF NOT EXISTS research_citations (
                record_id TEXT PRIMARY KEY,
                source_uri TEXT NOT NULL DEFAULT '',
                source_title TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'DOCUMENT',
                section TEXT NOT NULL DEFAULT '',
                page_or_line TEXT NOT NULL DEFAULT '',
                retrieved_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create research_citations table for Phase 17.6 research storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_research_citations_source
                ON research_citations(source_uri)
        """, "Index on research citation source_uri"),
        ("""
            CREATE TABLE IF NOT EXISTS research_reports (
                report_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL DEFAULT '',
                query_id TEXT NOT NULL DEFAULT '',
                question TEXT NOT NULL DEFAULT '',
                findings TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                claims TEXT NOT NULL DEFAULT '[]',
                verifications TEXT NOT NULL DEFAULT '[]',
                citations TEXT NOT NULL DEFAULT '[]'
            )
        """, "Create research_reports table for Phase 17.6 research storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_research_reports_created_at
                ON research_reports(created_at DESC)
        """, "Index on research report created_at"),
    ],
    6: [
        ("""
            CREATE TABLE IF NOT EXISTS evolution_requests (
                request_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                target_scope TEXT NOT NULL,
                change_payload TEXT NOT NULL DEFAULT '{}',
                intended_level TEXT NOT NULL,
                status TEXT NOT NULL,
                validation TEXT,
                risk TEXT,
                authorization TEXT,
                schedule TEXT,
                version_target TEXT,
                rollback TEXT,
                receipt TEXT,
                verification TEXT,
                outcome TEXT,
                parent_request_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create evolution_requests table for Phase 16.4 autonomous evolution"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_requests_status
                ON evolution_requests(status)
        """, "Index on evolution request status"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_requests_updated_at
                ON evolution_requests(updated_at DESC)
        """, "Index on evolution request updated_at"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_requests_target_scope
                ON evolution_requests(target_scope)
        """, "Index on evolution request target_scope"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_versions (
                manifest_id TEXT PRIMARY KEY,
                major INTEGER NOT NULL DEFAULT 1,
                minor INTEGER NOT NULL DEFAULT 0,
                patch INTEGER NOT NULL DEFAULT 0,
                applied_request_ids TEXT NOT NULL DEFAULT '[]',
                parent_version TEXT NOT NULL DEFAULT '',
                scope_versions TEXT NOT NULL DEFAULT '{}',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """, "Create evolution_versions table for Phase 16.4 version manifests"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_versions_created_at
                ON evolution_versions(created_at DESC)
        """, "Index on evolution version created_at"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_receipts (
                receipt_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                changed_keys TEXT NOT NULL DEFAULT '[]',
                before_refs TEXT NOT NULL DEFAULT '{}',
                after_refs TEXT NOT NULL DEFAULT '{}',
                version_delta TEXT NOT NULL DEFAULT '',
                target_tags TEXT NOT NULL DEFAULT '[]',
                applied_at TEXT NOT NULL
            )
        """, "Create evolution_receipts table for Phase 16.4 change receipts"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_receipts_request
                ON evolution_receipts(request_id)
        """, "Index on evolution receipt request_id"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                snapshot_data TEXT NOT NULL,
                checksum TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """, "Create evolution_snapshots table for Phase 16.4 rollback snapshots"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_snapshots_request
                ON evolution_snapshots(request_id)
        """, "Index on evolution snapshot request_id"),
        ("""
            CREATE TABLE IF NOT EXISTS evolution_outcomes (
                outcome_record_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                area TEXT NOT NULL DEFAULT '',
                risk_level TEXT NOT NULL,
                intended_level TEXT NOT NULL,
                authorization_mode TEXT NOT NULL,
                outcome TEXT NOT NULL,
                verification_passed INTEGER NOT NULL DEFAULT 0,
                rollback_occurred INTEGER NOT NULL DEFAULT 0,
                effectiveness_proxy REAL NOT NULL DEFAULT 0.0,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                related_ids TEXT NOT NULL DEFAULT '[]',
                strategy_key TEXT NOT NULL DEFAULT '',
                strategy_name TEXT NOT NULL DEFAULT '',
                planning_context_version TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create evolution_outcomes table for Phase 16.4 terminal outcomes"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_outcomes_request
                ON evolution_outcomes(request_id)
        """, "Index on evolution outcome request_id"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_evolution_outcomes_finished_at
                ON evolution_outcomes(finished_at DESC)
        """, "Index on evolution outcome finished_at"),
        ("""
            CREATE TABLE IF NOT EXISTS staged_config (
                entry_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                schema_status TEXT NOT NULL DEFAULT 'pending',
                activated_at TEXT,
                applied_at TEXT NOT NULL
            )
        """, "Create staged_config table for Phase 16.4 staged config entries"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_staged_config_request
                ON staged_config(request_id)
        """, "Index on staged config request_id"),
    ],
    8: [
        ("""
            CREATE TABLE IF NOT EXISTS toolchain_skills (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'utility',
                tool_name TEXT NOT NULL DEFAULT '',
                chain TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create toolchain_skills table for Phase 18.8 toolchain storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_toolchain_skills_category
                ON toolchain_skills(category)
        """, "Index on toolchain skill category"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_toolchain_skills_status
                ON toolchain_skills(status)
        """, "Index on toolchain skill status"),
        ("""
            CREATE TABLE IF NOT EXISTS toolchain_chains (
                chain_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                steps TEXT NOT NULL DEFAULT '[]',
                strategy TEXT NOT NULL DEFAULT 'sequential',
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create toolchain_chains table for Phase 18.8 toolchain storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_toolchain_chains_created_at
                ON toolchain_chains(created_at DESC)
        """, "Index on toolchain chain created_at"),
        ("""
            CREATE TABLE IF NOT EXISTS toolchain_effectiveness_records (
                record_id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                execution_time_ms REAL NOT NULL DEFAULT 0.0,
                context_hash TEXT NOT NULL DEFAULT '',
                skill_id TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create toolchain_effectiveness_records table for Phase 18.8 toolchain storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_toolchain_effectiveness_records_tool
                ON toolchain_effectiveness_records(tool_name)
        """, "Index on toolchain effectiveness record tool_name"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_toolchain_effectiveness_records_recorded_at
                ON toolchain_effectiveness_records(recorded_at DESC)
        """, "Index on toolchain effectiveness record recorded_at"),
        ("""
            CREATE TABLE IF NOT EXISTS toolchain_plans (
                plan_id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                steps TEXT NOT NULL DEFAULT '[]',
                strategy TEXT NOT NULL DEFAULT 'sequential',
                max_depth INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """, "Create toolchain_plans table for Phase 18.8 toolchain storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_toolchain_plans_created_at
                ON toolchain_plans(created_at DESC)
        """, "Index on toolchain plan created_at"),
        ("""
            CREATE TABLE IF NOT EXISTS toolchain_reports (
                result_id TEXT PRIMARY KEY,
                chain_id TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                step_results TEXT NOT NULL DEFAULT '[]',
                error TEXT NOT NULL DEFAULT '',
                execution_time_ms REAL NOT NULL DEFAULT 0.0,
                metadata TEXT NOT NULL DEFAULT '{}',
                stored_at TEXT NOT NULL
            )
        """, "Create toolchain_reports table for Phase 18.8 toolchain storage"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_toolchain_reports_chain_id
                ON toolchain_reports(chain_id)
        """, "Index on toolchain report chain_id"),
        ("""
            CREATE INDEX IF NOT EXISTS idx_toolchain_reports_stored_at
                ON toolchain_reports(stored_at DESC)
        """, "Index on toolchain report stored_at"),
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
