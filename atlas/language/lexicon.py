"""Atlas Language — lexical representation (STEP 1 foundation).

The Atlas-owned lexical layer that sits UNDER the existing L0–L10 conversation
architecture. It introduces no second pipeline: it supplies the meaning-facing
contracts the existing architecture previously expressed only as flat word
classes (:mod:`atlas.conversation.lexicon`).

Design contract (shared with the G1 lexicon and the linguistic seam):

* **pure** — standard library only: no clock, no randomness, no I/O, no network,
  no model, no embeddings, no kernel, no registry;
* **deterministic** — identical input yields identical output, and iteration
  order never depends on set/dict ordering;
* **bounded** — every collection has a hard cap; nothing grows at runtime;
* **serializable** — every public type has a deterministic ``to_dict``;
* **advisory only** — a lexical entry, sense or annotation NEVER routes,
  approves, executes or promotes anything. Meaning carries no authority.

A :class:`LexicalEntry` is deliberately *evidence-shaped*: every sense and
relation records its provenance, and an entry that is genuinely ambiguous keeps
that ambiguity visible (:attr:`LexicalEntry.ambiguous`) instead of collapsing to
one reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

#: Hard bounds (a malformed/oversized input can never produce unbounded work).
MAX_ENTRIES: int = 4096
MAX_SURFACE_FORMS: int = 16
MAX_ALIASES: int = 16
MAX_LEMMAS: int = 16
MAX_SENSES: int = 8
MAX_RELATIONS: int = 32
MAX_DOMAINS: int = 8
MAX_CONCEPTS: int = 16
MAX_TERM_CHARS: int = 64
MAX_TEXT_CHARS: int = 200
MAX_ANNOTATION_TOKENS: int = 64


class RelationKind(str, Enum):
    """The bounded semantic-relation vocabulary."""

    SYNONYM = "synonym"
    ANTONYM = "antonym"
    HYPERNYM = "hypernym"
    HYPONYM = "hyponym"
    RELATED = "related"


@dataclass(frozen=True, slots=True)
class SemanticRelation:
    """One typed, provenanced link from a term to another term."""

    kind: RelationKind
    target: str
    provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "target": self.target,
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class Sense:
    """One meaning of a term, with the Atlas concepts it may denote.

    ``atlas_concepts`` are canonical Atlas identifiers (a capability, component,
    module or operational capability). ``confidence`` is the *evidence*
    confidence for this sense, never a claim of certainty.
    """

    sense_id: str
    definition: str = ""
    domain: str = ""
    atlas_concepts: tuple[str, ...] = ()
    relations: tuple[SemanticRelation, ...] = ()
    provenance: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sense_id": self.sense_id,
            "definition": self.definition,
            "domain": self.domain,
            "atlas_concepts": list(self.atlas_concepts),
            "relations": [r.to_dict() for r in self.relations],
            "provenance": self.provenance,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class LexicalEntry:
    """A canonical term with its surface forms, senses and Atlas concepts.

    Smallest representation that satisfies the required contracts:

    * ``canonical_term`` — the term's identity;
    * ``surface_forms`` / ``aliases`` / ``lemmas`` — how text may refer to it;
    * ``senses`` — its meanings, each carrying concepts + relations + provenance;
    * ``domains`` / ``frequency`` — register and familiarity evidence;
    * ``atlas_concepts`` — the union of the senses' concepts (convenience);
    * ``ambiguous`` — True when the entry cannot be read as one concept;
    * ``provenance`` — where the entry came from (declared / provider name).
    """

    canonical_term: str
    surface_forms: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    lemmas: tuple[str, ...] = ()
    senses: tuple[Sense, ...] = ()
    domains: tuple[str, ...] = ()
    relations: tuple[SemanticRelation, ...] = ()
    frequency: float = 0.0
    atlas_concepts: tuple[str, ...] = ()
    ambiguous: bool = False
    provenance: str = ""

    def concepts(self) -> tuple[str, ...]:
        """The deduplicated union of this entry's own and sensed concepts."""
        seen: list[str] = []
        for concept in tuple(self.atlas_concepts) + tuple(
            c for sense in self.senses for c in sense.atlas_concepts
        ):
            text = str(concept or "").strip()
            if text and text not in seen:
                seen.append(text)
        return tuple(seen[:MAX_CONCEPTS])

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_term": self.canonical_term,
            "surface_forms": list(self.surface_forms),
            "aliases": list(self.aliases),
            "lemmas": list(self.lemmas),
            "senses": [s.to_dict() for s in self.senses],
            "domains": list(self.domains),
            "relations": [r.to_dict() for r in self.relations],
            "frequency": self.frequency,
            "atlas_concepts": list(self.atlas_concepts),
            "ambiguous": self.ambiguous,
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    """A deterministic, evidence-backed reading of a text's language/script."""

    language: str = "und"
    script: str = "unknown"
    direction: str = "ltr"
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()

    @property
    def known(self) -> bool:
        return self.language not in ("", "und")

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "script": self.script,
            "direction": self.direction,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class LinguisticAnnotation:
    """The bounded analysis of ONE text under a language profile."""

    surface: str = ""
    profile: LanguageProfile = field(default_factory=LanguageProfile)
    tokens: tuple[str, ...] = ()
    lemmas: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()
    entries: tuple[LexicalEntry, ...] = ()
    concepts: tuple[str, ...] = ()
    confidence: float = 0.0
    ambiguous: bool = False
    provenance: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "profile": self.profile.to_dict(),
            "tokens": list(self.tokens),
            "lemmas": list(self.lemmas),
            "matched_terms": list(self.matched_terms),
            "entries": [e.to_dict() for e in self.entries],
            "concepts": list(self.concepts),
            "confidence": self.confidence,
            "ambiguous": self.ambiguous,
            "provenance": list(self.provenance),
        }


