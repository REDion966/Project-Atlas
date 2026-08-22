"""Atlas Evolution Autonomy — Production State Adapters (Foundation Strengthening Batch 9).

Production ``StateReader`` / ``StateWriter`` implementations that wrap the
real kernel services for the four Phase 16 state scopes:

- :class:`~atlas.evolution.autonomy.adapters.memory_adapter.MemoryStateAdapter`
- :class:`~atlas.evolution.autonomy.adapters.knowledge_adapter.KnowledgeStateAdapter`
- :class:`~atlas.evolution.autonomy.adapters.config_adapter.ConfigStateAdapter`
- :class:`~atlas.evolution.autonomy.adapters.capability_adapter.CapabilityStateAdapter`

Each adapter implements the existing ``StateReader`` / ``StateWriter``
protocols from :mod:`atlas.evolution.autonomy.applier` and provides
deterministic key namespaces:

- ``memory.<memory_id>``
- ``knowledge.<entry_id>``
- ``config.<section>.<field>``
- ``capability.<name>``

These adapters are the linchpin of the governed ingest loop (Batches 9+).
They are independently constructible and testable; they are intentionally
NOT wired into ``ApplicationEngine`` or ``Atlas.start()`` in this batch.

No governance, autonomy, runtime, schema, or public service key changes.
"""

from atlas.evolution.autonomy.adapters.capability_adapter import (
    CapabilityStateAdapter,
)
from atlas.evolution.autonomy.adapters.config_adapter import ConfigStateAdapter
from atlas.evolution.autonomy.adapters.knowledge_adapter import (
    KnowledgeStateAdapter,
)
from atlas.evolution.autonomy.adapters.memory_adapter import MemoryStateAdapter

__all__ = [
    "MemoryStateAdapter",
    "KnowledgeStateAdapter",
    "ConfigStateAdapter",
    "CapabilityStateAdapter",
]
