"""The `artlab` command line."""

import argparse
import sys
from pathlib import Path

from artlab import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="artlab",
        description="Build and render the shared Blender test scene in each style.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    # Each command adds its own subparser and sets `handler`.
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    _add_sheet_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.error("a command is required")  # usage to stderr, exit 2
    return args.handler(args)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {number}")
    return number


# --- sheet -----------------------------------------------------------------


def _add_sheet_parser(subparsers) -> None:
    sheet = subparsers.add_parser(
        "sheet",
        help="lay every style's renders out in one contact sheet PNG",
        description=(
            "Lay out <renders-dir>/<style>/<camera>.png as a contact sheet: "
            "styles are columns, cameras are rows, and the sheet's path is printed."
        ),
    )
    sheet.add_argument(
        "styles",
        nargs="*",
        metavar="STYLE",
        help="styles to show, in column order (default: every complete style, by name)",
    )
    sheet.add_argument(
        "--camera",
        choices=["iso", "hero", "all"],
        default="all",
        help="rows to show (default: all, iso then hero)",
    )
    sheet.add_argument(
        "--renders-dir",
        type=Path,
        default=Path("renders"),
        help="where the renders are (default: renders)",
    )
    sheet.add_argument(
        "--out",
        type=Path,
        help="the PNG to write (default: <renders-dir>/contact-sheet.png)",
    )
    sheet.add_argument(
        "--tile",
        type=_positive_int,
        default=512,
        help="tile size in pixels (default: 512)",
    )
    sheet.set_defaults(handler=_run_sheet)


def _run_sheet(args: argparse.Namespace) -> int:
    from artlab.sheet import CAMERAS, MissingRender, NoRenders, make_sheet

    cameras = list(CAMERAS) if args.camera == "all" else [args.camera]
    out = args.out or args.renders_dir / "contact-sheet.png"
    try:
        path = make_sheet(
            args.renders_dir, args.styles or None, cameras, out, tile=args.tile
        )
    except (MissingRender, NoRenders) as error:
        print(f"artlab sheet: {error}", file=sys.stderr)
        return 2
    print(path)
    return 0
