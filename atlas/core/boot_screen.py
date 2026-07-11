"""
Atlas Boot Screen
"""


from atlas.config.settings import Settings


class BootScreen:
    """Displays the Atlas startup screen."""

    @staticmethod
    def show():

        print("=" * 50)
        print(f"{Settings.PROJECT_NAME:^50}")
        print("=" * 50)
        print(f"Version : {Settings.VERSION}")
        print(f"Author  : {Settings.AUTHOR}")
        print()
        print("Status  : Booting...")
        print("=" * 50)
        print()