def _bounded_terms(values: Iterable[Any], limit: int) -> tuple[str, ...]:
    """Ordered, de-duplicated, bounded, non-empty string terms."""
    out: list[str] = []
    for value in values or ():
        text = str(value or "").strip()[:MAX_TERM_CHARS]
        if text and text not in out:
            out.append(text)
    return tuple(out[:limit])


class Lexicon:
    """A bounded, deterministic lexical resource (the Atlas vocabulary).

    Entries are keyed by every one of their declared terms (canonical term,
    surface forms, aliases, lemmas) so a lookup is a single bounded dictionary
    read. Construction is deterministic: the first entry declaring a term owns
    it, and lookups return entries in insertion order.
    """

    def __init__(self, entries: Iterable[LexicalEntry] = ()) -> None:
        self._entries: list[LexicalEntry] = []
        self._index: dict[str, LexicalEntry] = {}
        for entry in entries or ():
            self.add(entry)

    # -- construction ------------------------------------------------------

    def add(self, entry: LexicalEntry) -> bool:
        """Add ``entry`` when it is well-formed and within bounds.

        Returns ``True`` when the entry was added. Never raises: a malformed
        entry is refused (fail-safe), and the lexicon is never grown past
        :data:`MAX_ENTRIES`.
        """
        if not isinstance(entry, LexicalEntry):
            return False
        term = str(entry.canonical_term or "").strip()[:MAX_TERM_CHARS]
        if not term or len(self._entries) >= MAX_ENTRIES:
            return False
        if term in self._index:
            return False
        self._entries.append(entry)
        for key in self._keys(entry):
            self._index.setdefault(key, entry)
        return True

    @staticmethod
    def _keys(entry: LexicalEntry) -> tuple[str, ...]:
        keys: list[str] = []
        for value in (
            entry.canonical_term,
            *entry.surface_forms,
            *entry.aliases,
            *entry.lemmas,
        ):
            text = str(value or "").strip()[:MAX_TERM_CHARS].lower()
            if text and text not in keys:
                keys.append(text)
        return tuple(keys)

    # -- queries (pure, read-only) ----------------------------------------

    def lookup(self, term: Any) -> LexicalEntry | None:
        """The entry declaring ``term``, or ``None`` (never a guess)."""
        if not isinstance(term, str):
            return None
        return self._index.get(term.strip()[:MAX_TERM_CHARS].lower())

    def entries(self) -> tuple[LexicalEntry, ...]:
        return tuple(self._entries)

    def size(self) -> int:
        return len(self._entries)

    def terms(self) -> tuple[str, ...]:
        """Every indexed term, alphabetically (deterministic ordering)."""
        return tuple(sorted(self._index))

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self._entries],
            "size": len(self._entries),
        }


