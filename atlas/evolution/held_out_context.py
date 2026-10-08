"""Atlas Evolution — the HELD-OUT authoring boundary (Command 2, W4/A3).

An authoring agent that can read the exact tests it is about to be judged by is
not being verified: it can overfit the assertions, the fixtures and the
traceback instead of solving the problem. It is also the classic way a
verification artifact leaks back into the change it is meant to measure.

This module draws that line explicitly. A verification artifact is either
HELD OUT — the author/repair side must never see its source, its assertions, its
fixtures, its path, or any excerpt derived from it — or it is explicitly
classified as SAFE METADATA, in which case only a bounded identity may cross.
Removing the test file from a context mapping is NOT enough on its own: the same
content can be carried inside a failure message, a rationale, a traceback or a
plan field, so free text is redacted line-by-line against the held-out sources
as well.

Nothing here decides what an author may do, approves anything, or executes
anything. It is a pure, bounded, deterministic filter over already-produced
authoring context. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Metadata key carrying the explicitly held-out verification test PATHS.
HELD_OUT_TESTS_KEY: str = "held_out_tests"
#: Metadata key carrying the ONLY metadata explicitly classified safe for authors.
SAFE_METADATA_KEY: str = "author_safe_metadata"

#: The bounded, closed vocabulary of abstract failure categories. When nothing
#: safe can be said, the author receives ``unknown`` — never a test excerpt.
FAILURE_CATEGORIES: frozenset[str] = frozenset(
    {
        "assertion_failure",
        "execution_error",
        "timeout",
        "change_refused",
        "unknown",
    }
)

#: A line shorter than this is too generic to be a meaningful leak signal.
MIN_SENSITIVE_LINE_CHARS: int = 12
#: Bound on the number of held-out sources/lines considered (deterministic).
MAX_HELD_OUT_SOURCES: int = 32
MAX_SENSITIVE_LINES: int = 4096
REDACTION: str = "[held-out verification content removed]"

_OUTCOME_CATEGORIES: tuple[tuple[str, str], ...] = (
    # ORDER MATTERS: ``guard_failed`` also contains "fail", so it must be tested
    # first, and a plain "failed" test outcome is an assertion failure.
    ("guard_failed", "change_refused"),
    ("timeout", "timeout"),
    ("assert", "assertion_failure"),
    ("fail", "assertion_failure"),
    ("error", "execution_error"),
)


@dataclass(frozen=True, slots=True)
class HeldOutBoundary:
    """The explicitly held-out verification artifacts for one authoring request."""

    paths: frozenset[str] = frozenset()
    sources: tuple[str, ...] = ()
    sensitive_lines: frozenset[str] = frozenset()

    @property
    def active(self) -> bool:
        return bool(self.paths or self.sensitive_lines)

    def excludes(self, path: Any) -> bool:
        """True when ``path`` is a held-out verification artifact."""
        text = str(path or "").strip().replace("\\", "/")
        if not text:
            return False
        if text in self.paths:
            return True
        # A dotted module name is as identifying as the repository path.
        dotted = text[:-3].replace("/", ".") if text.endswith(".py") else text
        return any(
            dotted == (item[:-3].replace("/", ".") if item.endswith(".py") else item)
            for item in self.paths
        )

    def redact(self, text: Any) -> str:
        """Remove any held-out SOURCE content carried inside ``text``."""
        if not isinstance(text, str) or not text:
            return text if isinstance(text, str) else ""
        if not self.sensitive_lines:
            return text
        if any(source and source in text for source in self.sources):
            text = text.replace(REDACTION, "")
            for source in self.sources:
                if source:
                    text = text.replace(source, REDACTION)
        out: list[str] = []
        for line in text.splitlines():
            if line.strip() and line.strip() in self.sensitive_lines:
                out.append(REDACTION)
            else:
                out.append(line)
        return "\n".join(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "held_out_paths": sorted(self.paths),
            "held_out_source_count": len(self.sources),
            "active": self.active,
        }


def held_out_paths(
    expectation: Any = None, metadata: Any = None
) -> frozenset[str]:
    """The explicitly held-out verification test paths (never inferred).

    A path is held out only when a ``VerificationExpectation`` marked it so
    (``held_out=True``) or when the caller declared it under
    :data:`HELD_OUT_TESTS_KEY`. Nothing is assumed.
    """
    out: set[str] = set()
    if metadata is not None and isinstance(metadata, dict):
        declared = metadata.get(HELD_OUT_TESTS_KEY)
        if isinstance(declared, (list, tuple, set, frozenset)):
            for item in declared:
                text = str(item or "").strip().replace("\\", "/")
                if text:
                    out.add(text)
    if expectation is not None and bool(getattr(expectation, "held_out", False)):
        for item in getattr(expectation, "tests", ()) or ():
            text = str(item or "").strip().replace("\\", "/")
            if text:
                out.add(text)
    return frozenset(out)


def boundary_of(
    expectation: Any = None,
    *,
    metadata: Any = None,
    sources: Any = None,
) -> HeldOutBoundary:
    """Build the boundary from an expectation and/or the held-out SOURCES.

    ``sources`` is a ``path -> content`` mapping (or an iterable of contents) of
    the held-out artifacts; it exists ONLY so free text can be redacted against
    it. It is never forwarded to an author.
    """
    paths = held_out_paths(expectation, metadata)
    contents: list[str] = []
    if isinstance(sources, dict):
        for path, content in sources.items():
            if paths and str(path) not in paths:
                continue
            if isinstance(content, str) and content:
                contents.append(content)
    elif isinstance(sources, (list, tuple)):
        for content in sources:
            if isinstance(content, str) and content:
                contents.append(content)
    contents = contents[:MAX_HELD_OUT_SOURCES]

    sensitive: set[str] = set()
    for content in contents:
        for line in content.splitlines():
            stripped = line.strip()
            if len(stripped) >= MIN_SENSITIVE_LINE_CHARS:
                sensitive.add(stripped)
            if len(sensitive) >= MAX_SENSITIVE_LINES:
                break
        if len(sensitive) >= MAX_SENSITIVE_LINES:
            break

    return HeldOutBoundary(
        paths=paths,
        sources=tuple(contents),
        sensitive_lines=frozenset(sensitive),
    )


def abstract_failure_category(outcome: Any = None) -> str:
    """A bounded abstract failure CATEGORY — never a test excerpt.

    This is the only description of the failure an author may receive: the
    specific assertion, traceback and test source stay behind the boundary.
    """
    token = ""
    if outcome is not None:
        token = str(getattr(outcome, "test_outcome", "") or "").strip().lower()
        if not token:
            token = str(getattr(outcome, "status", "") or "").strip().lower()
    if token:
        for needle, category in _OUTCOME_CATEGORIES:
            if needle in token:
                return category
    return "unknown"


def safe_context(context: Any, boundary: HeldOutBoundary) -> dict[str, str]:
    """The authoring context with every held-out artifact removed (or ``{}``).

    Held-out PATHS are dropped, and any held-out SOURCE content carried inside a
    surviving value is redacted — so the same test cannot leak through a
    rationale, a traceback or a neighbouring file.
    """
    if not isinstance(context, dict):
        return {}
    if not boundary.active:
        return {str(k): str(v) for k, v in context.items() if isinstance(v, str)}
    out: dict[str, str] = {}
    for path, content in context.items():
        if not isinstance(path, str) or not isinstance(content, str):
            continue
        if boundary.excludes(path):
            continue
        out[path] = boundary.redact(content)
    return out


def safe_verification_tests(
    tests: Any, boundary: HeldOutBoundary
) -> tuple[str, ...]:
    """The verification identities an author may see: the NON-held-out ones only.

    A held-out test's path is itself information, so it crosses the boundary
    only when the caller explicitly classified it safe. Callers that want to give
    the author NO verification identity simply pass the result of this function.
    """
    if not boundary.active:
        return tuple(str(item) for item in (tests or ()) if str(item).strip())
    return tuple(
        str(item)
        for item in (tests or ())
        if str(item).strip() and not boundary.excludes(item)
    )


def safe_metadata(metadata: Any, boundary: HeldOutBoundary) -> dict[str, Any]:
    """The explicitly-classified SAFE metadata, redacted (never the raw mapping)."""
    if not isinstance(metadata, dict):
        return {}
    declared = metadata.get(SAFE_METADATA_KEY)
    if not isinstance(declared, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in declared.items():
        if isinstance(value, str):
            out[str(key)] = boundary.redact(value)
        else:
            out[str(key)] = value
    return out


__all__ = [
    "FAILURE_CATEGORIES",
    "HELD_OUT_TESTS_KEY",
    "REDACTION",
    "SAFE_METADATA_KEY",
    "HeldOutBoundary",
    "abstract_failure_category",
    "boundary_of",
    "held_out_paths",
    "safe_context",
    "safe_metadata",
    "safe_verification_tests",
]
