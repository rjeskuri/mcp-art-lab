"""Style discovery: a style is `<styles_dir>/<name>/build.py` with `build(scene)`."""

import re
from pathlib import Path

NAME = re.compile(r"[a-z][a-z0-9_-]*")


def discover(styles_dir: Path) -> dict[str, Path]:
    """Map each style name to its `build.py`, by name; `{}` if the dir is missing.

    A style is a subdirectory whose name matches `^[a-z][a-z0-9_-]*$` and that
    holds a `build.py`; anything else in the dir is ignored.
    """
    styles_dir = Path(styles_dir)
    if not styles_dir.is_dir():
        return {}
    found = {
        entry.name: entry / "build.py"
        for entry in styles_dir.iterdir()
        if NAME.fullmatch(entry.name) and (entry / "build.py").is_file()
    }
    return dict(sorted(found.items()))