def entry(
    canonical_term: Any,
    *,
    surface_forms: Iterable[Any] = (),
    aliases: Iterable[Any] = (),
    lemmas: Iterable[Any] = (),
    senses: Iterable[Sense] = (),
    domains: Iterable[Any] = (),
    relations: Iterable[SemanticRelation] = (),
    frequency: float = 0.0,
    atlas_concepts: Iterable[Any] = (),
    provenance: str = "",
) -> LexicalEntry:
    """Build a bounded :class:`LexicalEntry` (convenience, fail-safe).

    Ambiguity is COMPUTED, never declared by hand: an entry is ambiguous when
    its senses denote more than one distinct Atlas concept.
    """
    built_senses = tuple(s for s in (senses or ()) if isinstance(s, Sense))
    built_senses = built_senses[:MAX_SENSES]
    concepts = _bounded_terms(atlas_concepts, MAX_CONCEPTS)
    all_concepts: list[str] = list(concepts)
    for sense in built_senses:
        for concept in sense.atlas_concepts:
            text = str(concept or "").strip()
            if text and text not in all_concepts:
                all_concepts.append(text)
    distinct = tuple(dict.fromkeys(all_concepts))
    try:
        freq = float(frequency)
    except (TypeError, ValueError):
        freq = 0.0
    return LexicalEntry(
        canonical_term=str(canonical_term or "").strip()[:MAX_TERM_CHARS],
        surface_forms=_bounded_terms(surface_forms, MAX_SURFACE_FORMS),
        aliases=_bounded_terms(aliases, MAX_ALIASES),
        lemmas=_bounded_terms(lemmas, MAX_LEMMAS),
        senses=built_senses,
        domains=_bounded_terms(domains, MAX_DOMAINS),
        relations=tuple(r for r in (relations or ()) if isinstance(r, SemanticRelation))[
            :MAX_RELATIONS
        ],
        frequency=max(0.0, min(1.0, freq)),
        atlas_concepts=distinct[:MAX_CONCEPTS],
        ambiguous=len(distinct) > 1,
        provenance=str(provenance or "")[:MAX_TEXT_CHARS],
    )


def sense(
    sense_id: Any,
    *,
    definition: str = "",
    domain: str = "",
    atlas_concepts: Iterable[Any] = (),
    relations: Iterable[SemanticRelation] = (),
    provenance: str = "",
    confidence: float = 0.0,
) -> Sense:
    """Build a bounded :class:`Sense` (convenience, fail-safe)."""
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 0.0
    return Sense(
        sense_id=str(sense_id or "").strip()[:MAX_TERM_CHARS],
        definition=str(definition or "")[:MAX_TEXT_CHARS],
        domain=str(domain or "")[:MAX_TERM_CHARS],
        atlas_concepts=_bounded_terms(atlas_concepts, MAX_CONCEPTS),
        relations=tuple(r for r in (relations or ()) if isinstance(r, SemanticRelation))[
            :MAX_RELATIONS
        ],
        provenance=str(provenance or "")[:MAX_TEXT_CHARS],
        confidence=max(0.0, min(1.0, conf)),
    )


def relation(kind: RelationKind | str, target: Any, *, provenance: str = "") -> SemanticRelation:
    """Build a bounded :class:`SemanticRelation` (unknown kind -> RELATED)."""
    if isinstance(kind, RelationKind):
        resolved = kind
    else:
        try:
            resolved = RelationKind(str(kind or "").strip().lower())
        except ValueError:
            resolved = RelationKind.RELATED
    return SemanticRelation(
        kind=resolved,
        target=str(target or "").strip()[:MAX_TERM_CHARS],
        provenance=str(provenance or "")[:MAX_TEXT_CHARS],
    )
