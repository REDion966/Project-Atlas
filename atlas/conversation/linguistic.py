"""Atlas Conversation — optional linguistic-provider seam (Stage 8).

A clean, model-independent boundary through which OPTIONAL linguistic-analysis
providers may contribute bounded, structured EVIDENCE to Atlas's deterministic
conversational pipeline. Atlas remains the interpreter, adjudicator, governor and
authority.

Why this seam (audit evidence, Stage 8):

  * The deterministic pipeline (lexicon word classes + TaskIntake + SemanticFrame
    + AtlasMeaning + the Stage 4/6 layers) already interprets the realistic
    lexical / grammatical / question variation, so NO external NLP dependency is
    justified. The boundary is therefore implemented and proven with an
    Atlas-native DETERMINISTIC provider.
  * The genuine remaining linguistic gaps — pronoun / discourse coreference — are
    Stage 6's to adjudicate: a provider may propose candidates, but Atlas decides.

Contract (mandatory):

  * Optional — an empty provider set yields an ``unavailable`` evidence record and
    the deterministic path continues unchanged.
  * Advisory only — evidence is EVIDENCE, never a command. It never overwrites
    ``AtlasMeaning`` / ``DialogueState`` / ``DiscourseState`` / thread state /
    governance / operation state, and never authorizes or executes anything.
  * Fail-safe — unavailable / raising / malformed / out-of-bounds provider output
    is rejected and recorded with provenance; Atlas never crashes or treats
    arbitrary output as truth.
  * Provenance — provider evidence is explicitly distinguished from native
    deterministic evidence.
  * Bounded, frozen, JSON-safe, deterministic, model-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

from atlas.conversation.lexicon import normalize_token, tokens

#: Context key under which the bounded, advisory projection rides the TaskSpec.
LINGUISTIC_EVIDENCE_KEY: str = "linguistic_evidence"

#: Provider outcome statuses.
PROVIDER_OK: str = "ok"
PROVIDER_UNAVAILABLE: str = "unavailable"
PROVIDER_INVALID: str = "invalid"
PROVIDER_ERROR: str = "error"

PROVIDER_STATUSES: frozenset[str] = frozenset(
    {PROVIDER_OK, PROVIDER_UNAVAILABLE, PROVIDER_INVALID, PROVIDER_ERROR}
)

#: Adjudication outcomes (descriptive: Atlas's reading of the provider evidence).
ADJUDICATION_NATIVE_ONLY: str = "native_only"
ADJUDICATION_CORROBORATED: str = "corroborated"
ADJUDICATION_CONFLICTING: str = "conflicting"
ADJUDICATION_UNAVAILABLE: str = "unavailable"

#: Question-type vocabulary a provider may propose.
QUESTION_WH: str = "wh"
QUESTION_YES_NO: str = "yes_no"
QUESTION_IMPERATIVE: str = "imperative"
QUESTION_DECLARATIVE: str = "declarative"
QUESTION_NONE: str = ""

QUESTION_TYPES: frozenset[str] = frozenset(
    {QUESTION_WH, QUESTION_YES_NO, QUESTION_IMPERATIVE, QUESTION_DECLARATIVE}
)

#: Bounds — a provider can never inject unbounded spans/metadata.
MAX_TOKENS: int = 64
MAX_ITEMS: int = 24
_MAX_ITEM_CHARS: int = 48
_MAX_PROVIDER_CHARS: int = 40


def _bounded(value: Any, limit: int = _MAX_ITEM_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _bounded_items(values: Any, *, limit: int = MAX_ITEMS) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    out: list[str] = []
    for value in values:
        text = _bounded(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


@dataclass(frozen=True, slots=True)
class LinguisticEvidence:
    """Bounded, advisory linguistic evidence from one optional provider."""

    provider: str = ""
    status: str = PROVIDER_UNAVAILABLE
    tokens: tuple[str, ...] = ()
    lemmas: tuple[str, ...] = ()
    pronouns: tuple[str, ...] = ()
    question_type: str = QUESTION_NONE
    temporal_cues: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()

    @property
    def is_ok(self) -> bool:
        return self.status == PROVIDER_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "tokens": list(self.tokens),
            "lemmas": list(self.lemmas),
            "pronouns": list(self.pronouns),
            "question_type": self.question_type,
            "temporal_cues": list(self.temporal_cues),
            "entities": list(self.entities),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["LinguisticEvidence"]:
        if not isinstance(data, dict):
            return None
        status = _bounded(data.get("status"), _MAX_PROVIDER_CHARS)
        if status not in PROVIDER_STATUSES:
            status = PROVIDER_UNAVAILABLE
        question_type = _bounded(data.get("question_type"), _MAX_PROVIDER_CHARS)
        if question_type not in QUESTION_TYPES and question_type != QUESTION_NONE:
            question_type = QUESTION_NONE
        return cls(
            provider=_bounded(data.get("provider"), _MAX_PROVIDER_CHARS),
            status=status,
            tokens=_bounded_items(data.get("tokens")),
            lemmas=_bounded_items(data.get("lemmas")),
            pronouns=_bounded_items(data.get("pronouns")),
            question_type=question_type,
            temporal_cues=_bounded_items(data.get("temporal_cues")),
            entities=_bounded_items(data.get("entities")),
        )


@dataclass(frozen=True, slots=True)
class EvidenceAdjudication:
    """Atlas's bounded, descriptive reading of the provider evidence."""

    status: str = ADJUDICATION_NATIVE_ONLY
    provider: str = ""
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "provider": self.provider, "notes": list(self.notes)}


