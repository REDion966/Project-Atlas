"""
Atlas AI Provider Health

Tracks provider availability.
"""


class ProviderHealth:
    """Tracks AI provider health."""

    def __init__(self):
        self._status = {}

    def mark_available(
        self,
        provider: str,
    ):
        self._status[provider] = True

    def mark_unavailable(
        self,
        provider: str,
    ):
        self._status[provider] = False

    def is_available(
        self,
        provider: str,
    ) -> bool:

        return self._status.get(
            provider,
            True,
        )

    def status(self):
        return dict(
            self._status
        )