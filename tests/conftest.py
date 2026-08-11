"""Shared fixtures for IPYNB installed-namespace proofs."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import pytest


def _is_editable_install(dist: importlib.metadata.Distribution) -> bool:
    """Detect an editable install via PEP 660 direct_url.json, matching the
    convention tools/assurance/verify_package_install.py already uses."""
    try:
        direct_url_text = dist.read_text("direct_url.json")
    except FileNotFoundError:
        direct_url_text = None
    if direct_url_text:
        data = json.loads(direct_url_text)
        if data.get("dir_info", {}).get("editable") or data.get("editable"):
            return True
    dist_path = getattr(dist, "_path", None)
    if dist_path is not None:
        site_packages = Path(dist_path).parent
        if list(site_packages.glob("__editable__*ipynb*.pth")):
            return True
    return False


@pytest.fixture
def is_editable_install():
    return _is_editable_install
