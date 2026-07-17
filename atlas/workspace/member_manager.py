"""
Atlas Member Manager.

Manages workspace members.
"""

from __future__ import annotations

from atlas.workspace.models.member import Member
from atlas.workspace.models.workspace import Workspace


class MemberManager:
    """Manage workspace members."""

    def __init__(
        self,
        workspace: Workspace,
    ) -> None:
        self.workspace = workspace

    def create_member(
        self,
        name: str,
    ) -> Member:
        """Create a member."""

        member = Member(
            name=name,
        )

        self.workspace.members.append(
            member,
        )

        self.workspace.touch()

        return member

    def get_member(
        self,
        member_id: str,
    ) -> Member | None:
        """Return a member."""

        for member in self.workspace.members:
            if member.id == member_id:
                return member

        return None

    def list_members(
        self,
    ) -> list[Member]:
        """Return all members."""

        return self.workspace.members

    def delete_member(
        self,
        member_id: str,
    ) -> bool:
        """Delete a member."""

        member = self.get_member(
            member_id,
        )

        if member is None:
            return False

        self.workspace.members.remove(
            member,
        )

        self.workspace.touch()

        return True