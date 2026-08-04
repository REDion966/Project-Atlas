"""Workspace resource source adapter (Phase 17.2).

Normalizes workspace resources under ``workspace://`` URIs into
:class:`~atlas.research.models.SourceProfile`. The adapter is handed a
callable that resolves a workspace-relative resource path to an absolute
filesystem path, so it never needs to know the storage implementation.
Pure normalization: no AI, no gateway, no storage.

``supports()`` never raises: malformed URIs (unknown scheme, absolute
workspace resource) resolve to ``False`` (fail-closed detection); only
``load()``/``metadata()`` raise ``ValueError``, and only for structurally
invalid URIs before any I/O.
"""

from collections.abc import Callable
from pathlib import Path

from atlas.research.models import ResearchSource, SourceKind, SourceProfile
from atlas.research.source_catalog import LANGUAGE_BY_EXTENSION, WORKSPACE_SCHEME
from atlas.research.sources._read import (
    build_profile,
    estimate_line_count,
    estimate_tokens,
    language_for,
    safe_read_text,
)


class WorkspaceSourceAdapter:
    """Adapter for workspace resources resolved against a project root."""

    def __init__(
        self,
        root: Path | None = None,
        resolver: Callable[[str], Path] | None = None,
    ) -> None:
        self._root: Path | None = Path(root) if root else None
        self._resolver: Callable[[str], Path] | None = resolver

    def supports(self, uri: str) -> bool:
        if not uri:
            return False
        scheme, resource_path = _split_workspace_uri(uri)
        if scheme != WORKSPACE_SCHEME:
            return False
        try:
            resource = self._resolve_resource(resource_path)
        except ValueError:
            # Malformed resource (e.g. absolute path): not supported.
            return False
        return (
            resource.is_file()
            and resource.suffix.lower() in LANGUAGE_BY_EXTENSION
        )

    def load(self, uri: str) -> SourceProfile:
        if not uri:
            raise ValueError("workspace source URI must not be empty")
        scheme, resource_path = _split_workspace_uri(uri)
        if scheme != WORKSPACE_SCHEME:
            raise ValueError(f"unsupported workspace source scheme: {scheme!r}")
        resource = self._resolve_resource(resource_path)
        if resource.suffix.lower() not in LANGUAGE_BY_EXTENSION:
            raise ValueError(f"not a supported workspace resource: {uri}")
        text, error = safe_read_text(resource)
        return build_profile(
            uri=uri,
            kind=SourceKind.WORKSPACE,
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
            raise ValueError("workspace source URI must not be empty")
        scheme, resource_path = _split_workspace_uri(uri)
        if scheme != WORKSPACE_SCHEME:
            raise ValueError(f"unsupported workspace source scheme: {scheme!r}")
        resource = self._resolve_resource(resource_path)
        return ResearchSource(
            uri=uri,
            kind=SourceKind.WORKSPACE,
            title=resource.name,
            metadata={"uri": uri},
        )

    def _resolve_resource(self, resource_path: str) -> Path:
        """Resolve a workspace-relative path to an absolute filesystem path."""
        relative = Path(resource_path)
        if relative.is_absolute():
            raise ValueError(f"workspace resource must be relative, got {resource_path!r}")
        if self._resolver is not None:
            resolved = self._resolver(resource_path)
            if not isinstance(resolved, Path):
                raise TypeError("workspace resolver must return a pathlib.Path")
            return resolved
        if self._root is None:
            raise ValueError("workspace adapter requires a root or resolver")
        return self._root / relative


def _split_workspace_uri(uri: str) -> tuple[str, str]:
    """Return ``(scheme, resource_path)`` for ``workspace://`` URIs."""
    if "://" not in uri:
        return "", uri
    scheme, _, rest = uri.partition("://")
    return scheme.lower(), rest
