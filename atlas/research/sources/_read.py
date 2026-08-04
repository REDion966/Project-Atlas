"""Shared, deterministic file reading helper for the source adapters.

Kept internal to the adapter package. Centralizes decoding and the
safe-error contract so every adapter behaves identically on unreadable
or binary inputs.
"""

from pathlib import Path

from atlas.research.models import SourceKind, SourceProfile
from atlas.research.source_catalog import LANGUAGE_BY_EXTENSION, TEXT_EXTENSIONS


def build_profile(
    *,
    uri: str,
    kind: SourceKind,
    text: str,
    byte_size: int,
    tokens_estimate: int,
    title: str,
    content_type: str,
    language: str,
    line_count: int,
    load_error: str,
) -> SourceProfile:
    """Construct a SourceProfile from fully normalized inputs.

    All inputs are supplied by the concrete adapters; keyword-only
    arguments keep call sites explicit and order-independent.
    """
    metadata: dict[str, object] = {"mtime_epoch": 0.0}
    if load_error:
        metadata["load_error"] = load_error
    return SourceProfile(
        uri=uri,
        kind=kind,
        text=text,
        title=title,
        language=language,
        content_type=content_type,
        byte_size=byte_size,
        tokens_estimate=tokens_estimate,
        line_count=line_count,
        metadata=metadata,
    )


def language_for(resource: Path) -> str:
    """Human-readable language family for a file, or empty if unknown."""
    return LANGUAGE_BY_EXTENSION.get(resource.suffix.lower(), "")


def is_text_resource(resource: Path) -> bool:
    """True when the file extension is known to be text-like."""
    return resource.suffix.lower() in TEXT_EXTENSIONS


def safe_read_text(resource: Path) -> tuple[str, str]:
    """Read a text file, returning ``(text, error)``.

    Returns ``("", ...)`` with an error description when the file is
    missing, unreadable, or not text regardless of the system's
    locale-dependent default encodings.
    """
    try:
        data = resource.read_bytes()
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return "", f"cannot read {resource}: {exc}"
    try:
        return data.decode("utf-8"), ""
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("utf-16"), ""
    except UnicodeDecodeError:
        return "", "binary or unsupported encoding"


def estimate_tokens(text: str) -> int:
    """Rough deterministic token estimate (whitespace-separated tokens)."""
    return len(text.split())


def estimate_line_count(text: str) -> int:
    """Number of text lines (always at least one for non-empty text)."""
    return len(text.splitlines())
