"""L4 — bounded deterministic entity identification for the current turn.

Identifies which *known* Atlas entities a user explicitly named in the current
turn. The mechanism is purely lexical and deterministic: catalog names are
matched against the normalized turn text with word-bounded, separator-tolerant
patterns (``code_inspector``, ``code inspector`` and ``code-inspector`` are the
same name). A name that is not literally present in the turn is never
identified — there is no model, no network, no embedding, no fuzzy match and no
inference of any kind.

Identification reports evidence only. It never resolves a reference, never
disambiguates between entities, never authorizes anything, and never guesses:
an absent or unmatched entity is simply not reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from atlas.conversation.normalization import collapse_whitespace

#: Evidence key used on the existing bounded ``TaskSpec.context`` channel.
IDENTIFIED_ENTITIES_KEY = "identified_entities"

#: Upper bound on entities reported for a single turn.
MAX_IDENTIFIED_ENTITIES = 8

#: Separator runs treated as equivalent inside a catalog name.
_NAME_SEPARATOR_RE = re.compile(r"[._\s-]+")

#: Regex source for the same separator runs.
_NAME_SEPARATORS = r"[._\s-]+"

#: Compiled per-name patterns, keyed by catalog name (bounded by catalog size).
_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _name_pattern(name: str) -> re.Pattern[str]:
    """Return the word-bounded, separator-tolerant pattern for ``name``."""
    pattern = _PATTERN_CACHE.get(name)
    if pattern is None:
        parts = [
            re.escape(part) for part in _NAME_SEPARATOR_RE.split(name.lower()) if part
        ]
        body = _NAME_SEPARATORS.join(parts) if parts else re.escape(name.lower())
        pattern = re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")
        _PATTERN_CACHE[name] = pattern
    return pattern


@dataclass(frozen=True, slots=True)
class IdentifiedEntity:
    """One explicitly named known entity. Evidence only, never authority."""

    name: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a JSON-safe dict."""
        return {"name": self.name, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class EntityCatalog:
    """Immutable, ordered catalog of known entity names.

    ``entries`` is a bounded tuple of ``(name, kind)`` pairs. Ordering is the
    caller's insertion order; matching order is derived deterministically from
    it (most specific first).
    """

    entries: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_names(
        cls, names_by_kind: Mapping[str, Iterable[str]]
    ) -> "EntityCatalog":
        """Build a catalog, deduplicated case-insensitively.

        The first kind seen for a duplicated name wins, so the result depends
        only on the caller's deterministic iteration order. Non-string and
        blank names are ignored.
        """
        seen: set[str] = set()
        entries: list[tuple[str, str]] = []
        for kind, names in names_by_kind.items():
            for name in names:
                if not isinstance(name, str):
                    continue
                cleaned = name.strip()
                key = cleaned.lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                entries.append((cleaned, str(kind)))
        return cls(tuple(entries))


def identify_entities(
    text: str, catalog: EntityCatalog | None
) -> tuple[IdentifiedEntity, ...]:
    """Identify the known entities explicitly named in ``text``.

    Deterministic and fail-closed: with no catalog (or no match) the result is
    empty. Matches are reported most-specific-first (longest name, then
    alphabetical), so the reported order never depends on text position.
    """
    if catalog is None or not catalog.entries:
        return ()
    normalized = collapse_whitespace(text)
    if not normalized:
        return ()
    normalized = normalized.lower()

    identified: list[IdentifiedEntity] = []
    seen: set[str] = set()
    for name, kind in sorted(catalog.entries, key=lambda e: (-len(e[0]), e[0])):
        key = _NAME_SEPARATOR_RE.sub(" ", name.lower())
        if key in seen:
            continue
        if _name_pattern(name).search(normalized):
            seen.add(key)
            identified.append(IdentifiedEntity(name=name, kind=kind))
        if len(identified) >= MAX_IDENTIFIED_ENTITIES:
            break
    return tuple(identified)
