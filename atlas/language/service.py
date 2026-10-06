"""Atlas Language — the cohesive foundation entry point (STEP 1).

One object ties the foundation together so there is exactly ONE coherent path:

    text -> normalize (L2) -> language profile/routing -> lexical analysis
         -> Atlas concept resolution (L1/L3-facing)

It is deliberately thin: each stage delegates to the module that owns it, and
the object holds no state that Atlas's authoritative conversation state does not
already own. Nothing here routes, approves, executes or promotes; the annotation
is evidence that existing Atlas layers may consult.

Pure: standard library only. No model, no network, no kernel, no registry.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from atlas.language.lexicon import (
    MAX_ANNOTATION_TOKENS,
    LinguisticAnnotation,
    LanguageProfile,
    LexicalEntry,
    Lexicon,
)
from atlas.language.normalizer import lemmatize, normalize, tokenize
from atlas.language.providers import LexicalProviderRegistry
from atlas.language.routing import detect_language, route_language
from atlas.language.vocabulary import (
    VocabularyResolution,
    VocabularyResolver,
    vocabulary_from_sources,
)

#: Bound on the matched terms reported for one annotation.
MAX_MATCHED_TERMS: int = 16


class LanguageService:
    """The Atlas language foundation: analysis + Atlas concept resolution.

    Args:
        lexicon: The bounded lexical resource (usually projected from Atlas's
            existing authoritative vocabularies via :func:`vocabulary_from_sources`).
        providers: Optional specialist lexical providers behind the Atlas-owned
            seam. ``None``/empty is the normal, fully-supported state.
    """

    def __init__(self, lexicon: Lexicon | None = None, *, providers: Any = ()) -> None:
        self._resolver = VocabularyResolver(lexicon, providers=providers)

    @classmethod
    def from_sources(
        cls,
        sources: Mapping[str, Iterable[Any]] | None = None,
        *,
        providers: Any = (),
    ) -> "LanguageService":
        """Build a service whose lexicon is the projection of Atlas sources."""
        return cls(vocabulary_from_sources(sources, providers=providers), providers=providers)

    # -- stages ------------------------------------------------------------

    @property
    def lexicon(self) -> Lexicon:
        return self._resolver.lexicon

    @property
    def providers(self) -> LexicalProviderRegistry:
        return self._resolver.providers

    def profile(self, text: Any) -> LanguageProfile:
        """The bounded language/script profile of ``text``."""
        return detect_language(text)

    def route(self, text: Any) -> str:
        """The language routing decision for ``text``."""
        return route_language(self.profile(text))

    def resolve(self, surface: Any) -> VocabularyResolution:
        """Resolve ``surface`` to Atlas concept(s), preserving ambiguity."""
        return self._resolver.resolve(surface)

    def analyse(self, text: Any, *, context: Any = None) -> LinguisticAnnotation:
        """The bounded linguistic annotation of ``text``.

        ``context`` is accepted for interface parity with the existing linguistic
        seam and to let providers use it; the foundation itself reads no state
        beyond ``text`` (Atlas conversation state stays authoritative).
        """
        if not isinstance(text, str) or not text.strip():
            return LinguisticAnnotation(provenance=("empty-or-non-text",))
        profile = self.profile(text)
        normalized = normalize(text)
        surfaces = tuple(tokenize(normalized))[:MAX_ANNOTATION_TOKENS]
        lemmas = tuple(lemmatize(normalized))[:MAX_ANNOTATION_TOKENS]

        matched_terms: list[str] = []
        entries: list[LexicalEntry] = []
        concepts: list[str] = []
        provenance: list[str] = ["atlas-language"]
        ambiguous = False
        confidence = 0.0

        for term in (normalized, *surfaces):
            resolution = self._resolver.resolve(term)
            if resolution.status.value == "unresolved":
                continue
            if resolution.canonical_concept and resolution.canonical_concept not in concepts:
                concepts.append(resolution.canonical_concept)
            for candidate in resolution.candidates:
                if candidate not in concepts:
                    concepts.append(candidate)
            if resolution.status.value == "ambiguous":
                ambiguous = True
            if resolution.matched_term and resolution.matched_term not in matched_terms:
                matched_terms.append(resolution.matched_term)
            found = self._resolver.lexicon.lookup(resolution.matched_term)
            if found is not None and found not in entries:
                entries.append(found)
            for origin in resolution.provenance:
                if origin not in provenance:
                    provenance.append(origin)
            confidence = max(confidence, resolution.confidence)

        return LinguisticAnnotation(
            surface=normalized[:200],
            profile=profile,
            tokens=surfaces,
            lemmas=lemmas,
            matched_terms=tuple(matched_terms[:MAX_MATCHED_TERMS]),
            entries=tuple(entries[:MAX_MATCHED_TERMS]),
            concepts=tuple(concepts[:MAX_MATCHED_TERMS]),
            confidence=confidence,
            ambiguous=ambiguous,
            provenance=tuple(provenance),
        )


__all__ = ["LanguageService", "MAX_MATCHED_TERMS"]
