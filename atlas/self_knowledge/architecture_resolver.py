"""Atlas Self-Knowledge — deterministic architectural TARGET RESOLUTION.

Maps a natural-language surface form onto a **canonical Atlas architectural
identity**, or reports honestly that it cannot.

Why this exists. ``ArchitectureModel.locate()`` is a strict CANONICAL lookup: it
resolves ``"conversation_service"`` and ``"atlas.conversation.conversation_service"``
but not ``"the conversation service"``. Development grounding therefore had no
way to address a component by name, and fell back to per-token lookups that
either missed (``conversation`` matches a capability and yields no module) or
matched an unrelated symbol (``planner`` → ``atlas.research.capability_handlers``).

This module is the addressing layer. It is **derived data over the EXISTING
authoritative registries** exposed by ``ArchitectureModel`` — it is never a
second authority, never invents an identity, and cannot authorize anything.

Determinism. Pure functions over the supplied model; no clock, no I/O, no
model/provider, no network. Identical input yields an identical index and an
identical resolution, on this instance or a fresh one.

Ambiguity policy (the settled architectural decision):

* ``expected_type`` supplied → candidates of other identity types are EXCLUDED
  (never down-ranked). Exactly one survivor → ``RESOLVED``; more than one →
  ``AMBIGUOUS``; none → ``UNRESOLVED``.
* ``expected_type`` absent → exactly one identity across ALL supported types →
  ``RESOLVED``; more than one → ``AMBIGUOUS``; none → ``UNRESOLVED``.
* An unknown/unsupported ``expected_type`` → ``UNRESOLVED``. It is never
  coerced into another type.

Atlas NEVER selects an identity because it is "probably" what the user meant.
One canonical identity reached through several surface forms is NOT ambiguity;
two DISTINCT canonical identities ARE.

Surface handling is deliberately mechanical: separator/case variants,
word-bounded article-prefixed phrases, dotted paths, and PascalCase/camelCase
splitting. There is no pluralization, no synonym expansion, no fuzzy or phonetic
matching, no embedding and no paraphrase understanding — ``"the thing that
handles conversations"`` is out of scope by design and stays unresolved.

Identity types reuse ``ArchitectureModel``'s EXISTING ``matched_kind``
vocabulary (``capability | component | module | package | symbol``); no new
type enum is introduced, and a ``tool`` is a *capability* of kind ``tool``,
never a separate namespace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Reuse the EXISTING status contract rather than a redundant enum.
from atlas.conversation.reference_resolution import ReferenceResolutionStatus

#: Identity types Atlas already distinguishes, via ``matched_kind``.
#: ``tool`` is deliberately absent: a tool IS a capability of kind "tool".
SUPPORTED_IDENTITY_TYPES: frozenset[str] = frozenset(
    {"capability", "component", "module", "package", "symbol"}
)

#: Separator runs treated as equivalent inside an identity name — the SAME set
#: the existing ``entity_identification`` mechanism uses.
_NAME_SEPARATOR_RE = re.compile(r"[._\s-]+")

#: Bounds (a malformed or oversized surface can never produce an unbounded index).
_MAX_IDENTITIES = 4096
_MAX_SURFACE_CHARS = 200
_MAX_CANDIDATES = 16

#: Acronym-aware camel/Pascal boundary: split ``HTTPServer`` but keep ``MyURL``.
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _split_identifier_parts(name: str) -> tuple[str, ...]:
    """Split an identifier into lowercase parts on separators AND case changes.

    Deterministic and total: ``conversation_service`` → ``("conversation",
    "service")``; ``ConversationService`` → the same; ``HTTPServer`` →
    ``("http", "server")``. Never guesses a word that is not present.
    """
    if not isinstance(name, str) or not name:
        return ()
    spaced = _NAME_SEPARATOR_RE.sub(" ", name.strip())
    parts: list[str] = []
    for chunk in spaced.split():
        for piece in _CAMEL_BOUNDARY_RE.split(chunk):
            cleaned = piece.strip().lower()
            if cleaned:
                parts.append(cleaned)
    return tuple(parts)


def _surface_key(text: str) -> str:
    """Deterministic comparison key: parts joined by a single space."""
    return " ".join(_split_identifier_parts(text))


@dataclass(frozen=True, slots=True)
class ArchitectureIdentity:
    """One canonical architectural identity derived from an authoritative source.

    Evidence only: it names where the identity came from and never grants
    authority.
    """

    canonical_id: str
    identity_type: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {
            "canonical_id": self.canonical_id,
            "identity_type": self.identity_type,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ArchitectureResolution:
    """The result of resolving one surface form.

    ``status`` distinguishes "Atlas knows exactly what this means" (RESOLVED)
    from "Atlas found several plausible things" (AMBIGUOUS) and "Atlas does not
    know" (UNRESOLVED). There is deliberately no confidence score: nothing here
    has a probabilistic meaning.
    """

    status: ReferenceResolutionStatus
    matched_surface: str = ""
    canonical_id: str = ""
    identity_type: str = ""
    candidates: tuple[ArchitectureIdentity, ...] = ()
    evidence: tuple[str, ...] = ()

    @property
    def is_resolved(self) -> bool:
        return self.status is ReferenceResolutionStatus.RESOLVED

    @property
    def is_ambiguous(self) -> bool:
        return self.status is ReferenceResolutionStatus.AMBIGUOUS

    @property
    def is_unresolved(self) -> bool:
        return self.status is ReferenceResolutionStatus.UNRESOLVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "matched_surface": self.matched_surface,
            "canonical_id": self.canonical_id,
            "identity_type": self.identity_type,
            "candidates": [c.to_dict() for c in self.candidates],
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class _IndexEntry:
    """One derived alias → canonical identity binding."""

    key: str
    identity: ArchitectureIdentity


class ArchitectureTargetResolver:
    """Derived, read-only address index over an existing ``ArchitectureModel``.

    The model — and the registries behind it — remain authoritative. This class
    only makes their existing identities *addressable* by the names people
    actually type. It never creates, mutates or persists an identity.

    ``architecture_model`` may be a model OR a zero-argument callable returning
    one (the same cache-only provider pattern the development planner uses).
    The callable form matters at STARTUP: the kernel builds the conversation
    before the repository map exists, so a snapshot taken then addresses only
    the component/capability identities and silently cannot see module
    identities that become available later. With a provider the index is derived
    from the CURRENT model on first use and cached, so it never invents an
    identity and never goes stale for the life of one Atlas session unless the
    caller supplies a fresh resolver.
    """

    __slots__ = ("_provider", "_entries", "_identity_count")

    def __init__(self, architecture_model: Any | None = None) -> None:
        self._provider: Any | None = None
        self._entries: tuple[_IndexEntry, ...] = ()
        self._identity_count: int = 0
        if callable(architecture_model) and not hasattr(architecture_model, "locate"):
            self._provider = architecture_model
        elif architecture_model is not None:
            self._entries, self._identity_count = _build_index(architecture_model)

    def _ensure_index(self) -> None:
        """Derive the index from the live model once, lazily (fail-soft)."""
        if self._entries or self._provider is None:
            return
        try:
            model = self._provider()
        except Exception:
            # Leave the index empty: resolution then fails closed rather than
            # raising or inventing anything.
            return
        if model is None:
            return
        self._entries, self._identity_count = _build_index(model)

    # ------------------------------------------------------------------
    # Introspection (evidence; the index is derived and inspectable)
    # ------------------------------------------------------------------

    @property
    def identity_count(self) -> int:
        """Number of DISTINCT canonical identities this index addresses."""
        return self._identity_count

    @property
    def entry_count(self) -> int:
        """Number of derived surface bindings (one identity may have several)."""
        return len(self._entries)

    def identities(self) -> tuple[ArchitectureIdentity, ...]:
        """Every distinct addressed identity, deterministically ordered."""
        self._ensure_index()
        seen: dict[str, ArchitectureIdentity] = {}
        for entry in self._entries:
            seen.setdefault(
                f"{entry.identity.identity_type}:{entry.identity.canonical_id}",
                entry.identity,
            )
        return tuple(seen.values())

    def is_authoritative_id(self, canonical_id: str, identity_type: str) -> bool:
        """True when ``canonical_id`` exists in the model as ``identity_type``."""
        if not isinstance(canonical_id, str) or not canonical_id:
            return False
        self._ensure_index()
        want = f"{identity_type}:{canonical_id}"
        return any(
            f"{e.identity.identity_type}:{e.identity.canonical_id}" == want
            for e in self._entries
        )

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(
        self,
        surface: str,
        *,
        expected_type: str | None = None,
    ) -> ArchitectureResolution:
        """Resolve one surface form to a canonical architectural identity.

        Follows the settled policy exactly: an ``expected_type`` EXCLUDES other
        types rather than down-ranking them; its absence preserves every
        distinct identity; one survivor resolves and several are AMBIGUOUS.
        Never picks one candidate over another.
        """
        if expected_type is not None and expected_type not in SUPPORTED_IDENTITY_TYPES:
            # An unsupported type cannot select anything and is never coerced.
            return ArchitectureResolution(
                status=ReferenceResolutionStatus.UNRESOLVED,
                matched_surface=_bounded_surface(surface),
                evidence=("unsupported_expected_type",),
            )
        if not isinstance(surface, str) or not surface.strip():
            return ArchitectureResolution(
                status=ReferenceResolutionStatus.UNRESOLVED,
                evidence=("empty_surface",),
            )

        self._ensure_index()
        key = _surface_key(surface[:_MAX_SURFACE_CHARS])
        if not key:
            return ArchitectureResolution(
                status=ReferenceResolutionStatus.UNRESOLVED,
                matched_surface=_bounded_surface(surface),
                evidence=("unresolvable_surface",),
            )

        # Pass 1 — find the STRONGEST (longest) surface that covers the query.
        # Longest-match selects the strongest SPAN only; it never chooses between
        # distinct canonical identities.
        best_parts = 0
        for entry in self._entries:
            if _surface_covers(entry.key, key):
                parts = len(entry.key.split())
                if parts > best_parts:
                    best_parts = parts
        if best_parts == 0:
            return ArchitectureResolution(
                status=ReferenceResolutionStatus.UNRESOLVED,
                matched_surface=_bounded_surface(surface),
                evidence=("no_authoritative_identity",),
            )

        # Pass 2 — collect DISTINCT canonical identities at exactly that
        # specificity. Several surface bindings for the SAME identity collapse,
        # so representation differences are never reported as ambiguity; two
        # DISTINCT identities are.
        found: dict[tuple[str, str], ArchitectureIdentity] = {}
        for entry in self._entries:
            if len(entry.key.split()) != best_parts:
                continue
            if not _surface_covers(entry.key, key):
                continue
            found.setdefault(
                (entry.identity.identity_type, entry.identity.canonical_id),
                entry.identity,
            )

        if expected_type is not None:
            found = {k: v for k, v in found.items() if k[0] == expected_type}

        if not found:
            return ArchitectureResolution(
                status=ReferenceResolutionStatus.UNRESOLVED,
                matched_surface=_bounded_surface(surface),
                evidence=("no_authoritative_identity",),
            )

        ordered = tuple(
            sorted(found.values(), key=lambda i: (i.identity_type, i.canonical_id))
        )
        if len(ordered) == 1:
            only = ordered[0]
            return ArchitectureResolution(
                status=ReferenceResolutionStatus.RESOLVED,
                matched_surface=_bounded_surface(surface),
                canonical_id=only.canonical_id,
                identity_type=only.identity_type,
                evidence=(only.source,),
            )
        return ArchitectureResolution(
            status=ReferenceResolutionStatus.AMBIGUOUS,
            matched_surface=_bounded_surface(surface),
            candidates=ordered[:_MAX_CANDIDATES],
            evidence=("multiple_distinct_identities",),
        )


def _surface_covers(alias_key: str, query_key: str) -> bool:
    """True when ``alias_key`` names ``query_key`` on whole-word boundaries.

    ``conversation service`` matches ``the conversation service`` and
    ``conversation_service``; ``conv`` never matches ``conversation``.
    """
    if alias_key == query_key:
        return True
    alias_parts = alias_key.split()
    query_parts = query_key.split()
    if not alias_parts or len(alias_parts) > len(query_parts):
        return False
    for start in range(len(query_parts) - len(alias_parts) + 1):
        if query_parts[start : start + len(alias_parts)] == alias_parts:
            return True
    return False


def _bounded_surface(surface: Any) -> str:
    if isinstance(surface, str):
        return surface[:_MAX_SURFACE_CHARS]
    return ""


def _identities_from_model(
    architecture_model: Any,
) -> tuple[ArchitectureIdentity, ...]:
    """Collect every identity the authoritative model already exposes.

    Only identities the model actually holds are produced — a package is
    included only when ``RepositoryMap`` records it as one, and a symbol is
    never fabricated (it is reached through the existing ``locate()`` primitive
    rather than pre-indexed).
    """
    identities: list[ArchitectureIdentity] = []

    for entry in getattr(architecture_model, "components", ()) or ():
        name = getattr(entry, "name", "")
        if isinstance(name, str) and name:
            identities.append(
                ArchitectureIdentity(
                    canonical_id=name, identity_type="component", source="component_registry"
                )
            )

    for entry in getattr(architecture_model, "capabilities", ()) or ():
        name = getattr(entry, "name", "")
        if isinstance(name, str) and name:
            identities.append(
                ArchitectureIdentity(
                    canonical_id=name, identity_type="capability", source="capability_model"
                )
            )

    repository_map = getattr(architecture_model, "repository_map", None)
    if repository_map is not None:
        for info in getattr(repository_map, "modules", ()) or ():
            module = getattr(info, "module", "")
            if not isinstance(module, str) or not module:
                continue
            identities.append(
                ArchitectureIdentity(
                    canonical_id=module,
                    identity_type="module",
                    source="repository_map",
                )
            )
            if getattr(info, "is_package", False):
                # A package IS a module in RepositoryMap; it is recorded as a
                # distinct kind only because locate() reports it that way.
                identities.append(
                    ArchitectureIdentity(
                        canonical_id=module,
                        identity_type="package",
                        source="repository_map",
                    )
                )

    return tuple(identities)


def _build_index(architecture_model: Any) -> tuple[tuple[_IndexEntry, ...], int]:
    """Derive the deterministic surface → identity index.

    Construction order is fixed (component, capability, module, package) and the
    result is sorted by key, so the index never depends on registry iteration
    order or on which instance built it.
    """
    identities = _identities_from_model(architecture_model)

    entries: dict[tuple[str, str], ArchitectureIdentity] = {}
    for identity in identities:
        key = _surface_key(identity.canonical_id)
        if not key:
            continue
        entries.setdefault((key, identity.identity_type), identity)
        if len(entries) >= _MAX_IDENTITIES:
            break

    ordered = tuple(
        _IndexEntry(key=key, identity=identity)
        for (key, _kind), identity in sorted(
            entries.items(), key=lambda item: (-len(item[0][0].split()), item[0])
        )
    )
    return ordered, len({(i.identity_type, i.canonical_id) for i in identities})


__all__ = [
    "SUPPORTED_IDENTITY_TYPES",
    "ArchitectureIdentity",
    "ArchitectureResolution",
    "ArchitectureTargetResolver",
]