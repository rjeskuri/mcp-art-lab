"""The contact sheet: every style's renders side by side in one PNG.

Columns are styles, rows are cameras, and each tile has a `<style> / <camera>`
label in the strip under it. Renders are read from `<renders_dir>/<style>/<camera>.png`.
"""

from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BACKGROUND = (24, 24, 24)
LABEL_COLOR = (210, 210, 210)
CAMERAS = ("iso", "hero")


class MissingRender(FileNotFoundError):
    """A requested style has no render for one of the requested cameras."""

    def __init__(self, path: Path, style: str) -> None:
        super().__init__(
            f"missing render {path}; run `artlab render {style}` to make it"
        )
        self.path = path
        self.style = style


class NoRenders(Exception):
    """Auto-discovery found no style directory with every requested camera."""


def make_sheet(
    renders_dir: Path,
    styles: Sequence[str] | None,
    cameras: Sequence[str],
    out: Path,
    *,
    tile: int = 512,
    gap: int = 16,
    label_height: int = 40,
) -> Path:
    """Write the contact sheet as an RGB PNG at `out` and return `out`.

    `styles=None` takes every subdirectory of `renders_dir` that has all of
    `cameras`, in name order. Raises MissingRender for a requested style
    without a render and NoRenders when there is nothing to lay out; either
    way nothing is written.
    """
    renders_dir = Path(renders_dir)
    if styles is None:
        styles = _discover(renders_dir, cameras)
    if not styles:
        raise NoRenders(
            f"no renders in {renders_dir}: a style needs "
            + " and ".join(f"<style>/{camera}.png" for camera in cameras)
            + "; run `artlab render <style>` to make them"
        )
    paths = [
        [renders_dir / style / f"{camera}.png" for style in styles]
        for camera in cameras
    ]
    for row in paths:
        for style, path in zip(styles, row, strict=True):
            if not path.is_file():
                raise MissingRender(path, style)

    width = len(styles) * tile + (len(styles) + 1) * gap
    height = len(cameras) * (tile + label_height) + (len(cameras) + 1) * gap
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    font = _label_font(label_height)
    for r, (camera, row) in enumerate(zip(cameras, paths, strict=True)):
        for c, (style, path) in enumerate(zip(styles, row, strict=True)):
            x = gap + c * (tile + gap)
            y = gap + r * (tile + label_height + gap)
            sheet.paste(_tile(path, tile), (x, y))
            if label_height > 0:
                label = _label(f"{style} / {camera}", tile, label_height, font)
                sheet.paste(label, (x, y + tile))

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, format="PNG")
    return out


def _discover(renders_dir: Path, cameras: Sequence[str]) -> list[str]:
    if not renders_dir.is_dir():
        return []
    return sorted(
        d.name
        for d in renders_dir.iterdir()
        if d.is_dir() and all((d / f"{camera}.png").is_file() for camera in cameras)
    )


def _tile(path: Path, tile: int) -> Image.Image:
    """The render fitted into a `tile` square, centered on BACKGROUND.

    Upscaling is nearest-neighbour so pixel art keeps its colors; downscaling
    is Lanczos. Transparent pixels show BACKGROUND.
    """
    with Image.open(path) as src:
        render = src.convert("RGBA")
    scale = min(tile / render.width, tile / render.height)
    size = (
        max(1, min(tile, round(render.width * scale))),
        max(1, min(tile, round(render.height * scale))),
    )
    if scale > 1:
        render = render.resize(size, Image.Resampling.NEAREST)
    elif scale < 1:
        render = render.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (tile, tile), BACKGROUND)
    offset = ((tile - render.width) // 2, (tile - render.height) // 2)
    canvas.paste(render.convert("RGB"), offset, mask=render.getchannel("A"))
    return canvas


def _label_font(label_height: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=max(6, label_height // 2))


def _label(
    text: str,
    width: int,
    height: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> Image.Image:
    """The label strip on its own image, so the text can never leave the strip."""
    strip = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(strip)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    x = max(0, (width - (right - left)) // 2) - left
    y = (height - (bottom - top)) // 2 - top
    draw.text((x, y), text, fill=LABEL_COLOR, font=font)
    return strip
