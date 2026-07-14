"""
Atlas Conversation Storage

Handles saving and loading conversations.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.conversation.conversation import Conversation


class ConversationStorage:
    """Handles conversation persistence."""

    STORAGE_DIR = Path("atlas_data/conversations")

    def __init__(self):
        self.STORAGE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    def save(
        self,
        conversation: Conversation,
    ) -> Path:
        """
        Save a conversation to disk.

        Returns:
            Path to the saved file.
        """

        filename = (
            f"{conversation.created_at.strftime('%Y-%m-%d_%H-%M-%S')}.json"
        )

        filepath = self.STORAGE_DIR / filename

        filepath.write_text(
            json.dumps(
                conversation.to_dict(),
                indent=4,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return filepath

    def load(
        self,
        filepath: Path,
    ) -> Conversation:
        """
        Load a conversation from disk.
        """

        data = json.loads(
            filepath.read_text(
                encoding="utf-8"
            )
        )

        return Conversation.from_dict(data)

    def list(self) -> list[Path]:
        """
        Return all saved conversations.
        """

        return sorted(
            self.STORAGE_DIR.glob("*.json")
        )