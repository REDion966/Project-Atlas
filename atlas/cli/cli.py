"""
Atlas Command Line Interface.
"""

from atlas.kernel.atlas import Atlas


class AtlasCLI:
    """Interactive command-line interface for Atlas."""

    def __init__(self):
        self._atlas = Atlas()

    def run(self):
        """Run the interactive CLI."""

        print("=" * 45)
        print("         Atlas AI Assistant")
        print("=" * 45)
        print("Type 'exit' to quit.\n")

        self._atlas.start()

        try:
            while True:
                user_input = input("You > ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit"):
                    print("\nGoodbye!")
                    break

                response = self._atlas.chat(user_input)

                print(f"\nAtlas > {response.content}\n")

        finally:
            self._atlas.shutdown()