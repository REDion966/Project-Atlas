"""Atlas Conversation — Bounded Conversational Entity Capture (NLU-4).

Captures the explicitly *named* entities a user mentions in a turn so a later
turn can resolve a bounded reference ("its", "this phone") to them.

This is deliberately NOT general entity extraction, NOT a knowledge graph, NOT
a world model, and NOT durable memory. It recognizes a narrow, high-precision
surface form — a run of capitalised / alphanumeric "proper noun" tokens
("Samsung Galaxy S26 Ultra", "iPhone 17 Pro", "Dell XPS") — and stores, for the
current conversation only, the *name the user used* plus bounded provenance.

Design contract:
  * Pure: standard library only. No AI, no network, no storage, no kernel, no
    execution, no authorization surface.
  * Deterministic: identical input yields identical output.
  * High precision over recall: arbitrary capitalised words are NOT entities.
    A single-token name must carry a distinguishing mark (two or more capitals
    or a digit); a multi-token name must not begin with a common request/
    function word. Unrecognized prose captures nothing.
  * Bounded: at most ``MAX_ENTITIES_PER_TURN`` names per turn, each bounded to
    ``MAX_NAME_WORDS`` words / ``MAX_NAME_CHARS`` characters.
  * Not authority: a captured entity records only that the user referred to a
    name; it never asserts a verified fact and never authorizes anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Bounds applied to capture.
MAX_ENTITIES_PER_TURN: int = 3
MAX_NAME_WORDS: int = 5
MAX_NAME_CHARS: int = 60

#: Word tokenizer (letters/digits plus internal apostrophe/hyphen).
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")

#: A capitalised token that may participate in an entity run.
_CAPITALISED_RE = re.compile(r"^[A-Z][A-Za-z0-9'’\-]*$")

#: Bounded request/function words trimmed from the FRONT of a candidate run so
#: an imperative or question opener is never captured as part of a name
#: ("Research Samsung Galaxy" -> "Samsung Galaxy").
_LEADING_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "my", "our", "your", "his", "her", "their", "its",
        "it", "this", "that", "these", "those", "i", "we", "you", "he", "she",
        "they", "and", "or", "but", "also", "about", "for", "with", "in", "on",
        "at", "to", "of", "from", "as", "is", "are", "was", "were", "do",
        "does", "did", "can", "could", "would", "should", "will", "please",
        "research", "find", "search", "investigate", "look", "lookup",
        "acquire", "tell", "show", "compare", "help", "give", "provide",
        "explain", "describe", "review", "reviewing", "check", "need", "want",
        "use", "using", "still", "latest", "what", "which", "who", "how",
        "why", "when", "where",
    }
)


@dataclass(frozen=True, slots=True)
class CapturedEntity:
    """A bounded, conversation-scoped entity the user explicitly named.

    ``name`` is the surface form the user used, ``normalized`` is its
    lower-cased comparison key, and ``turn_id`` is the originating turn.
    It carries no verified facts and no authority.
    """

    name: str
    normalized: str = ""
    turn_id: str = ""

    def to_dict(self) -> dict[str, str]:
        """Serialize to a JSON-safe dict."""
        return {
            "name": self.name,
            "normalized": self.normalized,
            "turn_id": self.turn_id,
        }

    @classmethod
    def from_dict(cls, data) -> "CapturedEntity | None":
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        normalized = data.get("normalized")
        turn_id = data.get("turn_id")
        return cls(
            name=name.strip()[:MAX_NAME_CHARS],
            normalized=(
                normalized.strip().lower()
                if isinstance(normalized, str) and normalized.strip()
                else name.strip().lower()[:MAX_NAME_CHARS]
            ),
            turn_id=turn_id.strip() if isinstance(turn_id, str) else "",
        )


def _is_entity_token(word: str) -> bool:
    """True when ``word`` may participate in an entity run (proper-noun-ish).

    Accepts a Capitalised word, an all-digit token, or a token with an internal
    capital ("iPhone", "eBay", "iOS") — the bounded surface of brand-style
    names. An ordinary lower-case word never participates, so a run cannot
    absorb surrounding prose.
    """
    if word.isdigit():
        return True
    if _CAPITALISED_RE.match(word):
        return True
    return any(c.isupper() for c in word[1:])


def _single_token_qualifies(word: str) -> bool:
    """A lone token qualifies only with a distinguishing mark.

    A digit ("S26") or a mixed-case brand form ("iPhone", "eBay", "iOS") is a
    strong signal. An ordinary capitalised word ("Python", "Atlas") and an
    ALL-CAPS shout ("SAMSUNG") are not captured, so arbitrary capitalisation —
    including a shouted repeat of an already-captured brand — cannot
    manufacture a second entity.
    """
    if word.isdigit():
        return True
    has_upper = any(c.isupper() for c in word)
    has_lower = any(c.islower() for c in word)
    if not (has_upper and has_lower):
        return False
    return any(c.isupper() for c in word[1:])


def capture_named_entities(text: str) -> tuple[str, ...]:
    """Return the bounded explicitly-named entities mentioned in ``text``."""
    if not isinstance(text, str) or not text.strip():
        return ()

    tokens = [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(text)]
    runs: list[list[tuple[str, int, int]]] = []
    current: list[tuple[str, int, int]] = []
    for word, start, end in tokens:
        if _is_entity_token(word):
            if current and text[current[-1][2]:start] == " ":
                current.append((word, start, end))
                continue
            if current:
                runs.append(current)
            current = [(word, start, end)]
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    names: list[str] = []
    seen: set[str] = set()
    for run in runs:
        words = [w for w, _s, _e in run]
        while words and words[0].lower() in _LEADING_STOPWORDS:
            words = words[1:]
        if not words:
            continue
        if len(words) > MAX_NAME_WORDS:
            continue
        if len(words) == 1 and (
            not _single_token_qualifies(words[0]) or len(words[0]) > 24
        ):
            # A lone token needs a distinguishing mark and a sane length, so a
            # long opaque string cannot be captured as an entity name.
            continue
        name = " ".join(words)[:MAX_NAME_CHARS].strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) >= MAX_ENTITIES_PER_TURN:
            break
    return tuple(names)
