"""
Atlas Error Handler

Centralized error handling for Project Atlas.
"""

from atlas.utils.logger import Logger


class ErrorHandler:
    """Handles unexpected errors."""

    @staticmethod
    def handle(error: Exception, context: str = "Unknown"):
        """Log an error with context."""

        Logger.error(f"{context}: {type(error).__name__}: {error}")