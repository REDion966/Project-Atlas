"""
Atlas Command Line Interface.
"""

from atlas.cli.command_router import CommandRouter
from atlas.kernel.atlas import Atlas


class AtlasCLI:
    """Interactive command-line interface for Atlas."""

    def __init__(self):
        self._atlas = Atlas()
        self._router = CommandRouter(self._atlas)

    def run(self):
        """Run the interactive CLI."""

        print("=" * 45)
        print("         Atlas AI Assistant")
        print("=" * 45)
        print("Type '/help' for commands.")
        print("Type '/exit' or 'exit' to quit.\n")

        self._atlas.start()

        try:
            while True:
                user_input = input("You > ").strip()

                if not user_input:
                    continue

                if user_input.lower() in (
                    "exit",
                    "/exit",
                    "quit",
                ):
                    print("\nGoodbye!")
                    break

                # Handle slash commands
                if self._router.execute(user_input):
                    continue

                print("\nAtlas > ", end="", flush=True)

                for chunk in self._atlas.stream(user_input):
                    print(chunk, end="", flush=True)

                print("\n")

        finally:
            self._atlas.shutdown()