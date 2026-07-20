"""
Atlas Knowledge Entry
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KnowledgeEntry:
    """
    Represents one piece of Atlas knowledge.
    """

    title: str

    content: str

    source: str