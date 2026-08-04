"""Atlas Research — Source Adapter Layer (Phase 17.2).

Defines the :class:`SourceAdapter` protocol that every concrete source
adapter implements. The protocol is the single seam between the research
planner/coordinator (future phases) and the normalized source layer.

Design constraints (Phase 17.2):
  * Pure data normalization only — no AI, no gateway, no storage.
  * Adapters never raise ``FileNotFoundError``; they fail closed by
    returning a ``SourceProfile`` with empty text and a recorded error in
    ``metadata["load_error"]`` and/or raising ``ValueError`` for malformed
    URIs before any I/O is attempted.
"""

from typing import Protocol, runtime_checkable

from atlas.research.models import ResearchSource, SourceProfile


@runtime_checkable
class SourceAdapter(Protocol):
    """Contract implemented by every research source adapter.

    Implementations normalize one kind of source into the shared
    :class:`SourceProfile` representation so downstream consumers never
    depend on a concrete source format.
    """

    def supports(self, uri: str) -> bool: ...

    def load(self, uri: str) -> SourceProfile: ...

    def metadata(self, uri: str) -> ResearchSource: ...
