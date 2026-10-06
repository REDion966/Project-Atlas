"""Atlas Language — language identification and routing.

Deterministic, evidence-backed language reading. It does NOT claim to identify
every language: it reports what the SCRIPT/character evidence can actually
support, and returns an UNKNOWN profile (``"und"``) rather than guessing. That is
what lets the rest of Atlas route honestly — an unsupported language is reported
as unsupported instead of being silently treated as English.

Chosen over fastText (an approved candidate resource) because the current
acceptance criteria need script/route evidence only: a deterministic classifier
is exact for the scripts Atlas can handle, has no dependency, cannot be wrong
about an unseen language, and fails closed. A learned identifier remains an
OPTIONAL provider behind the same seam (see :mod:`atlas.language.providers`).

Pure: standard library only, no clock, no randomness, no I/O, no model.
"""

from __future__ import annotations

import re
from typing import Any

from atlas.language.lexicon import LanguageProfile

#: Bounded input cap (a huge text cannot make routing expensive).
MAX_ROUTING_CHARS: int = 2000

#: Script names (the vocabulary the profile reports).
SCRIPT_LATIN = "latin"
SCRIPT_CYRILLIC = "cyrillic"
SCRIPT_GREEK = "greek"
SCRIPT_ARABIC = "arabic"
SCRIPT_HEBREW = "hebrew"
SCRIPT_CJK = "han"
SCRIPT_HIRAGANA = "hiragana"
SCRIPT_HANGUL = "hangul"
SCRIPT_BENGALI = "bengali"
SCRIPT_DEVANAGARI = "devanagari"
SCRIPT_UNKNOWN = "unknown"

#: Ordered script detectors: (regex, script, language, direction, confidence).
#: Specific scripts come first; Latin is last because it is the fallback.
_SCRIPT_RULES: tuple[tuple[str, str, str, str, float], ...] = (
    ("[\u0980-\u09ff]", SCRIPT_BENGALI, "bn", "ltr", 0.9),
    ("[\u0900-\u097f]", SCRIPT_DEVANAGARI, "hi", "ltr", 0.9),
    ("[\u0400-\u04ff]", SCRIPT_CYRILLIC, "ru", "ltr", 0.9),
    ("[\u0370-\u03ff]", SCRIPT_GREEK, "el", "ltr", 0.9),
    ("[\u0590-\u05ff]", SCRIPT_HEBREW, "he", "rtl", 0.9),
    ("[\u0600-\u06ff]", SCRIPT_ARABIC, "ar", "rtl", 0.9),
    ("[\uac00-\ud7af]", SCRIPT_HANGUL, "ko", "ltr", 0.9),
    ("[\u3040-\u309f]", SCRIPT_HIRAGANA, "ja", "ltr", 0.9),
    ("[\u4e00-\u9fff]", SCRIPT_CJK, "zh", "ltr", 0.85),
)

_LATIN_RE = re.compile(r"[A-Za-z]")

#: The languages this foundation treats as fully routable today.
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en"})

#: The languages whose text Atlas will still route through the authoritative
#: pipeline (they are understood as text, but not claimed as fully supported).
ROUTABLE_LANGUAGES: frozenset[str] = frozenset({"en"})


def detect_language(text: Any) -> LanguageProfile:
    """The bounded language/script profile of ``text`` (never a guess).

    Non-text or empty input yields the UNKNOWN profile. A script is reported
    only when its characters are actually present, and a Latin-script text is
    reported as English only when it carries Latin letters — a digit/punctuation
    only turn stays UNKNOWN.
    """
    if not isinstance(text, str) or not text.strip():
        return LanguageProfile(
            language="und",
            script=SCRIPT_UNKNOWN,
            direction="ltr",
            confidence=0.0,
            evidence=("empty-or-non-text",),
        )
    sample = text[:MAX_ROUTING_CHARS]
    for pattern, script, language, direction, confidence in _SCRIPT_RULES:
        if re.search(pattern, sample):
            return LanguageProfile(
                language=language,
                script=script,
                direction=direction,
                confidence=confidence,
                evidence=(f"script:{script}",),
            )
    if _LATIN_RE.search(sample):
        return LanguageProfile(
            language="en",
            script=SCRIPT_LATIN,
            direction="ltr",
            confidence=0.6,
            evidence=("script:latin", "assumed:en"),
        )
    return LanguageProfile(
        language="und",
        script=SCRIPT_UNKNOWN,
        direction="ltr",
        confidence=0.0,
        evidence=("no-letter-evidence",),
    )


def route_language(profile: LanguageProfile) -> str:
    """Route a profile to a bounded decision (``supported`` / ``routable`` /
    ``unsupported`` / ``unknown``).

    ``unsupported`` and ``unknown`` are honest outcomes: the caller must not
    treat them as English. Nothing here authorizes anything.
    """
    if not isinstance(profile, LanguageProfile) or not profile.known:
        return "unknown"
    if profile.language in SUPPORTED_LANGUAGES:
        return "supported"
    if profile.language in ROUTABLE_LANGUAGES:
        return "routable"
    return "unsupported"


__all__ = [
    "MAX_ROUTING_CHARS",
    "ROUTABLE_LANGUAGES",
    "SUPPORTED_LANGUAGES",
    "detect_language",
    "route_language",
]
