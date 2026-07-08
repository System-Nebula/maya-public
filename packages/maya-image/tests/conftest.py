"""Shared fixtures for maya-image unit tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _arena_workflows_runnable_without_comfy_models():
    """Arena pool tests use synthetic graphs; skip on-disk Comfy weight checks."""
    with patch("maya_image.comfy_assets.assets_ready_for_graph", return_value=True):
        yield
