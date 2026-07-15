"""
Atlas Workspace Enums
"""

from enum import Enum


class ResourceType(str, Enum):
    """Supported Atlas resource types."""

    FILE = "file"
    FOLDER = "folder"
    GIT = "git"
    WEBSITE = "website"
    API = "api"
    DATABASE = "database"


class PermissionLevel(str, Enum):
    """Permission levels."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    FULL = "full"