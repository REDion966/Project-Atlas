"""
Backward-compatibility alias.

MemoryService is now MemoryManagerService.
Import directly from memory_manager_service in new code.
"""

from atlas.memory.service.memory_manager_service import MemoryManagerService  # noqa: F401

MemoryService = MemoryManagerService

__all__ = [
    "MemoryService",
]
