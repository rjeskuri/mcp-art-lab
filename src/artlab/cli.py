"""The `artlab` command line."""

import argparse

from artlab import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="artlab",
        description="Build and render the shared Blender test scene in each style.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    # Later tickets add their commands here (render, sheet, ...).
    parser.add_subparsers(dest="command", metavar="command")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.error("a command is required")  # usage to stderr, exit 2
    return 0
