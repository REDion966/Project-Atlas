"""
Atlas Service Registry

Keeps track of all Atlas services.
"""

from atlas.services.service import Service


class ServiceRegistry:
    """Registry for Atlas services."""

    def __init__(self):
        self._services = {}

    def register(self, service: Service):
        """Register a service."""

        if service.name in self._services:
            raise ValueError(f"Service '{service.name}' is already registered.")

        self._services[service.name] = service

    def get(self, name: str):
        """Return a registered service."""

        return self._services.get(name)

    def start_all(self):
        """Start all registered services."""

        for service in self._services.values():
            service.start()

    def list_services(self):
        """Return all registered service names."""

        return list(self._services.keys())