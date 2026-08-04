"""Atlas Research — SQLite Storage (Phase 17.6).

Persistence adapter for Track A research artifacts. Additive tables only
(research_*), appended to the shared ``atlas_data/atlas_experience.db``
via the migration framework. Append-only where appropriate.

Persistence ONLY: no business logic, no gateway, no kernel, no dispatcher.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    ResearchReport,
    ResearchSource,
    SourceKind,
    VerificationStatus,
)
from atlas.research.storage_protocol import ResearchStorage
from atlas.storage import migration


logger = logging.getLogger(__name__)


class ResearchSQLiteStorage(ResearchStorage):
    """SQLite-backed persistence for Track A research artifacts."""

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
            logger.exception("Failed to initialize research storage at %s", self._db_path)
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
                logger.exception("Error closing research storage")
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
    # Sources (append-only log: INSERT, never mutating an earlier source)
    # ------------------------------------------------------------------

    def store_source(self, source: ResearchSource) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO research_sources (
                uri, kind, title, retrieved_at, metadata
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                source.uri,
                source.kind.name,
                source.title,
                source.retrieved_at.isoformat(),
                self._to_json(source.metadata),
            ),
        )

    def load_sources(self) -> list[ResearchSource]:
        cursor = self._execute(
            "SELECT uri, kind, title, retrieved_at, metadata "
            "FROM research_sources ORDER BY retrieved_at ASC, uri ASC"
        )
        return [
            ResearchSource(
                uri=row["uri"],
                kind=SourceKind[row["kind"]],
                title=row["title"],
                retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
                metadata=self._from_json_dict(row["metadata"]),
            )
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Claims (idempotent upsert by claim_id)
    # ------------------------------------------------------------------

    def store_claim(self, claim: KnowledgeClaim) -> None:
        self._run_write(
            """
            INSERT OR REPLACE INTO research_claims (
                claim_id, statement, confidence, extracted_at, metadata, citations
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                claim.claim_id,
                claim.statement,
                claim.confidence,
                claim.extracted_at.isoformat(),
                self._to_json(claim.metadata),
                self._to_json([c.record_id for c in claim.citations]),
            ),
        )
        for citation in claim.citations:
            self.store_citation(citation)

    def load_claims(self) -> list[KnowledgeClaim]:
        cursor = self._execute(
            "SELECT claim_id, statement, confidence, extracted_at, metadata, citations "
            "FROM research_claims ORDER BY extracted_at ASC, claim_id ASC"
        )
        citations_by_id = {c.record_id: c for c in self.load_citations()}
        return [
            KnowledgeClaim(
                claim_id=row["claim_id"],
                statement=row["statement"],
                confidence=row["confidence"],
                extracted_at=datetime.fromisoformat(row["extracted_at"]),
                metadata=self._from_json_dict(row["metadata"]),
                citations=tuple(
                    citations_by_id[cid]
                    for cid in self._from_json_list(row["citations"])
                    if cid in citations_by_id
                ),
            )
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Verifications (append-only log)
    # ------------------------------------------------------------------

    def store_verification(self, verification: ClaimVerification) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO research_verifications (
                verification_id, claim_id, status, score, evidence_summary,
                verified_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verification.verification_id,
                verification.claim_id,
                verification.status.name,
                verification.score,
                verification.evidence_summary,
                verification.verified_at.isoformat(),
                self._to_json(verification.metadata),
            ),
        )

    def load_verifications(self) -> list[ClaimVerification]:
        cursor = self._execute(
            "SELECT verification_id, claim_id, status, score, evidence_summary, "
            "verified_at, metadata "
            "FROM research_verifications ORDER BY verified_at ASC"
        )
        return [
            ClaimVerification(
                verification_id=row["verification_id"],
                claim_id=row["claim_id"],
                status=VerificationStatus[row["status"]],
                score=row["score"],
                evidence_summary=row["evidence_summary"],
                verified_at=datetime.fromisoformat(row["verified_at"]),
                metadata=self._from_json_dict(row["metadata"]),
            )
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Citations (idempotent upsert by record_id)
    # ------------------------------------------------------------------

    def store_citation(self, citation: CitationRecord) -> None:
        self._run_write(
            """
            INSERT OR REPLACE INTO research_citations (
                record_id, source_uri, source_title, source_kind, section,
                page_or_line, retrieved_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                citation.record_id,
                citation.source_uri,
                citation.source_title,
                citation.source_kind.name,
                citation.section,
                citation.page_or_line,
                citation.retrieved_at.isoformat(),
                self._to_json(citation.metadata),
            ),
        )

    def load_citations(self) -> list[CitationRecord]:
        cursor = self._execute(
            "SELECT record_id, source_uri, source_title, source_kind, section, "
            "page_or_line, retrieved_at, metadata "
            "FROM research_citations ORDER BY retrieved_at ASC, record_id ASC"
        )
        return [
            CitationRecord(
                record_id=row["record_id"],
                source_uri=row["source_uri"],
                source_title=row["source_title"],
                source_kind=SourceKind[row["source_kind"]],
                section=row["section"],
                page_or_line=row["page_or_line"],
                retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
                metadata=self._from_json_dict(row["metadata"]),
            )
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Reports (append-only log)
    # ------------------------------------------------------------------

    def store_report(self, report: ResearchReport) -> None:
        self._run_write(
            """
            INSERT OR IGNORE INTO research_reports (
                report_id, plan_id, query_id, question, findings, confidence,
                created_at, metadata, claims, verifications, citations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.report_id,
                report.plan_id,
                report.query_id,
                report.question,
                report.findings,
                report.confidence,
                report.created_at.isoformat(),
                self._to_json(report.metadata),
                self._to_json([c.claim_id for c in report.claims]),
                self._to_json([v.verification_id for v in report.verifications]),
                self._to_json([c.record_id for c in report.citations]),
            ),
        )
        for claim in report.claims:
            self.store_claim(claim)
        for verification in report.verifications:
            self.store_verification(verification)
        for citation in report.citations:
            self.store_citation(citation)

    def load_reports(self) -> list[ResearchReport]:
        cursor = self._execute(
            "SELECT report_id, plan_id, query_id, question, findings, confidence, "
            "created_at, metadata, claims, verifications, citations "
            "FROM research_reports ORDER BY created_at ASC"
        )
        claims_by_id = {c.claim_id: c for c in self.load_claims()}
        verifications_by_id = {v.verification_id: v for v in self.load_verifications()}
        citations_by_id = {c.record_id: c for c in self.load_citations()}
        reports: list[ResearchReport] = []
        for row in cursor.fetchall():
            reports.append(
                ResearchReport(
                    report_id=row["report_id"],
                    plan_id=row["plan_id"],
                    query_id=row["query_id"],
                    question=row["question"],
                    findings=row["findings"],
                    confidence=row["confidence"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    metadata=self._from_json_dict(row["metadata"]),
                    claims=tuple(
                        claims_by_id[cid]
                        for cid in self._from_json_list(row["claims"])
                        if cid in claims_by_id
                    ),
                    verifications=tuple(
                        verifications_by_id[vid]
                        for vid in self._from_json_list(row["verifications"])
                        if vid in verifications_by_id
                    ),
                    citations=tuple(
                        citations_by_id[cid]
                        for cid in self._from_json_list(row["citations"])
                        if cid in citations_by_id
                    ),
                )
            )
        return reports

    def get_schema_version(self) -> int:
        """Return the current schema version without applying migrations."""
        if self._conn is None:
            return 0
        return migration.get_schema_version(self._conn)

    @property
    def db_path(self) -> Path:
        return self._db_path
