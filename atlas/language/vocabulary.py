"""Atlas Language — vocabulary resolution (surface text -> Atlas concepts).

The ONE place a surface term is resolved to the Atlas concepts it may denote.
It does not create a source of truth: callers project the EXISTING authoritative
Atlas vocabularies (operational capabilities and their aliases, registered
components, capability-model names) into lexical entries, and this resolver
answers against that bounded resource.

Ambiguity is REPRESENTED, never resolved by preference: a term whose evidence
supports more than one distinct Atlas concept resolves to ``AMBIGUOUS`` with all
candidates, so the caller can clarify instead of guessing. ``UNRESOLVED`` is the
honest default for unknown text.

Pure: standard library only — no clock, randomness, I/O, network, model, kernel
or registry. Resolution grants no authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from atlas.language.lexicon import MAX_CONCEPTS, LexicalEntry, Lexicon
from atlas.language.normalizer import lemmatize, normalize
from atlas.language.providers import LexicalProviderRegistry

#: Bounded number of candidate concepts a resolution may report.
MAX_CANDIDATES: int = 16


class VocabularyStatus(str, Enum):
    """Whether a surface term resolves to exactly one concept, many, or none."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class VocabularyResolution:
    """The bounded outcome of resolving one surface form."""

    surface: str = ""
    status: VocabularyStatus = VocabularyStatus.UNRESOLVED
    canonical_concept: str = ""
    candidates: tuple[str, ...] = ()
    matched_term: str = ""
    evidence: tuple[str, ...] = ()
    confidence: float = 0.0
    provenance: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status is VocabularyStatus.RESOLVED and bool(self.canonical_concept)

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "status": self.status.value,
            "canonical_concept": self.canonical_concept,
            "candidates": list(self.candidates),
            "matched_term": self.matched_term,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "provenance": list(self.provenance),
        }


def vocabulary_from_sources(
    sources: Mapping[str, Iterable[Any]] | None = None,
    *,
    providers: Any = (),
) -> Lexicon:
    """Project Atlas's EXISTING vocabularies into a bounded :class:`Lexicon`.

    ``sources`` maps an Atlas source name (e.g. ``"operational_capability"``,
    ``"component"``, ``"capability"``) to the authoritative names that source
    declares. The caller supplies those names from the real structures — this
    function invents nothing, and it is the only place a concept's origin is
    recorded. Provider entries (if any) are added afterwards, so a declared
    Atlas fact always wins over an external resource.
    """
    lexicon = Lexicon()
    for source, names in (sources or {}).items():
        origin = str(source or "").strip()
        for name in tuple(names or ()):
            text = str(name or "").strip()
            if not text:
                continue
            from atlas.language.lexicon import entry

            lexicon.add(
                entry(
                    text,
                    aliases=(text,),
                    lemmas=lemmatize(text.replace(".", " ").replace("_", " ")),
                    atlas_concepts=(text,),
                    domains=(origin,) if origin else (),
                    provenance=f"atlas:{origin or 'declared'}",
                )
            )
    registry = LexicalProviderRegistry(providers)
    if registry.providers():
        for provider_name in registry.names():
            for concept in _provider_seed_terms(registry, provider_name):
                for built in registry.lookup(concept):
                    lexicon.add(built)
    return lexicon


def _provider_seed_terms(registry: LexicalProviderRegistry, provider_name: str) -> tuple[str, ...]:
    """Bounded terms a provider seeds the lexicon with (``seed_terms`` hook).

    Optional: a provider may expose ``seed_terms()`` returning the bounded terms
    it can answer for. A provider without the hook seeds nothing — it is still
    consulted on lookup.
    """
    for provider in registry.providers():
        if str(getattr(provider, "name", "")) != provider_name:
            continue
        hook = getattr(provider, "seed_terms", None)
        if not callable(hook):
            return ()
        try:
            seeded = hook()
        except Exception:
            return ()
        return tuple(str(t).strip() for t in tuple(seeded or ())[:MAX_CONCEPTS] if str(t).strip())
    return ()


class VocabularyResolver:
    """Deterministic surface -> Atlas concept resolution over a bounded lexicon.

    Resolution order (first hit wins, all deterministic):

    1. the WHOLE normalized surface as a lexicon term (strongest evidence);
    2. the normalized surface's individual tokens, in token order.

    A hit whose entry declares one distinct Atlas concept resolves; a hit that
    is ambiguous, or several hits that disagree, yields ``AMBIGUOUS`` with the
    bounded candidate set; no hit yields ``UNRESOLVED``.
    """

    def __init__(self, lexicon: Lexicon | None = None, *, providers: Any = ()) -> None:
        self._lexicon = lexicon if isinstance(lexicon, Lexicon) else Lexicon()
        self._providers = LexicalProviderRegistry(providers)

    @property
    def lexicon(self) -> Lexicon:
        return self._lexicon

    @property
    def providers(self) -> LexicalProviderRegistry:
        return self._providers

    def _entries_for(self, term: str) -> tuple[LexicalEntry, ...]:
        """Declared entries win; the optional providers are consulted only on a miss."""
        found = self._lexicon.lookup(term)
        if found is not None:
            return (found,)
        return self._providers.lookup(term)

    def resolve(self, surface: Any) -> VocabularyResolution:
        """Resolve ``surface`` to Atlas concepts (never a guess)."""
        if not isinstance(surface, str) or not surface.strip():
            return VocabularyResolution(surface=str(surface or "")[:200])

        text = normalize(surface)
        if not text:
            return VocabularyResolution(surface=surface[:200])

        matches: list[tuple[str, LexicalEntry]] = []
        whole = self._lexicon.lookup(text)
        if whole is not None:
            matches.append((text, whole))
        else:
            for token in lemmatize(text):
                for candidate in (token,):
                    found = self._entries_for(candidate)
                    for item in found:
                        matches.append((candidate, item))
                if matches:
                    break

        concepts: list[str] = []
        evidence: list[str] = []
        provenance: list[str] = []
        matched_term = ""
        confidence = 0.0
        ambiguous = False
        for term, item in matches:
            matched_term = matched_term or term
            for concept in item.concepts():
                if concept not in concepts:
                    concepts.append(concept)
            if item.ambiguous:
                ambiguous = True
            if item.provenance and item.provenance not in provenance:
                provenance.append(item.provenance)
            confidence = max(confidence, float(getattr(item, "frequency", 0.0) or 0.0))

        bounded = tuple(concepts[:MAX_CANDIDATES])
        if not bounded:
            return VocabularyResolution(
                surface=text[:200],
                status=VocabularyStatus.UNRESOLVED,
                evidence=("no-lexical-entry",),
            )
        if len(bounded) > 1 or ambiguous:
            return VocabularyResolution(
                surface=text[:200],
                status=VocabularyStatus.AMBIGUOUS,
                candidates=bounded,
                matched_term=matched_term,
                evidence=("multiple-concepts",) if len(bounded) > 1 else ("entry-ambiguous",),
                confidence=confidence,
                provenance=tuple(provenance),
            )
        return VocabularyResolution(
            surface=text[:200],
            status=VocabularyStatus.RESOLVED,
            canonical_concept=bounded[0],
            candidates=bounded,
            matched_term=matched_term,
            evidence=("lexical-entry",),
            confidence=confidence,
            provenance=tuple(provenance),
        )


__all__ = [
    "MAX_CANDIDATES",
    "VocabularyResolution",
    "VocabularyResolver",
    "VocabularyStatus",
    "vocabulary_from_sources",
]
