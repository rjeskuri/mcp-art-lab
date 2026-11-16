"""The contact sheet: `artlab.sheet.make_sheet` and the `artlab sheet` command.

Input renders are small PNGs made with Pillow in tmp_path; expected pixels come
from the layout formula in ticket #6, never from the code under test:
  width  = n_styles * tile + (n_styles + 1) * gap
  height = n_cameras * (tile + label_height) + (n_cameras + 1) * gap
  tile (r, c) top-left = (gap + c * (tile + gap), gap + r * (tile + label_height + gap))
"""

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from artlab.sheet import BACKGROUND, MissingRender, NoRenders, make_sheet

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)

# make_sheet's defaults, which the CLI uses (it exposes only --tile).
DEFAULT_TILE = 512
DEFAULT_GAP = 16
DEFAULT_LABEL = 40


def run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "artlab", "sheet", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def printed_path(result: subprocess.CompletedProcess[str], cwd: Path) -> Path:
    """The path the command printed, resolved against the cwd it ran in."""
    return (cwd / result.stdout.strip()).resolve()


def solid(path: Path, color, size=(64, 64), mode="RGB") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path)


def from_pixels(path: Path, rows: list[list[tuple]], mode="RGB") -> None:
    """A render whose pixel (x, y) is rows[y][x]."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new(mode, (len(rows[0]), len(rows)))
    img.putdata([px for row in rows for px in row])
    img.save(path)


def four_renders(root: Path, size=(64, 64)) -> None:
    solid(root / "a" / "iso.png", RED, size)
    solid(root / "a" / "hero.png", GREEN, size)
    solid(root / "b" / "iso.png", BLUE, size)
    solid(root / "b" / "hero.png", YELLOW, size)


def sheet_size(n_styles, n_cameras, tile, gap, label):
    return (
        n_styles * tile + (n_styles + 1) * gap,
        n_cameras * (tile + label) + (n_cameras + 1) * gap,
    )


def tile_origin(r, c, tile, gap, label):
    return gap + c * (tile + gap), gap + r * (tile + label + gap)


def tile_box(r, c, tile, gap, label):
    x, y = tile_origin(r, c, tile, gap, label)
    return (x, y, x + tile, y + tile)


def strip_box(r, c, tile, gap, label):
    x, y = tile_origin(r, c, tile, gap, label)
    return (x, y + tile, x + tile, y + tile + label)


def tile_center(img, r, c, tile, gap, label):
    x, y = tile_origin(r, c, tile, gap, label)
    return img.getpixel((x + tile // 2, y + tile // 2))


def colors_in(img, box) -> set:
    region = img.crop(box)
    return {color for _, color in region.getcolors(region.width * region.height)}


def open_rgb(path: Path) -> Image.Image:
    img = Image.open(path)
    img.load()
    assert img.format == "PNG"
    assert img.mode == "RGB"
    return img


# --- Broad behavior ---------------------------------------------------------


@pytest.mark.parametrize(
    ("styles", "cameras", "tile", "gap", "label"),
    [
        (["a", "b"], ["iso", "hero"], 64, 8, 20),  # the ticket's case: 152x192
        (["p", "q", "r"], ["hero"], 32, 4, 10),
        (["solo"], ["hero", "iso"], 40, 6, 12),  # rows follow `cameras`, not iso-first
        (["m", "n"], ["iso", "hero"], 24, 2, 16),  # narrow gaps
    ],
)
def test_sheet_lays_out_styles_by_camera(tmp_path, styles, cameras, tile, gap, label):
    renders = tmp_path / "renders"
    if styles == ["a", "b"]:
        four_renders(renders)
        expected = {("a", "iso"): RED, ("a", "hero"): GREEN}
        expected |= {("b", "iso"): BLUE, ("b", "hero"): YELLOW}
    else:
        # A distinct color per (style, camera), renders the size of the tile.
        expected = {}
        for i, style in enumerate(styles):
            for j, camera in enumerate(["iso", "hero"]):
                color = (40 + 50 * i, 200 - 60 * j, 90 + 30 * i + 70 * j)
                expected[(style, camera)] = color
                solid(renders / style / f"{camera}.png", color, (tile, tile))
    out = tmp_path / "sheet.png"

    result = make_sheet(
        renders, styles, cameras, out, tile=tile, gap=gap, label_height=label
    )

    assert Path(result) == out
    img = open_rgb(out)
    assert img.size == sheet_size(len(styles), len(cameras), tile, gap, label)
    if styles == ["a", "b"]:
        assert img.size == (152, 192)
    for r, camera in enumerate(cameras):
        for c, style in enumerate(styles):
            color = expected[(style, camera)]
            assert tile_center(img, r, c, tile, gap, label) == color, (r, c)
            # The whole tile, and nothing past its corner, is the render.
            assert colors_in(img, tile_box(r, c, tile, gap, label)) == {color}
            x, y = tile_origin(r, c, tile, gap, label)
            if gap:
                assert img.getpixel((x - 1, y - 1)) == BACKGROUND, (r, c)
    if gap:
        assert img.getpixel((0, 0)) == BACKGROUND
        assert img.getpixel((img.width - 1, img.height - 1)) == BACKGROUND


def test_cli_writes_default_path_with_iso_row_first(tmp_path):
    renders = tmp_path / "shots"
    four_renders(renders)

    result = run_cli(["--renders-dir", str(renders)], tmp_path)

    assert result.returncode == 0, result.stderr
    out = renders / "contact-sheet.png"
    assert out.is_file()
    assert printed_path(result, tmp_path) == out.resolve()
    img = open_rgb(out)
    t, g, lab = DEFAULT_TILE, DEFAULT_GAP, DEFAULT_LABEL
    assert img.size == sheet_size(2, 2, t, g, lab)
    assert tile_center(img, 0, 0, t, g, lab) == RED  # a / iso
    assert tile_center(img, 0, 1, t, g, lab) == BLUE  # b / iso
    assert tile_center(img, 1, 0, t, g, lab) == GREEN  # a / hero
    assert tile_center(img, 1, 1, t, g, lab) == YELLOW  # b / hero


def test_cli_default_renders_dir_and_out_and_tile_options(tmp_path):
    # No options: reads ./renders, writes ./renders/contact-sheet.png.
    four_renders(tmp_path / "renders", size=(16, 16))
    result = run_cli([], tmp_path)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "renders" / "contact-sheet.png"
    assert out.is_file()
    assert printed_path(result, tmp_path) == out.resolve()

    # --out and --tile.
    custom = tmp_path / "elsewhere.png"
    result = run_cli(["--out", str(custom), "--tile", "96"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert printed_path(result, tmp_path) == custom.resolve()
    img = open_rgb(custom)
    assert img.size == sheet_size(2, 2, 96, DEFAULT_GAP, DEFAULT_LABEL)
    assert tile_center(img, 1, 1, 96, DEFAULT_GAP, DEFAULT_LABEL) == YELLOW


def test_styles_argument_sets_column_order(tmp_path):
    renders = tmp_path / "renders"
    four_renders(renders)
    solid(renders / "c" / "iso.png", (10, 120, 200))
    solid(renders / "c" / "hero.png", (200, 120, 10))
    t, g, lab = 64, 8, 20

    out = make_sheet(
        renders,
        ["b", "a"],
        ["iso", "hero"],
        tmp_path / "x.png",
        tile=t,
        gap=g,
        label_height=lab,
    )
    img = open_rgb(out)
    assert img.size == sheet_size(2, 2, t, g, lab)  # c is left out
    assert tile_center(img, 0, 0, t, g, lab) == BLUE
    assert tile_center(img, 0, 1, t, g, lab) == RED
    assert tile_center(img, 1, 0, t, g, lab) == YELLOW
    assert tile_center(img, 1, 1, t, g, lab) == GREEN

    # Through the CLI: positional styles, in the order given.
    cli_out = tmp_path / "cli.png"
    result = run_cli(
        [
            "c",
            "a",
            "--renders-dir",
            str(renders),
            "--out",
            str(cli_out),
            "--tile",
            "64",
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    img = open_rgb(cli_out)
    t, g, lab = 64, DEFAULT_GAP, DEFAULT_LABEL
    assert img.size == sheet_size(2, 2, t, g, lab)
    assert tile_center(img, 0, 0, t, g, lab) == (10, 120, 200)
    assert tile_center(img, 0, 1, t, g, lab) == RED
    assert tile_center(img, 1, 0, t, g, lab) == (200, 120, 10)


def test_camera_option_selects_rows(tmp_path):
    renders = tmp_path / "renders"
    four_renders(renders)
    t, g, lab = 64, DEFAULT_GAP, DEFAULT_LABEL

    for camera, colors in [("hero", (GREEN, YELLOW)), ("iso", (RED, BLUE))]:
        out = tmp_path / f"{camera}.png"
        result = run_cli(
            [
                "--camera",
                camera,
                "--renders-dir",
                str(renders),
                "--out",
                str(out),
                "--tile",
                str(t),
            ],
            tmp_path,
        )
        assert result.returncode == 0, result.stderr
        img = open_rgb(out)
        assert img.height == t + lab + 2 * g
        assert img.size == sheet_size(2, 1, t, g, lab)
        assert tile_center(img, 0, 0, t, g, lab) == colors[0]
        assert tile_center(img, 0, 1, t, g, lab) == colors[1]

    # `all` is iso then hero.
    out = tmp_path / "all.png"
    result = run_cli(
        [
            "--camera",
            "all",
            "--renders-dir",
            str(renders),
            "--out",
            str(out),
            "--tile",
            str(t),
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    img = open_rgb(out)
    assert img.size == sheet_size(2, 2, t, g, lab)
    assert tile_center(img, 0, 0, t, g, lab) == RED
    assert tile_center(img, 1, 0, t, g, lab) == GREEN

    # Only the requested camera has to exist.
    (renders / "b" / "hero.png").unlink()
    out = tmp_path / "iso-only.png"
    result = run_cli(
        [
            "a",
            "b",
            "--camera",
            "iso",
            "--renders-dir",
            str(renders),
            "--out",
            str(out),
            "--tile",
            str(t),
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert tile_center(open_rgb(out), 0, 1, t, g, lab) == BLUE


# --- Scaling, aspect and transparency --------------------------------------


def test_small_renders_upscale_without_blending(tmp_path):
    renders = tmp_path / "renders"
    c1, c2 = (200, 30, 60), (20, 160, 220)
    checker = [[c1 if (x + y) % 2 == 0 else c2 for x in range(4)] for y in range(4)]
    from_pixels(renders / "s" / "iso.png", checker)
    t, g, lab = 64, 8, 20

    img = open_rgb(
        make_sheet(
            renders, ["s"], ["iso"], tmp_path / "x.png", tile=t, gap=g, label_height=lab
        )
    )

    assert colors_in(img, tile_box(0, 0, t, g, lab)) == {c1, c2}
    # Nearest neighbour: each source pixel becomes a 16x16 block in place.
    x0, y0 = tile_origin(0, 0, t, g, lab)
    for sy in range(4):
        for sx in range(4):
            block = (x0 + 16 * sx, y0 + 16 * sy, x0 + 16 * sx + 16, y0 + 16 * sy + 16)
            assert colors_in(img, block) == {checker[sy][sx]}, (sx, sy)

    # A non-integer scale (5x3 into 64) still adds no colors.
    pal = [(250, 250, 0), (0, 90, 40), (120, 0, 200)]
    rows = [[pal[(x + 2 * y) % 3] for x in range(5)] for y in range(3)]
    from_pixels(renders / "odd" / "iso.png", rows)
    img = open_rgb(
        make_sheet(
            renders,
            ["odd"],
            ["iso"],
            tmp_path / "y.png",
            tile=t,
            gap=g,
            label_height=lab,
        )
    )
    found = colors_in(img, tile_box(0, 0, t, g, lab))
    assert set(pal) <= found <= set(pal) | {BACKGROUND}


def test_large_renders_downscale_with_filtering(tmp_path):
    # A 1 px red/blue checker halved: nearest would keep pure red and blue,
    # Lanczos averages them to a mix.
    renders = tmp_path / "renders"
    checker = [
        [RED if (x + y) % 2 == 0 else BLUE for x in range(128)] for y in range(128)
    ]
    from_pixels(renders / "big" / "iso.png", checker)
    t, g, lab = 64, 8, 20

    img = open_rgb(
        make_sheet(
            renders,
            ["big"],
            ["iso"],
            tmp_path / "x.png",
            tile=t,
            gap=g,
            label_height=lab,
        )
    )

    r, gr, b = tile_center(img, 0, 0, t, g, lab)
    assert 60 <= r <= 195 and 60 <= b <= 195 and gr <= 30, (r, gr, b)

    # A solid large render fills the tile with its color.
    solid(renders / "huge" / "iso.png", GREEN, (300, 300))
    img = open_rgb(
        make_sheet(
            renders,
            ["huge"],
            ["iso"],
            tmp_path / "y.png",
            tile=t,
            gap=g,
            label_height=lab,
        )
    )
    assert tile_center(img, 0, 0, t, g, lab) == GREEN


@pytest.mark.parametrize(
    ("size", "band"),
    [
        ((64, 32), "rows"),  # the ticket's case: same width, half height
        ((16, 8), "rows"),  # upscaled
        ((256, 128), "rows"),  # downscaled
        ((32, 64), "cols"),  # portrait: pillarboxed
    ],
)
def test_non_square_render_is_letterboxed(tmp_path, size, band):
    renders = tmp_path / "renders"
    color = (90, 200, 140)
    solid(renders / "w" / "hero.png", color, size)
    t, g, lab = 64, 8, 20

    img = open_rgb(
        make_sheet(
            renders,
            ["w"],
            ["hero"],
            tmp_path / "x.png",
            tile=t,
            gap=g,
            label_height=lab,
        )
    )

    x0, y0 = tile_origin(0, 0, t, g, lab)
    assert tile_center(img, 0, 0, t, g, lab) == color
    if band == "rows":
        # The render is 64x32 in the tile, rows 16..47.
        assert colors_in(img, (x0, y0, x0 + t, y0 + 1)) == {BACKGROUND}
        assert colors_in(img, (x0, y0 + t - 1, x0 + t, y0 + t)) == {BACKGROUND}
        assert img.getpixel((x0 + t // 2, y0 + 12)) == BACKGROUND
        assert img.getpixel((x0 + t // 2, y0 + 51)) == BACKGROUND
        assert img.getpixel((x0 + t // 2, y0 + 20)) == color
        assert img.getpixel((x0 + t // 2, y0 + 43)) == color
        assert img.getpixel((x0 + 1, y0 + t // 2)) == color
    else:
        assert colors_in(img, (x0, y0, x0 + 1, y0 + t)) == {BACKGROUND}
        assert colors_in(img, (x0 + t - 1, y0, x0 + t, y0 + t)) == {BACKGROUND}
        assert img.getpixel((x0 + 12, y0 + t // 2)) == BACKGROUND
        assert img.getpixel((x0 + 51, y0 + t // 2)) == BACKGROUND
        assert img.getpixel((x0 + 20, y0 + t // 2)) == color
        assert img.getpixel((x0 + 43, y0 + t // 2)) == color
        assert img.getpixel((x0 + t // 2, y0 + 1)) == color
    if size == (16, 8):
        # Upscaling a solid render with letterboxing adds no colors.
        assert colors_in(img, tile_box(0, 0, t, g, lab)) == {color, BACKGROUND}


def test_transparent_pixels_show_background(tmp_path):
    renders = tmp_path / "renders"
    solid(renders / "ghost" / "iso.png", (255, 0, 255, 0), mode="RGBA")
    t, g, lab = 64, 8, 20

    img = open_rgb(
        make_sheet(
            renders,
            ["ghost"],
            ["iso"],
            tmp_path / "x.png",
            tile=t,
            gap=g,
            label_height=lab,
        )
    )

    assert tile_center(img, 0, 0, t, g, lab) == BACKGROUND
    assert colors_in(img, tile_box(0, 0, t, g, lab)) == {BACKGROUND}

    # Half opaque, half transparent: the opaque half keeps its color.
    opaque, clear = (10, 220, 90, 255), (255, 255, 255, 0)
    rows = [[opaque if x < 4 else clear for x in range(8)] for y in range(8)]
    from_pixels(renders / "half" / "iso.png", rows, mode="RGBA")
    img = open_rgb(
        make_sheet(
            renders,
            ["half"],
            ["iso"],
            tmp_path / "y.png",
            tile=t,
            gap=g,
            label_height=lab,
        )
    )
    x0, y0 = tile_origin(0, 0, t, g, lab)
    assert img.getpixel((x0 + 16, y0 + 32)) == opaque[:3]
    assert img.getpixel((x0 + 48, y0 + 32)) == BACKGROUND
    assert colors_in(img, tile_box(0, 0, t, g, lab)) == {opaque[:3], BACKGROUND}


# --- Labels ----------------------------------------------------------------


def test_labels_are_drawn(tmp_path):
    renders = tmp_path / "renders"
    four_renders(renders)
    t, g, lab = 200, 10, 30

    img = open_rgb(
        make_sheet(
            renders,
            ["a", "b"],
            ["iso", "hero"],
            tmp_path / "x.png",
            tile=t,
            gap=g,
            label_height=lab,
        )
    )

    strips = {}
    for r in range(2):
        for c in range(2):
            box = strip_box(r, c, t, g, lab)
            assert colors_in(img, box) != {BACKGROUND}, (r, c)
            strips[(r, c)] = img.crop(box).tobytes()
            # The label does not spill over the render.
            assert len(colors_in(img, tile_box(r, c, t, g, lab))) == 1, (r, c)
    # "a / iso", "b / iso", "a / hero", "b / hero" are four different texts.
    assert len(set(strips.values())) == 4
    # The gap between columns stays background.
    gap_x = g + t + g // 2
    assert colors_in(img, (gap_x, 0, gap_x + 1, img.height)) == {BACKGROUND}


# --- Errors ----------------------------------------------------------------


def test_missing_render_exits_2_with_hint(tmp_path):
    renders = tmp_path / "renders"
    four_renders(renders)
    missing = renders / "b" / "hero.png"
    missing.unlink()
    out = tmp_path / "x.png"

    result = run_cli(
        ["a", "b", "--renders-dir", str(renders), "--out", str(out)], tmp_path
    )

    assert result.returncode == 2, (result.stdout, result.stderr)
    assert str(missing) in result.stderr
    assert "artlab render b" in result.stderr
    assert not out.exists()

    # A style with no directory at all names that style.
    result = run_cli(["a", "zed", "--renders-dir", str(renders)], tmp_path)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert str(renders / "zed") in result.stderr
    assert "artlab render zed" in result.stderr

    # The API raises MissingRender carrying the path and style.
    with pytest.raises(MissingRender) as info:
        make_sheet(renders, ["a", "b"], ["iso", "hero"], out)
    assert isinstance(info.value, FileNotFoundError)
    assert Path(info.value.path) == missing
    assert info.value.style == "b"
    assert not out.exists()


def test_no_renders_exits_2(tmp_path):
    renders = tmp_path / "renders"
    renders.mkdir()

    result = run_cli(["--renders-dir", str(renders)], tmp_path)

    assert result.returncode == 2, (result.stdout, result.stderr)
    assert not (renders / "contact-sheet.png").exists()
    with pytest.raises(NoRenders):
        make_sheet(renders, None, ["iso", "hero"], tmp_path / "x.png")

    # Only incomplete style dirs is still nothing to lay out.
    solid(renders / "half" / "iso.png", RED)
    result = run_cli(["--renders-dir", str(renders)], tmp_path)
    assert result.returncode == 2, (result.stdout, result.stderr)
    with pytest.raises(NoRenders):
        make_sheet(renders, None, ["iso", "hero"], tmp_path / "x.png")


def test_auto_discovery_skips_incomplete_dirs(tmp_path):
    renders = tmp_path / "renders"
    solid(renders / "zeta" / "iso.png", BLUE)
    solid(renders / "zeta" / "hero.png", YELLOW)
    solid(renders / "alpha" / "iso.png", RED)
    solid(renders / "alpha" / "hero.png", GREEN)
    solid(renders / "mid" / "iso.png", (77, 77, 200))  # no hero.png
    solid(renders / "contact-sheet.png", (1, 2, 3))  # a previous sheet, not a style
    t, g, lab = 64, 8, 20

    img = open_rgb(
        make_sheet(
            renders,
            None,
            ["iso", "hero"],
            tmp_path / "x.png",
            tile=t,
            gap=g,
            label_height=lab,
        )
    )
    assert img.size == sheet_size(2, 2, t, g, lab)
    assert tile_center(img, 0, 0, t, g, lab) == RED  # alpha before zeta
    assert tile_center(img, 0, 1, t, g, lab) == BLUE
    assert tile_center(img, 1, 1, t, g, lab) == YELLOW

    # Asking only for iso makes `mid` complete, in name order between the two.
    img = open_rgb(
        make_sheet(
            renders, None, ["iso"], tmp_path / "y.png", tile=t, gap=g, label_height=lab
        )
    )
    assert img.size == sheet_size(3, 1, t, g, lab)
    assert tile_center(img, 0, 1, t, g, lab) == (77, 77, 200)

    # The CLI default overwrites the old sheet in place and leaves it out.
    result = run_cli(["--renders-dir", str(renders), "--tile", "64"], tmp_path)
    assert result.returncode == 0, result.stderr
    img = open_rgb(renders / "contact-sheet.png")
    assert img.size == sheet_size(2, 2, 64, DEFAULT_GAP, DEFAULT_LABEL)