@runtime_checkable
class LinguisticProvider(Protocol):
    """Optional linguistic evidence source. Advisory only, never authority."""

    name: str

    def analyse(self, text: str, *, context: Any = None) -> Any:
        """Return a bounded mapping of linguistic evidence, or ``None``."""
        ...


#: Pronouns / demonstratives the neutral provider surfaces (bounded vocabulary).
_PRONOUNS: frozenset[str] = frozenset(
    {"he", "she", "it", "they", "them", "him", "her", "their", "its",
     "this", "that", "these", "those"}
)
#: Bounded temporal/discourse cues.
_TEMPORAL_CUES: frozenset[str] = frozenset(
    {"now", "just", "earlier", "before", "after", "previous", "last", "later",
     "recently", "currently", "then"}
)
#: Leading question words.
_WH_WORDS: frozenset[str] = frozenset(
    {"what", "which", "who", "whom", "whose", "why", "when", "where", "how"}
)
#: Leading auxiliaries (yes/no questions).
_AUXILIARIES: frozenset[str] = frozenset(
    {"is", "are", "was", "were", "do", "does", "did", "can", "could", "would",
     "will", "should", "has", "have", "had", "may", "might"}
)


class NeutralLinguisticProvider:
    """The Atlas-native deterministic provider (no model, no dependency).

    It produces bounded surface evidence only (tokens, lemmas, pronouns, question
    type, temporal cues). It is deliberately NOT a parser and NOT a solver: it is
    the seam's baseline so the boundary is real and executable without an
    external NLP package.
    """

    name: str = "atlas-neutral"

    def analyse(self, text: str, *, context: Any = None) -> Any:
        if not isinstance(text, str) or not text.strip():
            return None
        surface = tokens(text)[:MAX_TOKENS]
        return {
            "tokens": list(surface),
            "lemmas": [normalize_token(token) for token in surface],
            "pronouns": [t for t in surface if t in _PRONOUNS],
            "question_type": _question_type(text, surface),
            "temporal_cues": [t for t in surface if t in _TEMPORAL_CUES],
        }


def _question_type(text: str, surface: tuple[str, ...]) -> str:
    if not surface:
        return QUESTION_NONE
    head = surface[0]
    if head in _WH_WORDS:
        return QUESTION_WH
    if head in _AUXILIARIES:
        return QUESTION_YES_NO
    if text.rstrip().endswith("?"):
        return QUESTION_YES_NO
    if head in {"please", "investigate", "explain", "research", "find", "tell",
                "show", "describe", "summarize", "summarise", "compare"}:
        return QUESTION_IMPERATIVE
    return QUESTION_DECLARATIVE


