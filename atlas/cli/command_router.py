"""
Atlas Command Router.

Routes CLI slash commands.
"""

from atlas.config.settings import Settings
from atlas.kernel.atlas import Atlas


class CommandRouter:
    """Routes CLI commands."""

    def __init__(self, atlas: Atlas):
        self._atlas = atlas

    def execute(self, command: str) -> bool:
        """
        Execute a CLI command.

        Returns:
            True if the command was handled.
            False if it is not a command.
        """

        if not command.startswith("/"):
            return False

        command = command.lower().strip()

        if command == "/help":
            self._show_help()
            return True

        if command == "/version":
            self._show_version()
            return True

        if command == "/provider":
            self._show_provider()
            return True

        if command == "/models":
            self._show_models()
            return True

        if command == "/save":
            self._save_conversation()
            return True

        if command == "/load":
            self._load_conversation()
            return True

        return False

    def _show_help(self):
        """Display available commands."""

        print("\nAvailable Commands\n")
        print("  /help      Show this help menu")
        print("  /version   Show Atlas version")
        print("  /provider  Show active AI provider")
        print("  /models    Show installed AI models")
        print("  /save      Save current conversation")
        print("  /load      Load a saved conversation")
        print("  /clear     Clear the screen")
        print("  /exit      Exit Atlas")
        print()

    def _show_version(self):
        """Display Atlas version information."""

        print("\nProject Information\n")
        print(f"Project : {Settings.PROJECT_NAME}")
        print(f"Version : {Settings.VERSION}")
        print(f"Author  : {Settings.AUTHOR}")
        print()

    def _show_provider(self):
        """Display the active AI provider."""

        provider = self._atlas.provider

        print("\nCurrent Provider\n")
        print(f"Provider : {provider.name()}")
        print()

    def _show_models(self):
        """Display installed AI models."""

        models = self._atlas.models()

        print("\nInstalled Models\n")

        for index, model in enumerate(models, start=1):
            print(f"{index}. {model}")

        print()

    def _save_conversation(self):
        """Save the current conversation."""

        filepath = self._atlas.save_conversation()

        print("\nConversation Saved\n")
        print(filepath)
        print()

    def _load_conversation(self):
        """Load a saved conversation."""

        files = self._atlas.saved_conversations()

        if not files:
            print("\nNo saved conversations found.\n")
            return

        print("\nSaved Conversations\n")

        for index, file in enumerate(files, start=1):
            print(f"{index}. {file.name}")

        print()

        try:
            choice = int(
                input("Select conversation: ")
            )

            if choice < 1 or choice > len(files):
                print("\nInvalid selection.\n")
                return

        except ValueError:
            print("\nInvalid selection.\n")
            return

        filepath = files[choice - 1]

        self._atlas.load_conversation(
            filepath
        )

        print("\nConversation Loaded\n")