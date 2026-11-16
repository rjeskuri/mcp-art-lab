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
    _add_styles_parser(subparsers)
    _add_render_parser(subparsers)
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


# --- styles ----------------------------------------------------------------


def _add_styles_parser(subparsers) -> None:
    styles = subparsers.add_parser(
        "styles",
        help="list the styles, one name per line",
        description="List each <styles-dir>/<name>/build.py style by name.",
    )
    styles.add_argument(
        "--styles-dir",
        type=Path,
        default=Path("styles"),
        help="where the styles are (default: styles)",
    )
    styles.set_defaults(handler=_run_styles)


def _run_styles(args: argparse.Namespace) -> int:
    from artlab.styles import discover

    for name in discover(args.styles_dir):
        print(name)
    return 0


# --- render ----------------------------------------------------------------


def _render_size(value: str) -> int:
    from artlab.render import MIN_SIZE

    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {value!r}") from None
    if number < MIN_SIZE:
        raise argparse.ArgumentTypeError(f"must be at least {MIN_SIZE}, got {number}")
    return number


def _add_render_parser(subparsers) -> None:
    render = subparsers.add_parser(
        "render",
        help="build the test scene in each style and render it",
        description=(
            "Build the test scene in each style and write "
            "<renders-dir>/<style>/manifest.json and <camera>.png, printing each "
            "written path. Styles run in name order and stop at the first failure."
        ),
    )
    render.add_argument(
        "styles",
        nargs="*",
        metavar="STYLE",
        help="styles to render (or --all)",
    )
    render.add_argument("--all", action="store_true", help="render every style")
    render.add_argument(
        "--camera",
        choices=["iso", "hero", "all"],
        default="all",
        help="cameras to render (default: all, iso then hero)",
    )
    render.add_argument(
        "--size",
        type=_render_size,
        default=1024,
        help="square image size in pixels (default: 1024)",
    )
    render.add_argument(
        "--renders-dir",
        type=Path,
        default=Path("renders"),
        help="where to write (default: renders)",
    )
    render.add_argument(
        "--styles-dir",
        type=Path,
        default=Path("styles"),
        help="where the styles are (default: styles)",
    )
    render.add_argument(
        "--no-render",
        action="store_true",
        help="build and write the manifest, render nothing",
    )
    render.add_argument(
        "--save-blend",
        action="store_true",
        help="also save <renders-dir>/<style>/scene.blend",
    )
    render.set_defaults(handler=_run_render)


def _run_render(args: argparse.Namespace) -> int:
    from artlab.blender import BlenderError, BlenderNotFound
    from artlab.render import CAMERA_ORDER, UnknownStyle, render_style
    from artlab.styles import discover

    def fail(message: object, code: int) -> int:
        print(f"artlab render: {message}", file=sys.stderr)
        return code

    if args.all == bool(args.styles):
        return fail("give STYLE names or --all, not both or neither", 2)
    available = discover(args.styles_dir)
    if not available:
        return fail(f"no styles in {args.styles_dir} (each is <name>/build.py)", 2)
    names = sorted(available) if args.all else sorted(set(args.styles))
    unknown = [name for name in names if name not in available]
    if unknown:
        return fail(UnknownStyle(unknown, args.styles_dir, available), 2)

    cameras = CAMERA_ORDER if args.camera == "all" else (args.camera,)
    for name in names:
        print(f"artlab render: {name}", file=sys.stderr, flush=True)
        try:
            result = render_style(
                name,
                styles_dir=args.styles_dir,
                renders_dir=args.renders_dir,
                cameras=cameras,
                size=args.size,
                render=not args.no_render,
                save_blend=args.save_blend,
            )
        except BlenderNotFound as error:
            return fail(error, 2)
        except BlenderError as error:
            return fail(error, 1)
        for path in (result.manifest, result.blend, *result.images.values()):
            if path is not None:
                print(path, flush=True)
    return 0


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
