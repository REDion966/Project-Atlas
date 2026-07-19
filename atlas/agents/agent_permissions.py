"""
Atlas Agent Permissions

Controls what agents are allowed to access.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentPermissions:
    """
    Security boundaries for an agent.
    """

    permissions: set[str] = field(
        default_factory=set
    )


    def grant(
        self,
        permission: str,
    ) -> None:
        """
        Grant permission.
        """

        self.permissions.add(permission)


    def revoke(
        self,
        permission: str,
    ) -> None:
        """
        Remove permission.
        """

        self.permissions.discard(permission)


    def allows(
        self,
        permission: str,
    ) -> bool:
        """
        Check permission.
        """

        return permission in self.permissions


    def list(self) -> list[str]:
        """
        Return permissions.
        """

        return sorted(
            self.permissions
        )


    def to_dict(self) -> dict:
        return {
            "permissions": self.list()
        }