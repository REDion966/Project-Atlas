"""Atlas Research — Source Adapters (Phase 17.2).

Concrete adapters implementing :class:`~atlas.research.source_adapter.SourceAdapter`.

Currently: document files, workspace resources, codebase files.
A web adapter is deliberately deferred to a later phase — third-party
fetching is out of scope for this layer.
"""

from atlas.research.sources.codebase import CodebaseSourceAdapter
from atlas.research.sources.document import DocumentSourceAdapter
from atlas.research.sources.workspace import WorkspaceSourceAdapter

__all__ = [
    "CodebaseSourceAdapter",
    "DocumentSourceAdapter",
    "WorkspaceSourceAdapter",
]
