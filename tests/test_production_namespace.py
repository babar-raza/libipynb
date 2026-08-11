"""Characterization and package-chassis checks for the production namespace."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import io
import json
from pathlib import Path

import pytest

from libipynb import (
    IpynbDocument,
    dump,
    dumps,
    load,
    loads,
    probe,
    upgrade,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SAMPLE = FIXTURES / "valid" / "minimal.ipynb"


def test_implicit_namespace_importable(is_editable_install) -> None:
    spec = importlib.util.find_spec("libipynb")
    assert spec is not None
    assert spec.origin is not None
    dist = importlib.metadata.distribution("libipynb")
    source_root = str((ROOT / "src").resolve())
    resolved_origin = str(Path(spec.origin).resolve())
    if is_editable_install(dist):
        assert source_root in resolved_origin
    else:
        assert "site-packages" in resolved_origin.lower()
        assert source_root not in resolved_origin


def test_common_lifecycle_and_unknown_member_preservation(tmp_path: Path) -> None:
    source = json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 6,
            "metadata": {"vendor": {"enabled": True}},
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "known-id",
                    "metadata": {},
                    "source": "# title",
                    "vendor_cell": {"retained": 1},
                }
            ],
            "vendor_root": ["retained"],
        }
    )
    result = probe(source)
    assert result.matched
    assert result.profile == "nbformat-4.6"

    document = loads(source, mode="preservation")
    assert isinstance(document, IpynbDocument)
    assert validate(document).is_valid
    assert document.raw["vendor_root"] == ["retained"]
    assert document.cells[0]["vendor_cell"] == {"retained": 1}

    destination = tmp_path / "roundtrip.ipynb"
    dump(document, destination, profile="declared")
    reloaded = load(destination, mode="preservation")
    assert reloaded.raw["vendor_root"] == ["retained"]
    assert reloaded.cells[0]["vendor_cell"] == {"retained": 1}


def test_load_from_a_readable_text_stream() -> None:
    """"Provide load from ... a readable stream" -- Source is typed to accept
    anything with a str-returning read(), not only bytes/str/path, but no
    existing test constructed an actual stream object until this one."""
    source = json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [],
        }
    )
    document = load(io.StringIO(source))

    assert isinstance(document, IpynbDocument)
    assert document.declared_version.as_tuple() == (4, 5)


def test_dump_writes_to_a_writable_text_stream() -> None:
    """"Provide save to ... a writable stream" -- Destination is typed to
    accept anything with a str-accepting write(), not only a path."""
    document = load(
        json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []})
    )
    buffer = io.StringIO()

    dump(document, buffer)

    reloaded = load(io.StringIO(buffer.getvalue()))
    assert reloaded.declared_version.as_tuple() == (4, 5)


def test_deterministic_cell_ids_are_created_only_by_explicit_upgrade() -> None:
    source = json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 4,
            "metadata": {},
            "cells": [{"cell_type": "markdown", "metadata": {}, "source": "same"}],
        }
    )
    first = load(source).raw
    second = load(source).raw
    assert "id" not in first["cells"][0]
    assert "id" not in second["cells"][0]

    first_upgrade = upgrade(first).document
    second_upgrade = upgrade(second).document
    assert first_upgrade.cells[0]["id"] == second_upgrade.cells[0]["id"]
    assert dumps(first_upgrade) == dumps(second_upgrade)


def test_default_writer_emits_45_and_rejects_nonfinite_json() -> None:
    document = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "code",
                "id": "nan-cell",
                "metadata": {},
                "source": "",
                "outputs": [],
                "execution_count": None,
            }
        ],
    }
    document["metadata"]["nonfinite"] = float("nan")
    with pytest.raises(Exception, match="serialize"):
        dumps(document)

    document["metadata"].pop("nonfinite")
    serialized = json.loads(dumps(document))
    assert (serialized["nbformat"], serialized["nbformat_minor"]) == (4, 5)
    assert serialized["cells"][0]["id"] == "nan-cell"


def test_package_chassis_and_python_policy() -> None:
    package_root = ROOT / "src" / "libipynb"
    for layer in (
        "model",
        "codec/reader",
        "codec/writer",
        "validation",
        "security",
        "adapters",
        "analytics",
        "cli",
    ):
        assert (package_root / layer).is_dir()
    assert (package_root / "py.typed").is_file()

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.11"' in pyproject


def test_repository_fixture_is_loadable() -> None:
    document = load(SAMPLE, mode="preservation")
    assert document.nbformat == 4
    assert document.cell_count >= 0
