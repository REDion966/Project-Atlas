"""Atlas Research — Deterministic Source Selection (Phase 3.2).

A bounded, deterministic policy that selects AUTHORIZED local source
specifications for a research question, so the existing research pipeline has
material to acquire. It only SELECTS among sources the existing architecture
already recognizes and is authorized to use — local repository files served by
the existing CODEBASE adapter. It never grants authorization, never fabricates a
source, and never selects web (the web adapter stays deny-by-default behind its
existing host policy).

The selection is derived solely from the deterministic
:class:`~atlas.research.repository_map.RepositoryMap` (module names/paths) and
the question's significant tokens. Same question + same repository state ⇒ same
selection.

Pure logic: stdlib only. No AI, no network, no storage, no kernel access,
no execution, no authorization surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas.research._text import significant_tokens

#: Hard cap on the number of sources selected for one research invocation.
MAX_SELECTED_SOURCES: int = 4

#: Minimum length of a question token considered for module matching.
MIN_TOKEN_LENGTH: int = 3

#: URI scheme for the existing CODEBASE source adapter.
CODE_URI_SCHEME: str = "code"

#: Bounded, curated command/cue words that describe the *request* rather than its
#: subject. Ignoring them keeps selection pointed at the subject (e.g. "Research
#: the memory architecture." must not select the research subsystem itself).
DEFAULT_IGNORED_TOKENS: frozenset[str] = frozenset(
    {
        "research",
        "investigate",
        "acquire",
        "find",
        "search",
        "lookup",
        "look",
        "latest",
        "news",
        "about",
        "please",
        "tell",
        "show",
    }
)


@dataclass(frozen=True, slots=True)
class SourceSelectionPolicy:
    """Bounded, deterministic selection policy (immutable)."""

    max_sources: int = MAX_SELECTED_SOURCES
    min_token_length: int = MIN_TOKEN_LENGTH
    ignored_tokens: frozenset[str] = DEFAULT_IGNORED_TOKENS

    def __post_init__(self) -> None:
        if self.max_sources < 1:
            raise ValueError(f"max_sources must be >= 1, got {self.max_sources}")
        if self.min_token_length < 1:
            raise ValueError(
                f"min_token_length must be >= 1, got {self.min_token_length}"
            )


DEFAULT_POLICY = SourceSelectionPolicy()


def _module_tokens(module_name: str) -> frozenset[str]:
    """Lower-cased dotted+fragment tokens of a module name (deterministic)."""
    tokens: set[str] = set()
    for part in module_name.split("."):
        for piece in part.split("_"):
            piece = piece.lower()
            if piece:
                tokens.add(piece)
    return frozenset(tokens)


def select_repository_sources(
    question: str,
    repository_map: Any,
    policy: SourceSelectionPolicy = DEFAULT_POLICY,
) -> tuple[str, ...]:
    """Return bounded, ordered CODEBASE source specs for ``question``.

    Candidate sources are the repository modules in ``repository_map`` whose
    dotted-name tokens overlap the question's significant tokens. Ranking is
    deterministic: most token matches first, then ascending repository path.
    ``is_package`` modules are skipped (only real files are loadable sources).

    Fail-closed: a missing map, an empty/blank question, no token overlap, or
    any error returns an empty tuple — never a fabricated or unauthorized
    source, and never a web source.
    """
    if not isinstance(question, str) or not question.strip():
        return ()
    if repository_map is None:
        return ()
    try:
        modules = tuple(getattr(repository_map, "modules", ()) or ())
    except Exception:
        return ()
    if not modules:
        return ()

    question_tokens = {
        token
        for token in significant_tokens(question)
        if len(token) >= policy.min_token_length
        and token not in policy.ignored_tokens
    }
    if not question_tokens:
        return ()

    scored: list[tuple[int, str]] = []
    for info in modules:
        if bool(getattr(info, "is_package", False)):
            continue
        module = str(getattr(info, "module", "") or "")
        path = str(getattr(info, "path", "") or "")
        if not module or not path:
            continue
        matches = len(question_tokens & _module_tokens(module))
        if matches > 0:
            # Ascending (most matches first, then path) is the deterministic order.
            scored.append((-matches, path))

    if not scored:
        return ()
    scored.sort()

    selected: list[str] = []
    seen: set[str] = set()
    for _, path in scored:
        if path in seen:
            continue
        seen.add(path)
        selected.append(f"{CODE_URI_SCHEME}://{path}")
        if len(selected) >= policy.max_sources:
            break
    return tuple(selected)
