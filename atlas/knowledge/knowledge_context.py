"""
Atlas Knowledge Context
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KnowledgeContext:
    """
    Context supplied when searching knowledge.
    """

    query: str