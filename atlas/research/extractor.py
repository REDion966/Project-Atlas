"""Atlas Research — Knowledge Extractor (Phase 17.4).

Converts a normalized source into a list of
:class:`~atlas.research.models.KnowledgeClaim`.

Input: either :class:`~atlas.research.models.ResearchSource` (metadata
handle; no embedded text → yields no claims) or, more commonly, the
text-bearing :class:`~atlas.research.models.SourceProfile` produced by the
source adapter layer. Both are handled through the same pure,
never-raising ``source_text()`` accessor.

Provider-independent: AI models are used ONLY through the injected
:class:`ExtractionModel` protocol (deliberately shaped like the existing
``atlas.ai.AIService.complete`` surface, but the extractor imports no AI
package and instantiates no provider). With no model injected, the
extractor runs entirely deterministically.

Pipeline (all deterministic unless a model is injected):
  text → chunking → extraction request build → model extract (optional) →
  normalization → duplicate removal → claim-id generation →
  provisional confidence → KnowledgeClaim list.

No verification. No storage. No gateway.
"""

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from atlas.research._extraction import (
    chunk_text,
    claim_id_for,
    normalize_claim_statement,
    provisional_confidence,
)
from atlas.research._text import source_text
from atlas.research.models import (
    CitationRecord,
    KnowledgeClaim,
    ResearchSource,
    SourceProfile,
)

DEFAULT_CHUNK_SIZE: int = 2000

# A source carrying extractable text: SourceProfile from the adapter layer,
# or a plain ResearchSource handle (metadata only, empty text).
ExtractableSource = ResearchSource | SourceProfile


@runtime_checkable
class ExtractionModel(Protocol):
    """Minimal AI extraction surface, injected by the caller."""

    def complete(self, prompt: str) -> str: ...


class KnowledgeExtractor:
    """Deterministic-first claim extractor over a single research source."""

    def __init__(
        self,
        model: ExtractionModel | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        if chunk_size < 1:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        self._model: ExtractionModel | None = model
        self._chunk_size: int = chunk_size
        # Tracks whether the most recent extract() used the optional model
        # path or the deterministic sentence fallback (provenance markers).
        self._last_extraction_origin: str = "deterministic"
        self._last_extracted_at: str = ""

    @property
    def chunk_size(self) -> int:
        """The configured extraction chunk size."""
        return self._chunk_size

    # -- public pipeline --------------------------------------------------

    def extract(self, source: ExtractableSource) -> list[KnowledgeClaim]:
        """Extract normalized, deduplicated, id-stable claims from a source."""
        text: str = source_text(source)
        chunks: list[str] = chunk_text(text, self._chunk_size)
        claims: list[KnowledgeClaim] = []
        self._last_extraction_origin = "deterministic"
        self._last_extracted_at = datetime.now(timezone.utc).isoformat()
        for chunk_index, chunk in enumerate(chunks):
            raw_statements: list[str] = self._raw_statements(chunk)
            for raw_statement in raw_statements:
                normalized: str = normalize_claim_statement(raw_statement)
                if not normalized:
                    continue
                claims.append(
                    KnowledgeClaim(
                        claim_id=claim_id_for(normalized),
                        statement=normalized,
                        citations=(self._build_citation(source, chunk_index),),
                        confidence=provisional_confidence(normalized, source),
                        metadata={
                            "source_uri": source.uri,
                            "extraction_origin": self._last_extraction_origin,
                            "extracted_at": self._last_extracted_at,
                        },
                    )
                )
        return self._deduplicate_claims(claims)

    # -- pipeline steps ---------------------------------------------------

    def chunk(self, text: str) -> list[str]:
        """Deterministic sentence-based chunking (public, testable)."""
        return chunk_text(text, self._chunk_size)

    def build_extraction_request(self, chunk: str) -> str:
        """Build the model prompt for a single chunk (extension point)."""
        return (
            "Extract factual claims from the following text. "
            "Return one claim per line as plain statements.\n\n"
            f"{chunk}"
        )

    def _raw_statements(self, chunk: str) -> list[str]:
        """Raw claim statements from one chunk.

        With a model injected, the model performs extraction; without one,
        the deterministic fallback emits the chunk's sentences. Fail-closed:
        a model returning nothing, or raising, falls back to the sentence
        fallback rather than dropping the chunk silently.
        """
        model: ExtractionModel | None = self._model
        if model is not None:
            try:
                response: str = model.complete(self.build_extraction_request(chunk))
            except Exception:
                response = ""
            statements: list[str] = [
                line.strip() for line in response.splitlines() if line.strip()
            ]
            if statements:
                self._last_extraction_origin = "model"
                return statements
        return [s for s in chunk.split(". ") if s.strip()]

    @staticmethod
    def _build_citation(source: ExtractableSource, chunk_index: int) -> CitationRecord:
        """Citation for a claim, keyed to its source and chunk."""
        return CitationRecord(
            record_id=f"cite:{source.uri}:{chunk_index:04d}",
            source_uri=source.uri,
            source_title=getattr(source, "title", ""),
            source_kind=source.kind,
            section=f"chunk:{chunk_index:04d}",
        )

    @staticmethod
    def _deduplicate_claims(claims: list[KnowledgeClaim]) -> list[KnowledgeClaim]:
        """Stable deduplication by claim_id, keeping first occurrence."""
        seen: set[str] = set()
        kept: list[KnowledgeClaim] = []
        for claim in claims:
            if claim.claim_id not in seen:
                seen.add(claim.claim_id)
                kept.append(claim)
        return kept
