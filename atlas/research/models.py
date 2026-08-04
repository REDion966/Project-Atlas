"""Atlas Research — Data Models (Phase 17.1)."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class SourceKind(Enum):
    """Kind of a research source in the source adapter layer."""

    DOCUMENT = auto()
    WORKSPACE = auto()
    CODEBASE = auto()


class VerificationStatus(Enum):
    """State of a knowledge claim after verification (Phase 17.1)."""

    UNVERIFIED = auto()
    SUPPORTED = auto()
    CONTRADICTED = auto()
    AMBIGUOUS = auto()


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    """Deterministic decomposition of a research query."""

    plan_id: str
    query_id: str
    question: str
    sub_queries: tuple[str, ...] = ()
    target_sources: tuple[SourceKind, ...] = ()
    verification_strategy: str = ""
    max_depth: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResearchSource:
    """A source instance the adapter layer can load (canonical URI)."""

    uri: str
    kind: SourceKind = SourceKind.DOCUMENT
    title: str = ""
    retrieved_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (datetime objects pass through)."""
        return {
            "uri": self.uri,
            "kind": self.kind.name,
            "title": self.title,
            "retrieved_at": self.retrieved_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class SourceProfile:
    """Normalized, provider-independent representation of source content."""

    uri: str
    kind: SourceKind
    text: str
    title: str = ""
    language: str = ""
    content_type: str = ""
    byte_size: int = 0
    tokens_estimate: int = 0
    line_count: int = 0
    loaded_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (datetime objects pass through)."""
        return {
            "uri": self.uri,
            "kind": self.kind.name,
            "text": self.text,
            "title": self.title,
            "language": self.language,
            "content_type": self.content_type,
            "byte_size": self.byte_size,
            "tokens_estimate": self.tokens_estimate,
            "line_count": self.line_count,
            "loaded_at": self.loaded_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeClaim:
    """A single factual statement attributed to one or more citations."""

    claim_id: str
    statement: str
    citations: tuple[CitationRecord, ...] = ()
    confidence: float = 0.0
    extracted_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested citations become dicts)."""
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "citations": tuple(c.to_dict() for c in self.citations),
            "confidence": self.confidence,
            "extracted_at": self.extracted_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ClaimVerification:
    """Outcome of verifying a single knowledge claim (Phase 17.1)."""

    verification_id: str
    claim_id: str
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    score: float = 0.0
    evidence_summary: str = ""
    verified_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (datetime objects pass through)."""
        return {
            "verification_id": self.verification_id,
            "claim_id": self.claim_id,
            "status": self.status.name,
            "score": self.score,
            "evidence_summary": self.evidence_summary,
            "verified_at": self.verified_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class CitationRecord:
    """A structured citation referencing a normalized source."""

    record_id: str
    source_uri: str = ""
    source_title: str = ""
    source_kind: SourceKind = SourceKind.DOCUMENT
    section: str = ""
    page_or_line: str = ""
    retrieved_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (datetime objects pass through)."""
        return {
            "record_id": self.record_id,
            "source_uri": self.source_uri,
            "source_title": self.source_title,
            "source_kind": self.source_kind.name,
            "section": self.section,
            "page_or_line": self.page_or_line,
            "retrieved_at": self.retrieved_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """Final, citable deliverable of a research run."""

    report_id: str
    plan_id: str
    query_id: str
    question: str
    findings: str
    claims: "tuple[KnowledgeClaim, ...]" = ()
    verifications: "tuple[ClaimVerification, ...]" = ()
    citations: "tuple[CitationRecord, ...]" = ()
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (nested records become dicts)."""
        return {
            "report_id": self.report_id,
            "plan_id": self.plan_id,
            "query_id": self.query_id,
            "question": self.question,
            "findings": self.findings,
            "claims": tuple(c.to_dict() for c in self.claims),
            "verifications": tuple(v.to_dict() for v in self.verifications),
            "citations": tuple(c.to_dict() for c in self.citations),
            "confidence": self.confidence,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
