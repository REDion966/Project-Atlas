"""G3 — deterministic scaffold derivation for a conversational development request.

The bounded ``DevelopmentDriver`` authors exactly one change class: the deterministic
capability-handler scaffold produced by ``ScaffoldChangeSupplier``. A conversational
request carries no authoring payload, so this module reduces the request's own words to the
scaffold SPECIFICATION the EXISTING supplier validates — deterministically, with no model
and no free-form synthesis.

When the request names no capability this returns ``None``, so the driver reports its own
honest ``AUTHOR_UNAVAILABLE`` terminal instead of inventing content. The derived paths are
validated by the EXISTING supplier (``CodeChangeSet.validate_path`` + the
architecture-sensitive-prefix rule), so an unconfirmed derivation can never reach authoring.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier

#: The scaffold target package: the package that OWNS the existing capability handlers
#: (``atlas.reasoning.execution``), so an authored scaffold lands in the sanctioned,
#: non-architecture-sensitive home of the change class it belongs to.
SCAFFOLD_PACKAGE: str = "atlas/reasoning/execution"

#: Bound on the derived capability slug (and therefore on the authored paths).
MAX_CAPABILITY_SLUG_CHARS: int = 40

#: Maximum number of request words folded into the slug.
MAX_SLUG_WORDS: int = 3

#: Bounded reduction: an authoring verb plus the capability noun. The optional tail (after
#: the capability noun) names the capability; the middle fallback covers
#: "<verb> capability <noun>" orderings.
_CAPABILITY_REQUEST_RE = re.compile(
    r"\b(?:add|adding|build|building|create|creating|implement|implementing|develop|"
    r"developing|introduce|introducing|support|supporting|provide|providing|need|"
    r"needs|want|wants|enable|enabling)\b"
    r"(?P<middle>[^.!?]{0,60}?)\b(?:capabilit(?:y|ies)|feature|handler|tool)\b"
    r"(?P<tail>[^.!?]{0,80})",
    re.IGNORECASE,
)

#: Words that describe the request shape rather than the capability being asked for.
_SLUG_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "so", "then", "that", "this", "these", "those",
        "which", "who", "for", "to", "of", "in", "on", "into", "with", "using", "use",
        "by", "from", "at", "as", "it", "its", "my", "me", "you", "your", "atlas",
        "please", "can", "could", "would", "should", "will", "new", "also", "some",
        "called", "named", "able", "capability", "capabilities", "feature", "features",
        "handler", "handlers", "tool", "tools", "run", "runs", "make", "makes",
    }
)

_SLUG_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_SLUG_OK_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _content_words(text: Any) -> tuple[str, ...]:
    """Deterministic content words of ``text`` (lowercased, stopwords dropped)."""
    if not isinstance(text, str):
        return ()
    words: list[str] = []
    for token in _SLUG_SPLIT_RE.split(text.lower()):
        if not token or token in _SLUG_STOPWORDS:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        if not token.isalnum():
            continue
        words.append(token)
    return tuple(words)


def capability_slug(request: Any) -> str | None:
    """The bounded capability slug named by ``request``, or ``None``.

    Deterministic and read-only. ``None`` means the request names no capability, so nothing
    may be authored for it.
    """
    if not isinstance(request, str) or not request.strip():
        return None
    match = _CAPABILITY_REQUEST_RE.search(request)
    if match is None:
        return None
    words = _content_words(match.group("tail"))
    if not words:
        words = _content_words(match.group("middle"))
    if not words:
        return None
    slug = "_".join(words[:MAX_SLUG_WORDS])
    if len(slug) > MAX_CAPABILITY_SLUG_CHARS or not _SLUG_OK_RE.match(slug):
        return None
    return slug


def scaffold_spec_for_request(
    request: Any,
    *,
    registered_names: Iterable[str] = (),
) -> dict[str, Any] | None:
    """The scaffold specification for ``request``, or ``None`` (fail-closed).

    The specification is returned ONLY when the EXISTING ``ScaffoldChangeSupplier`` accepts
    it for the derived slug, so an unconfirmed derivation cannot reach authoring. A request
    that names no capability, or one that already names a registered capability, returns
    ``None`` and the driver reports its own honest terminal.

    Read-only and deterministic: no model, no network, no state change.
    """
    slug = capability_slug(request)
    if slug is None:
        return None
    normalized = slug.replace("_", "")
    for name in tuple(registered_names or ()):
        if str(name).replace("_", "").replace(".", "").lower() == normalized:
            return None
    spec = {
        "module": f"{SCAFFOLD_PACKAGE}/{slug}.py",
        "capability_name": slug,
        "test_module": f"tests/test_{slug}.py",
    }
    try:
        supplied = ScaffoldChangeSupplier().supply_changes(
            DevelopmentNeed(
                title=str(request)[:200],
                metadata={"scaffold": dict(spec)},
            )
        )
    except Exception:
        return None
    if supplied is None:
        return None
    return spec
