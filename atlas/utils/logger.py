"""
Atlas Logger

Central logging system for Project Atlas.
"""

from datetime import datetime
from pathlib import Path

# Ensure the logs directory exists
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "atlas.log"


class Logger:
    """Atlas logging utility."""

    @staticmethod
    def _write(level: str, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {level:<5} | {message}"

        # Print to console
        print(log_entry)

        # Save to log file
        with open(LOG_FILE, "a", encoding="utf-8") as file:
            file.write(log_entry + "\n")

    @staticmethod
    def info(message: str):
        Logger._write("INFO", message)

    @staticmethod
    def warning(message: str):
        Logger._write("WARN", message)

    @staticmethod
    def error(message: str):
        Logger._write("ERROR", message)