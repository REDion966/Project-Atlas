"""
Atlas Startup Module

Responsible for starting Atlas and displaying
basic startup information.
"""

from atlas.config.settings import (
    PROJECT_NAME,
    VERSION,
    AUTHOR,
    WELCOME_MESSAGE,
)

def start():
    """Start Atlas."""

    print("=" * 40)
    print(PROJECT_NAME)
    print("=" * 40)

    print(f"Version: {VERSION}")
    print(f"Author: {AUTHOR}")
    print()

    print(WELCOME_MESSAGE)
    print()