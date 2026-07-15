"""
Atlas Memory Enums
"""

from enum import Enum


class MemoryType(str, Enum):
    """Types of memory."""

    GENERAL = "general"
    USER = "user"
    PROJECT = "project"
    KNOWLEDGE = "knowledge"
    PREFERENCE = "preference"
    SYSTEM = "system"


class MemoryImportance(int, Enum):
    """Memory priority."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4