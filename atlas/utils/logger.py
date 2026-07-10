"""
Atlas Logger

Central logging system for Project Atlas.
"""

from datetime import datetime


class Logger:
    """Simple console logger."""

    @staticmethod
    def info(message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] INFO  | {message}")

    @staticmethod
    def warning(message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] WARN  | {message}")

    @staticmethod
    def error(message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ERROR | {message}")