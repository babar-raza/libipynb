"""Executed proof for forward-compatible nbformat 4.x minor versions.

The factory's production profile remains nbformat 4.0 through 4.5.  A future
minor is therefore preservation-only: strict mode must reject it, while the
explicit ``declared`` writer profile must carry its version and unknown
dictionary constructs without claiming that the factory understands them.
"""

from __future__ import annotations

import json

import pytest

import nbformat
from libipynb import IpynbParseError, IpynbWriteError, dumps, loads, upgrade


def _future_minor_notebook() -> dict[str, object]:
    return {
        "nbformat": 4,
        "nbformat_minor": 6,
        "metadata": {"vendor.example": {"revision": 7}},
        "cells": [
            {
                "cell_type": "vendor_cell",
                "id": "future-cell",
                "metadata": {"vendor": True},
                "source": "future cell payload",
                "vendor_payload": {"ordered": [1, 2, 3]},
            },
            {
                "cell_type": "code",
                "id": "future-output",
                "metadata": {},
                "source": "display_future()",
                "execution_count": None,
                "outputs": [
                    {
                        "output_type": "vendor_output",
                        "vendor_payload": {"mime": "application/vnd.example+json"},
                    }
                ],
            },
        ],
        "vendor_root": {"preserve": "exactly"},
    }


def test_future_minor_unknown_constructs_match_official_preservation() -> None:
    source = _future_minor_notebook()
    encoded = json.dumps(source, ensure_ascii=False)

    official = nbformat.reads(encoded, as_version=nbformat.NO_CONVERT)
    nbformat.validate(official)
    official_reloaded = nbformat.reads(
        nbformat.writes(official, version=nbformat.NO_CONVERT),
        as_version=nbformat.NO_CONVERT,
    )

    factory = loads(encoded, mode="preservation")
    factory_reloaded = loads(dumps(factory, profile="declared"), mode="preservation")
    official_serialized = json.loads(nbformat.writes(official_reloaded))

    assert factory.raw == source
    assert factory_reloaded.raw == source
    assert (
        official_serialized["nbformat"],
        official_serialized["nbformat_minor"],
    ) == (4, 6)
    assert official_serialized["vendor_root"] == source["vendor_root"]
    assert official_serialized["cells"][0]["vendor_payload"] == {
        "ordered": [1, 2, 3]
    }
    assert official_serialized["cells"][1]["outputs"][0]["vendor_payload"] == {
        "mime": "application/vnd.example+json"
    }


def test_future_minor_remains_outside_strict_supported_profile() -> None:
    encoded = json.dumps(_future_minor_notebook())

    with pytest.raises(IpynbParseError, match=r"supports nbformat 4\.0 through 4\.5"):
        loads(encoded, mode="strict")


def test_default_writer_profile_requires_explicit_upgrade_to_45() -> None:
    current = {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {},
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "default profile",
            }
        ],
    }

    with pytest.raises(IpynbWriteError, match="explicit upgrade"):
        dumps(current)

    serialized = json.loads(dumps(upgrade(current, target="4.5").document))
    assert (serialized["nbformat"], serialized["nbformat_minor"]) == (4, 5)
    assert isinstance(serialized["cells"][0]["id"], str)
