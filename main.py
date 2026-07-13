"""
Atlas Entry Point.
"""

from atlas.cli.cli import AtlasCLI


def main():
    cli = AtlasCLI()
    cli.run()


if __name__ == "__main__":
    main()