"""
Atlas Evolution Autonomy — Scope Classifier — Phase 16.1

The closed, immutable mapping between governance ScopeType and the
target_components that an EvolutionRequest translation may carry.

Per Phase 16 Decision D2: target_components are derived EXCLUSIVELY
from ``EvolutionRequest.target_scope`` via this closed map. They are
never influenced by the change payload or any other user-controlled
input, so governance classification cannot be smuggled. A request
whose scope maps to an UNKNOWN classification is structurally unable
to execute at any governance level (enforced downstream by the
gateway's UNKNOWN-close invariant, implemented in a later sub-phase).

Pure logic. No infrastructure. No AI. No payload-based inference.
"""

from types import MappingProxyType
from typing import Mapping

from atlas.evolution.governance.models import ScopeType

# ---------------------------------------------------------------------------
# Closed scope → components map (immutable)
# ---------------------------------------------------------------------------

#: Components a CONFIG-scoped request may declare.
_CONFIG_COMPONENTS: tuple[str, ...] = ("config", "autonomy:config")

#: Components a MEMORY-scoped request may declare.
_MEMORY_COMPONENTS: tuple[str, ...] = ("memory", "autonomy:memory")

#: Components a KNOWLEDGE-scoped request may declare.
_KNOWLEDGE_COMPONENTS: tuple[str, ...] = ("knowledge", "autonomy:knowledge")

#: Components a CAPABILITY-scoped request may declare.
_CAPABILITY_COMPONENTS: tuple[str, ...] = ("capability", "autonomy:capability")

#: Components used when a request carries no recognised state scope.
#: These never match an existing RuleEngine keyword, so governance
#: classifies such translations as UNKNOWN — the fail-closed case.
_UNKNOWN_COMPONENTS: tuple[str, ...] = ("governance:unknown",)

#: The closed, immutable map. MappingProxyType prevents mutation at runtime.
#: Keys and values are frozen; this module is the single source of truth
#: for scope-to-component translation in Phase 16.
SCOPE_COMPONENTS: Mapping[ScopeType, tuple[str, ...]] = MappingProxyType({
    ScopeType.CONFIG: _CONFIG_COMPONENTS,
    ScopeType.MEMORY: _MEMORY_COMPONENTS,
    ScopeType.KNOWLEDGE: _KNOWLEDGE_COMPONENTS,
    ScopeType.CAPABILITY: _CAPABILITY_COMPONENTS,
    ScopeType.UNKNOWN: _UNKNOWN_COMPONENTS,
})

#: Closed set of state scopes a request may target for application.
STATE_SCOPES: frozenset[ScopeType] = frozenset({
    ScopeType.CONFIG,
    ScopeType.MEMORY,
    ScopeType.KNOWLEDGE,
    ScopeType.CAPABILITY,
})


def components_for_scope(scope: ScopeType) -> list[str]:
    """
    Return the immutable component tuple for a scope, as a list.

    Deterministic: the same scope always yields the same components.
    Unrecognised scopes (e.g. IDENTITY, CODE) are not in the closed map
    and produce the UNKNOWN component set — they can never be translated
    into a state-change proposal.

    Args:
        scope: The target ScopeType.

    Returns:
        The component names for the scope as a new list (copy semantics).
    """
    return list(SCOPE_COMPONENTS.get(scope, _UNKNOWN_COMPONENTS))


def classify_components(components: list[str]) -> ScopeType:
    """
    Classify component names into a ScopeType using the closed map only.

    Exact-set matching in a fixed priority order (CONFIG, MEMORY,
    KNOWLEDGE, CAPABILITY). Any component set that does not exactly
    correspond to one closed entry classifies as UNKNOWN.

    This function is deliberately conservative: it performs NO free-form
    keyword matching. Payload-derived or user-supplied component lists
    therefore cannot influence classification (No payload-based scope
    inference).

    Args:
        components: The component names to classify.

    Returns:
        The matching ScopeType, or ScopeType.UNKNOWN.
    """
    normalized = {c.lower() for c in components}

    if set(_CONFIG_COMPONENTS) == normalized:
        return ScopeType.CONFIG
    if set(_MEMORY_COMPONENTS) == normalized:
        return ScopeType.MEMORY
    if set(_KNOWLEDGE_COMPONENTS) == normalized:
        return ScopeType.KNOWLEDGE
    if set(_CAPABILITY_COMPONENTS) == normalized:
        return ScopeType.CAPABILITY
    return ScopeType.UNKNOWN


def classify_request(request: object) -> ScopeType:
    """
    Classify an EvolutionRequest by its declared target_scope.

    The target_scope is the single authority for classification. The
    closed map guarantees a scope-carrying request can never be
    translated into an UNKNOWN governance classification; this helper
    exists so downstream gates (UNKNOWN-close, implemented in later
    sub-phases) can prove that invariant deterministically.

    Args:
        request: An EvolutionRequest-like object exposing target_scope.

    Returns:
        The request's ScopeType, or UNKNOWN if the attribute is absent.
    """
    scope = getattr(request, "target_scope", None)
    if scope is None or scope not in STATE_SCOPES:
        return ScopeType.UNKNOWN
    return scope


def is_state_scope(scope: ScopeType) -> bool:
    """Return True if the scope is a closed state scope for Phase 16.

    IDENTITY and CODE are intentionally excluded — they are
    constitutionally protected and cannot be targeted in Phase 16.
    """
    return scope in STATE_SCOPES
