"""
Atlas Service Container

Central registry and lifecycle manager for Atlas services.
"""

from typing import Any


class ServiceContainer:
    """
    Stores, retrieves, starts, and stops Atlas services.
    """

    def __init__(self):
        self._services: dict[str, Any] = {}

    def register(self, name: str, service: Any) -> None:
        """
        Register a service.
        """

        if name in self._services:
            raise ValueError(
                f"Service '{name}' is already registered."
            )

        self._services[name] = service


    def get(self, name: str) -> Any:
        """
        Retrieve a registered service.
        """

        if name not in self._services:
            raise KeyError(
                f"Service '{name}' is not registered."
            )

        return self._services[name]


    def resolve(self, name: str) -> Any:
        """
        Resolve a service.

        Alias for get().
        Used by higher-level Atlas components.
        """

        return self.get(name)


    def has(self, name: str) -> bool:
        """
        Check whether a service exists.
        """

        return name in self._services


    def remove(self, name: str) -> None:
        """
        Remove a registered service.
        """

        if name not in self._services:
            raise KeyError(
                f"Service '{name}' is not registered."
            )

        del self._services[name]


    def clear(self) -> None:
        """
        Remove all services.
        """

        self._services.clear()


    def names(self) -> list[str]:
        """
        Return registered service names.
        """

        return sorted(self._services.keys())


    def start_all(self) -> None:
        """
        Start every registered service.
        """

        for service in self._services.values():

            start = getattr(service, "start", None)

            if callable(start):
                start()


    def stop_all(self) -> None:
        """
        Stop every registered service.
        """

        services = list(self._services.values())

        for service in reversed(services):

            stop = getattr(service, "stop", None)

            if callable(stop):
                stop()