class LinguisticEvidenceService:
    """Runs the optional provider(s) fail-safe and normalises their evidence.

    Single-provider by design (the smallest justified boundary): the first
    provider that answers is used. Everything is bounded and provenance-marked.
    """

    def __init__(self, providers: "tuple[Any, ...] | None" = None) -> None:
        self._providers = tuple(providers or ())

    @property
    def providers(self) -> tuple[Any, ...]:
        return self._providers

    def analyse(self, text: Any, *, context: Any = None) -> LinguisticEvidence:
        """Return bounded evidence from the first provider, or ``unavailable``.

        Fail-safe: a raising provider yields ``error``; a non-mapping payload
        yields ``invalid``; a ``None`` payload yields ``unavailable``. In every
        case the deterministic path continues unchanged.
        """
        if not self._providers:
            return LinguisticEvidence(status=PROVIDER_UNAVAILABLE)
        if not isinstance(text, str) or not text.strip():
            return LinguisticEvidence(status=PROVIDER_UNAVAILABLE)
        for provider in self._providers:
            name = _bounded(getattr(provider, "name", ""), _MAX_PROVIDER_CHARS)
            try:
                raw = provider.analyse(text, context=context)
            except Exception:  # a provider must never break a turn
                return LinguisticEvidence(provider=name, status=PROVIDER_ERROR)
            if raw is None:
                return LinguisticEvidence(provider=name, status=PROVIDER_UNAVAILABLE)
            if not isinstance(raw, dict):
                return LinguisticEvidence(provider=name, status=PROVIDER_INVALID)
            return _normalise(raw, name)
        return LinguisticEvidence(status=PROVIDER_UNAVAILABLE)

    def adjudicate(
        self, evidence: LinguisticEvidence, *, deterministic_illocution: str = ""
    ) -> EvidenceAdjudication:
        """Describe how the provider evidence relates to the deterministic reading.

        Purely descriptive: ``native_only`` (no provider evidence), ``unavailable``
        (provider failed), ``corroborated`` (agrees on questionhood) or
        ``conflicting``. It never changes a decision.
        """
        if not isinstance(evidence, LinguisticEvidence) or not evidence.is_ok:
            return EvidenceAdjudication(
                status=ADJUDICATION_UNAVAILABLE,
                provider=getattr(evidence, "provider", ""),
                notes=("no provider evidence",),
            )
        det_question = deterministic_illocution == "question"
        provider_question = evidence.question_type in (QUESTION_WH, QUESTION_YES_NO)
        if not evidence.question_type:
            return EvidenceAdjudication(
                status=ADJUDICATION_NATIVE_ONLY, provider=evidence.provider
            )
        if provider_question == det_question:
            return EvidenceAdjudication(
                status=ADJUDICATION_CORROBORATED,
                provider=evidence.provider,
                notes=("question type agrees",),
            )
        return EvidenceAdjudication(
            status=ADJUDICATION_CONFLICTING,
            provider=evidence.provider,
            notes=("question type differs",),
        )


def _normalise(raw: dict, provider_name: str) -> LinguisticEvidence:
    """Whitelist + bound a provider's raw mapping into evidence (fail-closed)."""
    question_type = _bounded(raw.get("question_type"), _MAX_PROVIDER_CHARS)
    if question_type not in QUESTION_TYPES:
        question_type = QUESTION_NONE
    return LinguisticEvidence(
        provider=provider_name,
        status=PROVIDER_OK,
        tokens=_bounded_items(raw.get("tokens")),
        lemmas=_bounded_items(raw.get("lemmas")),
        pronouns=_bounded_items(raw.get("pronouns")),
        question_type=question_type,
        temporal_cues=_bounded_items(raw.get("temporal_cues")),
        entities=_bounded_items(raw.get("entities")),
    )


__all__ = [
    "LINGUISTIC_EVIDENCE_KEY",
    "PROVIDER_OK",
    "PROVIDER_UNAVAILABLE",
    "PROVIDER_INVALID",
    "PROVIDER_ERROR",
    "PROVIDER_STATUSES",
    "ADJUDICATION_NATIVE_ONLY",
    "ADJUDICATION_CORROBORATED",
    "ADJUDICATION_CONFLICTING",
    "ADJUDICATION_UNAVAILABLE",
    "QUESTION_WH",
    "QUESTION_YES_NO",
    "QUESTION_IMPERATIVE",
    "QUESTION_DECLARATIVE",
    "QUESTION_NONE",
    "QUESTION_TYPES",
    "MAX_TOKENS",
    "MAX_ITEMS",
    "LinguisticEvidence",
    "EvidenceAdjudication",
    "LinguisticProvider",
    "NeutralLinguisticProvider",
    "LinguisticEvidenceService",
]
