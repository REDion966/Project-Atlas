"""Atlas Language — normalization facade (L2).

ONE coherent normalization path. This module owns no second implementation: it
delegates to the EXISTING shared primitives already used across the conversation
layer, so the language foundation and the L0–L10 pipeline can never drift apart.

  * surface whitespace + bounded surface canonicalization ->
    :mod:`atlas.conversation.normalization`;
  * tokenization + bounded morphology (lemmatization) ->
    :mod:`atlas.conversation.lexicon`.

Deterministic, model-free, bounded. Normalizing text never changes meaning and
grants no authority.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation.lexicon import (
    normalize_token,
    token_set,
    tokens,
)
from atlas.conversation.normalization import (
    canonicalize_surface,
    collapse_whitespace,
)

#: The normalization stages, in the order :func:`normalize` applies them.
NORMALIZATION_STAGES: tuple[str, ...] = (
    "collapse_whitespace",
    "canonicalize_surface",
)


def normalize(text: Any) -> str:
    """The Atlas surface normalization for ``text`` (L2).

    Whitespace is collapsed, then the EXISTING bounded surface canonicalization
    maps a small, anchored set of ordinary equivalent whole requests onto
    vocabulary the deterministic pipeline already recognizes. Unrecognized text
    is preserved verbatim apart from whitespace — nothing is invented.
    """
    return canonicalize_surface(collapse_whitespace(text))


def tokenize(text: Any) -> tuple[str, ...]:
    """Deterministic, bounded word tokens of ``text``."""
    return tokens(text)


def lemmatize(text_or_tokens: Any) -> tuple[str, ...]:
    """Bounded lemmas for ``text`` (or for a sequence of tokens).

    A ``str`` is tokenized first; any other iterable is treated as tokens.
    Uses the SAME morphological normalizer as the existing lexicon.
    """
    if isinstance(text_or_tokens, str):
        items = tokens(text_or_tokens)
    elif isinstance(text_or_tokens, (list, tuple, set, frozenset)):
        items = tuple(str(item) for item in text_or_tokens)
    else:
        return ()
    return tuple(normalize_token(item) for item in items)


def lemma_set(text: Any) -> frozenset[str]:
    """The lemma set of ``text`` (deterministic; empty for non-text)."""
    return frozenset(lemmatize(text))


__all__ = [
    "NORMALIZATION_STAGES",
    "collapse_whitespace",
    "lemma_set",
    "lemmatize",
    "normalize",
    "normalize_token",
    "token_set",
    "tokenize",
    "tokens",
]
