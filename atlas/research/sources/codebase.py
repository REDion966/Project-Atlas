"""Codebase file source adapter (Phase 17.2).

Normalizes source code files (Python, TypeScript, Rust, Go, ...) into
:class:`~atlas.research.models.SourceProfile`. Accepts bare filesystem
paths as well as ``code://`` and ``file://`` URIs. Pure normalization:
no AI, no gateway, no storage.

Ownership rule (shared with the document adapter): only files whose
extension is a known code extension are claimed — a ``.md`` file is never
a codebase source, even under a ``code://`` URI. This keeps adapter
support disjoint.
"""

from pathlib import Path

from atlas.research.models import ResearchSource, SourceKind, SourceProfile
from atlas.research.source_catalog import (
    CODE_EXTENSIONS,
    CODEBASE_SCHEMES,
    LANGUAGE_BY_EXTENSION,
)
from atlas.research.sources._read import (
    build_profile,
    estimate_line_count,
    estimate_tokens,
    language_for,
    safe_read_text,
)


class CodebaseSourceAdapter:
    """Adapter for source code files on the local filesystem."""

    def supports(self, uri: str) -> bool:
        if not uri:
            return False
        scheme = _split_scheme(uri)[0]
        if scheme not in CODEBASE_SCHEMES:
            return False
        resource = _resolve(uri)
        return (
            resource.is_file()
            and resource.suffix.lower() in CODE_EXTENSIONS
        )

    def load(self, uri: str) -> SourceProfile:
        if not uri:
            raise ValueError("codebase source URI must not be empty")
        scheme, _ = _split_scheme(uri)
        if scheme not in CODEBASE_SCHEMES:
            raise ValueError(f"unsupported codebase source scheme: {scheme!r}")
        resource = _resolve(uri)
        if resource.suffix.lower() not in CODE_EXTENSIONS:
            raise ValueError(f"not a code file: {uri}")
        text, error = safe_read_text(resource)
        extension = resource.suffix.lower()
        return build_profile(
            uri=uri,
            kind=SourceKind.CODEBASE,
            text=text,
            byte_size=len(text.encode("utf-8", errors="replace")),
            tokens_estimate=estimate_tokens(text),
            title=resource.name,
            content_type=extension.lstrip("."),
            language=language_for(resource) or LANGUAGE_BY_EXTENSION.get(extension, ""),
            line_count=estimate_line_count(text),
            load_error=error,
        )

    def metadata(self, uri: str) -> ResearchSource:
        if not uri:
            raise ValueError("codebase source URI must not be empty")
        scheme, _ = _split_scheme(uri)
        if scheme not in CODEBASE_SCHEMES:
            raise ValueError(f"unsupported codebase source scheme: {scheme!r}")
        resource = _resolve(uri)
        return ResearchSource(
            uri=uri,
            kind=SourceKind.CODEBASE,
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
    """Resolve a codebase URI to a ``Path`` (pathlib never raises)."""
    if not _split_scheme(uri)[0]:
        return Path(uri)
    return Path(uri.rsplit("://", 1)[1])
