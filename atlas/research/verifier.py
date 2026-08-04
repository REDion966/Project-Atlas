"""Atlas Research — Claim Verifier (Phase 17.5).

Cross-source verification of :class:`~atlas.research.models.KnowledgeClaim`
against a list of sources (either :class:`~atlas.research.models.ResearchSource`
handles or text-bearing :class:`~atlas.research.models.SourceProfile`
profiles), producing :class:`~atlas.research.models.ClaimVerification`.

Design:
  * Deterministic verification first. Outcome + score are derived purely
    from string matching and evidence tallies (pure, order-stable).
  * LLM-assisted verification is OPTIONAL and dependency-injected via the
    :class:`VerificationModel` protocol. When ``strict_llm`` is False
    (default) the model is never consulted. When enabled, the model may
    override the verdict, never the score.
  * Four required verdicts are represented by :class:`ClaimOutcome`; the
    lossless label is stored in ``metadata["outcome"]`` and mapped to the
    locked Phase 17.1 :class:`~atlas.research.models.VerificationStatus`:
      VERIFIED → SUPPORTED
      PLAUSIBLE → SUPPORTED
      CONTESTED → CONTRADICTED
      UNKNOWN → UNVERIFIED

No storage. No gateway. No evolution integration.
"""

from collections.abc import Sequence
from enum import Enum, auto
from typing import Protocol, runtime_checkable

from atlas.research._text import significant_tokens, source_text
from atlas.research._verification import confidence_from_evidence, norm_alpha, similarity_ratio
from atlas.research.models import (
    ClaimVerification,
    KnowledgeClaim,
    ResearchSource,
    SourceProfile,
    VerificationStatus,
)

# Sequence-subsequence similarity above which two texts are treated as the
# same statement (deterministic threshold).
MATCH_SIMILARITY_THRESHOLD: float = 0.8

# Multi-word or unambiguous contradiction markers (checked against the RAW
# source text — they contain spaces, so they can never match the
# alphanumeric-normalized form).
CONTRADICTION_MARKERS: tuple[str, ...] = (
    "does not",
    "do not",
    "is not",
    "are not",
    "was not",
    "were not",
    "never",
    "cannot",
    "can't",
    "doesn't",
    "isn't",
    "aren't",
    "contradicts",
    "contrary",
    "refutes",
    "disputed",
)

# A source usable for verification: a ResearchSource handle (metadata only,
# empty text) or a text-bearing SourceProfile.
VerifiableSource = ResearchSource | SourceProfile


class ClaimOutcome(Enum):
    """Verification verdict for a single claim (Phase 17.5)."""

    VERIFIED = auto()
    PLAUSIBLE = auto()
    CONTESTED = auto()
    UNKNOWN = auto()


@runtime_checkable
class VerificationModel(Protocol):
    """Optional LLM verification surface, injected by the caller.

    Mirrors the minimal request/response shape needed for verification so a
    provider or the existing AIService can be adapted without the verifier
    importing any AI package.
    """

    def complete(self, prompt: str) -> str: ...


