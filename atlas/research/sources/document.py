"""Document file source adapter (Phase 17.2).

Normalizes human-readable document files (markdown, JSON, YAML, TOML,
plain text, ...) into :class:`~atlas.research.models.SourceProfile`.
Pure normalization: no AI, no gateway, no storage.
"""

from pathlib import Path

from atlas.research.models import ResearchSource, SourceKind, SourceProfile
from atlas.research.source_catalog import DOCUMENT_EXTENSIONS, DOCUMENT_SCHEMES
from atlas.research.sources._read import (
    build_profile,
    estimate_line_count,
    estimate_tokens,
    language_for,
    safe_read_text,
)


class DocumentSourceAdapter:
    """Adapter for human-readable document files on the local filesystem."""

    def supports(self, uri: str) -> bool:
        if not uri:
            return False
        scheme = _split_scheme(uri)[0]
        if scheme not in DOCUMENT_SCHEMES:
            return False
        resource = _resolve(uri)
        return (
            resource.is_file()
            and resource.suffix.lower() in DOCUMENT_EXTENSIONS
        )

    def load(self, uri: str) -> SourceProfile:
        if not uri:
            raise ValueError("document source URI must not be empty")
        scheme, _ = _split_scheme(uri)
        if scheme not in DOCUMENT_SCHEMES:
            raise ValueError(f"unsupported document source scheme: {scheme!r}")
        resource = _resolve(uri)
        if resource.suffix.lower() not in DOCUMENT_EXTENSIONS:
            raise ValueError(f"not a document file: {uri}")
        text, error = safe_read_text(resource)
        return build_profile(
            uri=uri,
            kind=SourceKind.DOCUMENT,
            text=text,
            byte_size=len(text.encode("utf-8", errors="replace")),
            tokens_estimate=estimate_tokens(text),
            title=resource.name,
            content_type=resource.suffix.lower().lstrip("."),
            language=language_for(resource),
            line_count=estimate_line_count(text),
            load_error=error,
        )

    def metadata(self, uri: str) -> ResearchSource:
        if not uri:
            raise ValueError("document source URI must not be empty")
        scheme, _ = _split_scheme(uri)
        if scheme not in DOCUMENT_SCHEMES:
            raise ValueError(f"unsupported document source scheme: {scheme!r}")
        resource = _resolve(uri)
        return ResearchSource(
            uri=uri,
            kind=SourceKind.DOCUMENT,
            title=resource.name,
            metadata={"uri": uri},
        )


def _split_scheme(uri: str) -> tuple[str, str]:
    """Return ``(scheme, remainder)``. Filesystem paths have no scheme."""
    if "://" not in uri:
        return "", uri
    scheme, _, rest = uri.partition("://")
    return scheme.lower(), rest


def _resolve(uri: str) -> Path:
    """Resolve a document URI to a ``Path`` (pathlib never raises)."""
    if not _split_scheme(uri)[0]:
        return Path(uri)
    return Path(uri.rsplit("://", 1)[1])
