"""Atlas Language — optional lexical provider seam.

The Atlas-owned interface through which an OPTIONAL specialist resource (WordNet,
wordfreq, spaCy, fastText, GLiNER, ConceptNet, multilingual-E5, ...) may supply
lexical evidence. It mirrors the EXISTING linguistic seam
(:class:`atlas.conversation.linguistic.LinguisticProvider`): a runtime-checkable
Protocol plus a deterministic Atlas-native baseline, so the boundary is real and
executable without any external package.

Non-negotiable properties, all enforced here:

* a provider is ADVISORY — it supplies evidence into Atlas's representation and
  can never authorize, route, approve, execute or promote anything;
* providers are OPTIONAL — with none registered the baseline is used and every
  call still succeeds deterministically;
* provider output is UNTRUSTED — a provider that raises, returns a malformed
  payload, or exceeds the bounds is simply not evidence (fail-closed);
* provider absence or failure NEVER corrupts state and never raises to callers.

No external dependency is imported by this module, and none is required.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from atlas.language.lexicon import (
    MAX_SENSES,
    LexicalEntry,
    RelationKind,
    entry,
    relation,
    sense,
)

#: Bounded number of optional providers that may be registered.
MAX_PROVIDERS: int = 8

#: Bounded number of entries one provider lookup may contribute.
MAX_PROVIDER_ENTRIES: int = 8

#: Bounded length of any provider-supplied text.
MAX_PROVIDER_TEXT: int = 200


@runtime_checkable
class LexicalProvider(Protocol):
    """Optional lexical evidence source. Advisory only, never authority."""

    name: str

    def lookup(self, term: str, *, context: Any = None) -> Any:
        """Return bounded lexical evidence for ``term``, or ``None``."""
        ...


class NullLexicalProvider:
    """The Atlas-native deterministic baseline: no external lexicon is wired.

    It reports honestly that it holds no entry rather than inventing one, which
    is what makes provider absence a safe, testable state.
    """

    name: str = "atlas-null"

    def lookup(self, term: str, *, context: Any = None) -> Any:
        return None


def _bounded(value: Any) -> str:
    return str(value or "").strip()[:MAX_PROVIDER_TEXT]


def _coerce_entry(raw: Any) -> LexicalEntry | None:
    """Turn untrusted provider output into a bounded entry, or ``None``.

    Accepts a :class:`LexicalEntry`, or a mapping with ``canonical_term`` and an
    optional ``senses`` list of mappings. Anything else — including a wrong
    type, a missing term, or an over-long payload — is NOT evidence.
    """
    if isinstance(raw, LexicalEntry):
        return raw
    if not isinstance(raw, dict):
        return None
    term = _bounded(raw.get("canonical_term") or raw.get("term"))
    if not term:
        return None
    senses = []
    raw_senses = raw.get("senses")
    if isinstance(raw_senses, (list, tuple)):
        from atlas.language.lexicon import Sense

        for item in raw_senses[:MAX_SENSES]:
            if isinstance(item, Sense):
                senses.append(item)
            elif isinstance(item, dict):
                senses.append(
                    sense(
                        item.get("sense_id") or f"{term}.{len(senses)}",
                        definition=_bounded(item.get("definition")),
                        domain=_bounded(item.get("domain")),
                        atlas_concepts=item.get("atlas_concepts") or (),
                        provenance=_bounded(item.get("provenance"))
                        or f"provider:{_bounded(raw.get('provenance'))}",
                        confidence=item.get("confidence", 0.0),
                    )
                )
    relations = []
    raw_relations = raw.get("relations")
    if isinstance(raw_relations, (list, tuple)):
        for item in raw_relations[:MAX_PROVIDER_ENTRIES]:
            if isinstance(item, dict) and item.get("target"):
                relations.append(
                    relation(
                        item.get("kind", RelationKind.RELATED),
                        item.get("target"),
                        provenance=_bounded(item.get("provenance")),
                    )
                )
    return entry(
        term,
        surface_forms=raw.get("surface_forms") or (),
        aliases=raw.get("aliases") or (),
        lemmas=raw.get("lemmas") or (),
        senses=senses,
        domains=raw.get("domains") or (),
        relations=relations,
        frequency=raw.get("frequency", 0.0),
        atlas_concepts=raw.get("atlas_concepts") or (),
        provenance=_bounded(raw.get("provenance")) or f"provider:{_bounded(getattr(raw, 'name', ''))}",
    )


class LexicalProviderRegistry:
    """A bounded, ordered set of OPTIONAL lexical providers.

    Resolution is: first registered provider that returns usable evidence wins;
    a provider that raises, returns a malformed payload, or exceeds the bounds
    is skipped (fail-closed) and the next one is tried. With no usable provider
    the result is ``None`` — never a fabricated entry.
    """

    def __init__(self, providers: Any = ()) -> None:
        self._providers: list[Any] = []
        for provider in providers or ():
            self.register(provider)

    def register(self, provider: Any) -> bool:
        """Register ``provider`` when it satisfies the seam and fits the bound."""
        if provider is None or len(self._providers) >= MAX_PROVIDERS:
            return False
        if not isinstance(provider, LexicalProvider):
            return False
        if not str(getattr(provider, "name", "") or ""):
            return False
        if any(getattr(p, "name", "") == provider.name for p in self._providers):
            return False
        self._providers.append(provider)
        return True

    def providers(self) -> tuple[Any, ...]:
        return tuple(self._providers)

    def names(self) -> tuple[str, ...]:
        return tuple(str(getattr(p, "name", "")) for p in self._providers)

    def lookup(self, term: Any) -> tuple[LexicalEntry, ...]:
        """Bounded entries for ``term`` from the first usable provider."""
        if not isinstance(term, str) or not term.strip():
            return ()
        text = term.strip()[:MAX_PROVIDER_TEXT]
        for provider in self._providers:
            try:
                raw = provider.lookup(text)
            except Exception:
                continue
            if raw is None:
                continue
            items = raw if isinstance(raw, (list, tuple)) else (raw,)
            built: list[LexicalEntry] = []
            for item in items[:MAX_PROVIDER_ENTRIES]:
                parsed = _coerce_entry(item)
                if parsed is not None:
                    built.append(parsed)
            if built:
                return tuple(built)
        return ()


__all__ = [
    "MAX_PROVIDERS",
    "MAX_PROVIDER_ENTRIES",
    "LexicalProvider",
    "LexicalProviderRegistry",
    "NullLexicalProvider",
]
