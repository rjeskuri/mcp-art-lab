"""Shared pytest setup: skip tests marked `blender` when no Blender is found.

A bad ARTLAB_BLENDER makes `blender_skip_reason()` raise BlenderNotFound, which
fails the whole run loudly instead of silently skipping.
"""

import pytest

from artlab.blender import blender_skip_reason


def pytest_collection_modifyitems(config, items):
    blender_items = [item for item in items if item.get_closest_marker("blender")]
    if not blender_items:
        return
    reason = blender_skip_reason()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in blender_items:
        item.add_marker(skip)
