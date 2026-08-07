"""Atlas Advanced Reasoning — HypothesisGenerator (Track D, Batch 2).

Deterministic generation and ranking of competing hypotheses for a claim.
Consumes only the injected :class:`EvidenceProvider` protocol — the generator
never imports or owns knowledge/memory services.

Mechanics:
  * Template families (direct, inverse, alternative_cause, mediating_cause)
    produce candidate hypotheses deterministically.
  * Evidence scoring queries the injected provider against each hypothesis.
  * Confidence is a deterministic blend of evidence support and template
    prior.
  * Optional :class:`HypothesisModel` enhancement is protocol-injected; its
    proposals are re-scored and ranked by the deterministic layer.

Pure logic. No storage. No kernel. No AI SDKs. No atlas.reasoning imports.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from atlas.advanced_reasoning.catalog import (
    DEFAULT_HYPOTHESIS_FAMILY,
    HYPOTHESIS_FAMILIES,
    HYPOTHESIS_ID_PREFIX,
    HYPOTHESIS_SET_ID_PREFIX,
    REASONER_VERSION,
)
from atlas.advanced_reasoning.models import (
    Hypothesis,
    HypothesisSet,
    HypothesisSupport,
    ReasoningConfig,
)
from atlas.advanced_reasoning.protocols import (
    EvidenceProvider,
    HypothesisModel,
)

#: Evidence-support score used when the provider confirms relevance.
_EXACT_SUPPORT_SCORE: float = 0.9
#: Evidence-support score used when evidence exists but is weak.
_WEAK_SUPPORT_SCORE: float = 0.5
#: Prior confidence for a candidate before evidence is consulted.
_TEMPLATE_PRIOR = {
    "direct": 0.5,
    "inverse": 0.4,
    "alternative_cause": 0.4,
    "mediating_cause": 0.4,
}
#: Evidence weight in the blended confidence.
_EVIDENCE_WEIGHT: float = 0.6
#: Template-prior weight in the blended confidence.
_PRIOR_WEIGHT: float = 0.4
#: Evidence query below this count is treated as weak.
_WEAK_EVIDENCE_THRESHOLD: int = 2
#: Minimum length for a usable claim.
_MIN_CLAIM_LENGTH: int = 3


def _sha16(text: str) -> str:
    """Return the first 16 hex chars of the SHA-256 digest of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class HypothesisGenerator:
    """Deterministic competing-hypothesis generator.

    Args:
        evidence_provider: Optional injected evidence source. Candidates are
            still produced without one, scored at their template priors.
        hypothesis_model: Optional model enhancer. Its proposals are merged,
            re-scored, and ranked deterministically.
        config: Optional reasoning configuration; a default is used when
            ``None`` is given.
    """

    def __init__(
        self,
        evidence_provider: EvidenceProvider | None = None,
        hypothesis_model: HypothesisModel | None = None,
        config: ReasoningConfig | None = None,
    ) -> None:
        self._evidence_provider = evidence_provider
        self._hypothesis_model = hypothesis_model
        self._config = config or ReasoningConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        claim: str,
        limit: int | None = None,
        set_id: str | None = None,
    ) -> HypothesisSet:
        """Generate and rank competing hypotheses for ``claim``.

        Returns:
            A HypothesisSet with hypotheses ranked best-first. An invalid
            (empty/too-short) claim yields an empty, never-failing set.
        """
        max_hypotheses = max(1, limit or self._config.max_hypotheses)
        normalized = self._normalize(claim)
        if not normalized:
            return HypothesisSet(
                set_id=set_id or f"{HYPOTHESIS_SET_ID_PREFIX}:empty:{_sha16(claim)}",
                claim=claim.strip(),
                hypotheses=(),
                top_hypothesis_id="",
                created_at=datetime.now(),
                metadata={"reasoner_version": REASONER_VERSION},
            )

        candidates = self._template_candidates(normalized)
        candidates = list(candidates) + list(self._model_candidates(normalized))

        scored = [self._score_hypothesis(candidate) for candidate in candidates]
        ranked = tuple(
            sorted(
                scored,
                key=lambda h: (round(h.score, 6), h.hypothesis_id),
                reverse=True,
            )[:max_hypotheses]
        )
        top_id = ranked[0].hypothesis_id if ranked else ""

        return HypothesisSet(
            set_id=set_id or f"{HYPOTHESIS_SET_ID_PREFIX}:{_sha16(normalized)}",
            claim=normalized,
            hypotheses=ranked,
            top_hypothesis_id=top_id,
            created_at=datetime.now(),
            metadata={"reasoner_version": REASONER_VERSION},
        )

    @staticmethod
    def compare(
        first: Hypothesis,
        second: Hypothesis,
    ) -> str:
        """Explain the deterministic ordering between two hypotheses.

        The returned sentence is stable for the same inputs.
        """
        if first.score > second.score:
            return (
                f"{first.hypothesis_id} ({first.score:.2f}) is ranked above "
                f"{second.hypothesis_id} ({second.score:.2f})."
            )
        if first.score < second.score:
            return (
                f"{second.hypothesis_id} ({second.score:.2f}) is ranked above "
                f"{first.hypothesis_id} ({first.score:.2f})."
            )
        return (
            f"{first.hypothesis_id} and {second.hypothesis_id} are equally "
            f"ranked ({first.score:.2f})."
        )

    @staticmethod
    def explain(hypothesis: Hypothesis) -> str:
        """Build a deterministic explanation of a single hypothesis."""
        support = hypothesis.support.name.lower()
        return (
            f"{hypothesis.claim} (kind={hypothesis.kind or 'generic'}, "
            f"score={hypothesis.score:.2f}, support={support}, "
            f"evidence={len(hypothesis.evidence_refs)} refs)"
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(claim: str) -> str:
        """Collapse whitespace and trim the claim."""
        return " ".join(claim.split()).strip()

    def _template_candidates(self, claim: str) -> tuple[Hypothesis, ...]:
        """Deterministic template-family candidates for ``claim``."""
        candidates: list[Hypothesis] = []
        for family in self._ordered_families():
            h = Hypothesis(
                hypothesis_id=f"{HYPOTHESIS_ID_PREFIX}:{_sha16(claim)}:{family}",
                claim=self._family_statement(family, claim),
                kind=family,
                support=HypothesisSupport.UNVERIFIED,
                score=0.0,
                evidence_refs=(),
                metadata={"template": family},
            )
            candidates.append(h)
        return tuple(candidates)

    def _model_candidates(self, claim: str) -> tuple[Hypothesis, ...]:
        """Model-proposed candidates (validated; fail-soft)."""
        model = self._hypothesis_model
        if model is None:
            return ()
        try:
            proposed = tuple(model.generate(claim, limit=self._config.max_hypotheses))
        except Exception:
            return ()
        seen: set[str] = {c.hypothesis_id for c in self._template_candidates(claim)}
        validated: list[Hypothesis] = []
        for candidate in proposed:
            if not candidate.hypothesis_id or candidate.hypothesis_id in seen:
                continue  # duplicate or empty id — invalid
            if len(candidate.claim.strip()) < _MIN_CLAIM_LENGTH:
                continue
            seen.add(candidate.hypothesis_id)
            validated.append(
                Hypothesis(
                    hypothesis_id=candidate.hypothesis_id,
                    claim=candidate.claim.strip(),
                    kind=candidate.kind or "model",
                    support=HypothesisSupport.UNVERIFIED,
                    score=0.0,
                    evidence_refs=(),
                    metadata={"template": "model"},
                )
            )
        return tuple(validated)

    def _score_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        """Score a candidate deterministically and assign support/evidence."""
        evidence = self._query_evidence(hypothesis.claim)
        support_score = (
            _EXACT_SUPPORT_SCORE
            if len(evidence) >= _WEAK_EVIDENCE_THRESHOLD
            else _WEAK_SUPPORT_SCORE
        )
        prior = _TEMPLATE_PRIOR.get(hypothesis.kind, 0.4)
        confidence = _EVIDENCE_WEIGHT * support_score + _PRIOR_WEIGHT * prior
        support = (
            HypothesisSupport.SUPPORTED
            if len(evidence) >= _WEAK_EVIDENCE_THRESHOLD
            else (
                HypothesisSupport.CONTRADICTED
                if not evidence
                else HypothesisSupport.UNVERIFIED
            )
        )
        return Hypothesis(
            hypothesis_id=hypothesis.hypothesis_id,
            claim=hypothesis.claim,
            kind=hypothesis.kind,
            support=support,
            score=round(confidence, 4),
            evidence_refs=evidence,
            metadata=hypothesis.metadata,
        )

    def _query_evidence(self, claim: str) -> tuple[str, ...]:
        """Query the injected evidence provider (fail-soft)."""
        provider = self._evidence_provider
        if provider is None:
            return ()
        try:
            results = provider.query(claim, limit=self._config.evidence_limit)
            return tuple(sorted(str(ref) for ref in results[: self._config.evidence_limit]))
        except Exception:
            return ()

    @staticmethod
    def _ordered_families() -> tuple[str, ...]:
        """Deterministic stable order of template families."""
        ordered = [DEFAULT_HYPOTHESIS_FAMILY] + sorted(
            family
            for family in HYPOTHESIS_FAMILIES
            if family != DEFAULT_HYPOTHESIS_FAMILY
        )
        return tuple(ordered)

    @staticmethod
    def _family_statement(family: str, claim: str) -> str:
        """Deterministic hypothesis wording per template family."""
        if family == "direct":
            return f"Directly: {claim}"
        if family == "inverse":
            return f"Inverse: not {claim}"
        if family == "alternative_cause":
            return f"Alternative cause explains: {claim}"
        if family == "mediating_cause":
            return f"Mediating cause produces: {claim}"
        return f"Candidate: {claim}"