class ClaimVerifier:
    """Deterministic-first cross-source claim verifier."""

    def __init__(
        self,
        model: VerificationModel | None = None,
        strict_llm: bool = False,
    ) -> None:
        self._model: VerificationModel | None = model
        self._strict_llm: bool = strict_llm

    # -- public entry point ------------------------------------------------

    def verify(
        self,
        claims: Sequence[KnowledgeClaim],
        sources: Sequence[VerifiableSource],
    ) -> list[ClaimVerification]:
        """Verify every claim against every source (order-preserving)."""
        results: list[ClaimVerification] = []
        for claim in claims:
            results.append(self._verify_claim(claim, sources))
        return results

    # -- per-claim pipeline ------------------------------------------------

    def _verify_claim(
        self,
        claim: KnowledgeClaim,
        sources: Sequence[VerifiableSource],
    ) -> ClaimVerification:
        supporting: list[str] = []
        contradicting: list[str] = []
        for source in sources:
            sign: str | None = self._source_sign(claim.statement, source_text(source))
            if sign == "support":
                if source.uri not in supporting:
                    supporting.append(source.uri)
            elif sign == "contradict":
                if source.uri not in contradicting:
                    contradicting.append(source.uri)

        outcome: ClaimOutcome
        score: float
        if not supporting and not contradicting:
            outcome = ClaimOutcome.UNKNOWN
            score = 0.0
        elif supporting and contradicting:
            outcome = ClaimOutcome.CONTESTED
            score = confidence_from_evidence(len(supporting), len(contradicting))
        elif not supporting and contradicting:
            outcome = ClaimOutcome.CONTESTED
            score = confidence_from_evidence(0, len(contradicting))
        elif len(supporting) >= 2:
            outcome = ClaimOutcome.VERIFIED
            score = confidence_from_evidence(len(supporting), 0)
        else:
            outcome = ClaimOutcome.PLAUSIBLE
            score = confidence_from_evidence(len(supporting), 0)

        # Optional LLM override (never alters the score).
        if self._strict_llm and self._model is not None:
            outcome = self._model_outcome(claim, outcome)

        summary: str = self._summarize(claim.statement, supporting, contradicting)
        return ClaimVerification(
            verification_id=f"verify:{claim.claim_id}",
            claim_id=claim.claim_id,
            status=_to_verification_status(outcome),
            score=score,
            evidence_summary=summary,
            metadata={
                "outcome": outcome.name,
                "supporting": list(supporting),
                "contradicting": list(contradicting),
                "checked_sources": len(sources),
            },
        )

    # -- matching heuristics ----------------------------------------------

    def _source_sign(self, claim_statement: str, source_text: str) -> str | None:
        """Deterministic evidence sign for one claim/source pair.

        Returns ``"support"``, ``"contradict"``, or ``None`` when the source
        is silent about the claim.

        Order matters (deterministic precedence):
          1. explicit contradiction marker in the RAW text → contradict
             (a negated sentence such as "Atlas does not use SQLite" still
             CONTAINS the claim text as a substring, so an explicit
             negation must win over every substring/similarity/token match)
          2. verbatim/substring match → support
          3. high character-level similarity → support
          4. claim-token containment in the source → support
          5. otherwise → None
        """
        if not claim_statement or not source_text:
            return None
        claim_norm: str = norm_alpha(claim_statement)
        source_norm: str = norm_alpha(source_text)
        if not claim_norm:
            return None
        raw_lower: str = source_text.lower()
        if any(marker in raw_lower for marker in CONTRADICTION_MARKERS):
            return "contradict"
        if claim_norm in source_norm:
            return "support"
        if similarity_ratio(claim_norm, source_norm) >= MATCH_SIMILARITY_THRESHOLD:
            return "support"
        claim_tokens: set[str] = significant_tokens(claim_statement)
        source_tokens: set[str] = significant_tokens(source_text)
        if claim_tokens and claim_tokens <= source_tokens:
            return "support"
        return None

    def _model_outcome(self, claim: KnowledgeClaim, fallback: ClaimOutcome) -> ClaimOutcome:
        """Optional LLM verdict, validated and bounds-checked (never raises)."""
        model: VerificationModel | None = self._model
        if model is None:
            return fallback
        try:
            response: str = model.complete(self.build_verification_request(claim))
        except Exception:
            return fallback
        token: str = response.strip().upper().splitlines()[0] if response.strip() else ""
        for member in ClaimOutcome:
            if member.name == token:
                return member
        return fallback

    def build_verification_request(self, claim: KnowledgeClaim) -> str:
        """Build the model prompt for a single claim (extension point)."""
        return (
            "Classify the following factual claim as exactly one of "
            "VERIFIED, PLAUSIBLE, CONTESTED, UNKNOWN. "
            "Reply with the single word only.\n\n"
            f"Claim: {claim.statement}"
        )

    # -- summary -----------------------------------------------------------

    @staticmethod
    def _summarize(
        statement: str,
        supporting: list[str],
        contradicting: list[str],
    ) -> str:
        if not supporting and not contradicting:
            return "no corroborating or contradicting evidence found"
        chunks: list[str] = []
        if supporting:
            chunks.append(f"supported by {len(supporting)} source(s)")
        if contradicting:
            chunks.append(f"contradicted by {len(contradicting)} source(s)")
        return "; ".join(chunks) + f" for claim: {statement}"


def _to_verification_status(outcome: ClaimOutcome) -> VerificationStatus:
    """Map a Phase 17.5 verdict onto the locked Phase 17.1 status enum."""
    if outcome is ClaimOutcome.UNKNOWN:
        return VerificationStatus.UNVERIFIED
    if outcome is ClaimOutcome.CONTESTED:
        return VerificationStatus.CONTRADICTED
    return VerificationStatus.SUPPORTED  # VERIFIED and PLAUSIBLE
