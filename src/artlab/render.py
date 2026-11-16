"""Render one style: run `inblender/runner.py` in Blender on its `build.py`.

The runner builds the test scene, applies the style and writes, under
`<renders_dir>/<name>/`, `manifest.json`, `scene.blend` when asked, and one
`<camera>.png` per requested camera.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from artlab.blender import run_blender
from artlab.styles import discover

# Run in Blender by path: host code never imports artlab.inblender.
RUNNER = Path(__file__).resolve().parent / "inblender" / "runner.py"
# Mirrors artlab.inblender.cameras.CAMERA_ORDER: the primary view first.
CAMERA_ORDER = ("iso", "hero")
MIN_SIZE = 4  # Blender clamps a smaller render resolution up to this


class UnknownStyle(LookupError):
    """Style names not in the styles dir; the message lists the ones that are."""

    def __init__(
        self, names: Sequence[str], styles_dir: Path, available: Iterable[str]
    ) -> None:
        self.names = list(names)
        self.available = list(available)
        label = "style" if len(self.names) == 1 else "styles"
        unknown = ", ".join(repr(name) for name in self.names)
        listing = (
            f"available: {', '.join(self.available)}"
            if self.available
            else "it has no styles"
        )
        super().__init__(f"unknown {label} {unknown} in {styles_dir}; {listing}")


@dataclass(frozen=True)
class RenderResult:
    """What a render wrote: images by camera, the manifest and the `.blend` if saved."""

    images: dict[str, Path]
    manifest: Path
    blend: Path | None


def render_style(
    name: str,
    *,
    styles_dir: Path,
    renders_dir: Path,
    cameras: Sequence[str] = CAMERA_ORDER,
    size: int = 1024,
    render: bool = True,
    save_blend: bool = False,
) -> RenderResult:
    """Build the test scene in style `name` and render `cameras` at `size` x `size`.

    Cameras render in `CAMERA_ORDER` whatever order they are given in. Raises
    UnknownStyle before looking for Blender, then BlenderNotFound, or BlenderError
    when the style raises, breaks the content rules or Blender fails.
    """
    styles = discover(styles_dir)
    if name not in styles:
        raise UnknownStyle([name], styles_dir, styles)
    unknown = [key for key in cameras if key not in CAMERA_ORDER]
    if unknown:
        raise ValueError(f"unknown cameras {unknown}; choose from {CAMERA_ORDER}")
    if size < MIN_SIZE:
        raise ValueError(f"size must be at least {MIN_SIZE}, got {size}")

    keys = [key for key in CAMERA_ORDER if key in cameras] if render else []
    out = Path(renders_dir) / name
    args = [name, str(styles[name].resolve()), str(out.resolve()), "--size", str(size)]
    for key in keys:
        args += ["--camera", key]
    if save_blend:
        args.append("--save-blend")
    run_blender(RUNNER, args)
    return RenderResult(
        images={key: out / f"{key}.png" for key in keys},
        manifest=out / "manifest.json",
        blend=out / "scene.blend" if save_blend else None,
    )
