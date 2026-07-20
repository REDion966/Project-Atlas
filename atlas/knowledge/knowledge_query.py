"""
Atlas Knowledge Query
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KnowledgeQuery:
    """
    Query issued against the knowledge engine.
    """

    text: str