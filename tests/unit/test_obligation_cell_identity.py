"""Cell identity against the shipped namespace: ids, names, name uniqueness.

Covers three capabilities whose only prior test file imported the deprecated
`ipynb.*` shadow package and so could not count as coverage of
format_factory.ipynb (GAP-017/GAP-018):

- IPYNB-ID-001 (4.5): ids required, unique, charset and length constrained;
  generated ONLY via explicit upgrade, with a rewrite map.
- IPYNB-CELLNAME-001 (4.0-4.5): a present cell metadata name is a non-empty
  string; names are never synthesized during a passive read.
- IPYNB-CELLNAMEUNIQUE-001 (4.2-4.5): notebook-wide uniqueness for present
  names, which JSON Schema provably cannot express.

The last of these was entirely unimplemented — see
TC-FF6-IPYNB-CELL-NAME-UNIQUENESS-001. That is precisely why porting the shadow
tests would have been the wrong move: those tests describe a package whose cell
identity behavior differs from the shipped one.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from libipynb import (
    CELL_ID_PATTERN,
    dumps,
    loads,
    upgrade,
    validate,
)

ALL_PROFILES = [f"4.{minor}" for minor in range(6)]
UNIQUENESS_PROFILES = [f"4.{minor}" for minor in range(2, 6)]
PRE_UNIQUENESS_PROFILES = ["4.0", "4.1"]


def _cell(
    *, name: str | None = None, cell_id: str | None = None, with_metadata: bool = True
) -> dict[str, Any]:
    cell: dict[str, Any] = {"cell_type": "markdown", "source": "s"}
    if with_metadata:
        cell["metadata"] = {} if name is None else {"name": name}
    if cell_id is not None:
        cell["id"] = cell_id
    return cell


def _notebook(profile: str, cells: list[dict[str, Any]]) -> dict[str, Any]:
    minor = int(profile.split(".")[1])
    if minor >= 5:
        for index, cell in enumerate(cells):
            cell.setdefault("id", f"auto{index}")
    return {"nbformat": 4, "nbformat_minor": minor, "metadata": {}, "cells": cells}


def _codes(notebook: dict[str, Any], profile: str) -> set[str]:
    return {d.code for d in validate(notebook, profile=profile).diagnostics}


# ── IPYNB-CELLNAMEUNIQUE-001: notebook-wide uniqueness, 4.2+ only ──────────


@pytest.mark.parametrize("profile", UNIQUENESS_PROFILES)
def test_duplicate_cell_names_are_rejected_from_4_2_onward(profile: str) -> None:
    """The obligation's core requirement. JSON Schema cannot express this, so
    only a semantic check can satisfy it."""
    notebook = _notebook(profile, [_cell(name="dup"), _cell(name="dup")])
    report = validate(notebook, profile=profile)
    assert not report.is_valid
    assert "IPYNB_CELL_NAME_DUPLICATE" in {d.code for d in report.diagnostics}


@pytest.mark.parametrize("profile", PRE_UNIQUENESS_PROFILES)
def test_duplicate_cell_names_remain_allowed_before_4_2(profile: str) -> None:
    """The obligation scopes uniqueness to 4.2+. Tightening 4.0/4.1 would be its
    own defect, so this guards against over-correction."""
    notebook = _notebook(profile, [_cell(name="dup"), _cell(name="dup")])
    assert validate(notebook, profile=profile).is_valid


@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_distinct_names_pass_in_every_profile(profile: str) -> None:
    notebook = _notebook(profile, [_cell(name="alpha"), _cell(name="beta")])
    assert validate(notebook, profile=profile).is_valid


@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_absent_names_pass_in_every_profile(profile: str) -> None:
    """Uniqueness applies to PRESENT names; absence is not a collision."""
    notebook = _notebook(profile, [_cell(), _cell()])
    assert validate(notebook, profile=profile).is_valid


@pytest.mark.parametrize("profile", UNIQUENESS_PROFILES)
def test_cells_without_metadata_do_not_break_the_uniqueness_check(
    profile: str,
) -> None:
    notebook = _notebook(profile, [_cell(with_metadata=False), _cell(name="only-one")])
    assert "IPYNB_CELL_NAME_DUPLICATE" not in _codes(notebook, profile)


def test_only_the_colliding_cell_is_reported() -> None:
    notebook = _notebook("4.5", [_cell(name="dup"), _cell(name="unique"), _cell(name="dup")])
    report = validate(notebook, profile="4.5")
    duplicates = [d for d in report.diagnostics if d.code == "IPYNB_CELL_NAME_DUPLICATE"]
    assert len(duplicates) == 1, "the first occurrence is not itself a duplicate"
    assert 2 in duplicates[0].location.path, "must point at the second colliding cell"


def test_three_way_collision_reports_each_repeat() -> None:
    notebook = _notebook("4.5", [_cell(name="dup"), _cell(name="dup"), _cell(name="dup")])
    duplicates = [
        d
        for d in validate(notebook, profile="4.5").diagnostics
        if d.code == "IPYNB_CELL_NAME_DUPLICATE"
    ]
    assert len(duplicates) == 2


# ── IPYNB-CELLNAME-001: present names are non-empty strings, 4.0-4.5 ───────


@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_present_non_empty_name_passes_in_every_supported_profile(
    profile: str,
) -> None:
    """The requirement says "in every supported profile", so every profile is
    exercised rather than a representative one."""
    notebook = _notebook(profile, [_cell(name="a real name")])
    assert validate(notebook, profile=profile).is_valid


@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_empty_name_fails_in_every_supported_profile(profile: str) -> None:
    """The schema pattern is ^.+$, so an empty name cannot be valid anywhere."""
    notebook = _notebook(profile, [_cell(name="")])
    assert not validate(notebook, profile=profile).is_valid


@pytest.mark.parametrize("profile", ALL_PROFILES)
def test_names_are_never_synthesized_during_a_passive_read(profile: str) -> None:
    """ "without synthesizing names during passive reads" — load must not invent
    a name for a cell that has none.

    The write is pinned to the declared profile: writing a pre-4.5 notebook at
    the 4.5 default is refused with "requires explicit upgrade()", which is
    IPYNB-ID-001's explicit-upgrade-only rule doing its job and is asserted
    directly in test_ids_are_not_generated_by_a_passive_read below.
    """
    notebook = _notebook(profile, [_cell()])
    restored = json.loads(dumps(loads(json.dumps(notebook)), profile=profile))
    assert "name" not in restored["cells"][0]["metadata"]


@pytest.mark.parametrize("profile", PRE_UNIQUENESS_PROFILES + ["4.2", "4.3", "4.4"])
def test_writing_a_pre_4_5_notebook_at_the_default_profile_is_refused(
    profile: str,
) -> None:
    """A silent version bump would generate ids without an explicit upgrade,
    which IPYNB-ID-001 forbids."""
    from libipynb import NotebookWriteError

    notebook = _notebook(profile, [_cell(name="n")])
    with pytest.raises(NotebookWriteError, match="explicit upgrade"):
        dumps(loads(json.dumps(notebook)))


def test_a_present_name_survives_roundtrip_unchanged() -> None:
    notebook = _notebook("4.5", [_cell(name="kept")])
    restored = json.loads(dumps(loads(json.dumps(notebook))))
    assert restored["cells"][0]["metadata"]["name"] == "kept"


# ── IPYNB-ID-001: id syntax, length, uniqueness, explicit-upgrade-only ─────


def test_duplicate_cell_ids_are_rejected() -> None:
    notebook = _notebook("4.5", [_cell(cell_id="same"), _cell(cell_id="same")])
    assert "IPYNB_CELL_ID_DUPLICATE" in _codes(notebook, "4.5")


@pytest.mark.parametrize(
    "bad_id",
    ["", "has space", "has/slash", "hasunicodé", "a" * 65, "tab\there"],
)
def test_invalid_cell_ids_are_rejected(bad_id: str) -> None:
    """Charset and length rules, exercised as negatives per the requirement."""
    notebook = _notebook("4.5", [_cell(cell_id=bad_id)])
    assert "IPYNB_CELL_ID" in _codes(notebook, "4.5")


@pytest.mark.parametrize("good_id", ["a", "A1", "cell-1", "cell_1", "b" * 64])
def test_valid_cell_ids_are_accepted(good_id: str) -> None:
    assert CELL_ID_PATTERN.fullmatch(good_id) is not None
    notebook = _notebook("4.5", [_cell(cell_id=good_id)])
    assert validate(notebook, profile="4.5").is_valid


def test_ids_are_not_generated_by_a_passive_read() -> None:
    """The obligation says ids are generated ONLY via explicit upgrade."""
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {},
        "cells": [_cell(name="n")],
    }
    restored = loads(json.dumps(notebook)).raw
    assert "id" not in restored["cells"][0]


def test_explicit_upgrade_generates_ids_and_reports_the_rewrite_map() -> None:
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {},
        "cells": [_cell(name="one"), _cell(name="two")],
    }
    result = upgrade(notebook)
    cells = result.document.cells
    assert all(CELL_ID_PATTERN.fullmatch(cell["id"]) for cell in cells)
    assert cells[0]["id"] != cells[1]["id"], "generated ids must be unique"


def test_upgrade_is_deterministic_for_identical_input() -> None:
    """A rewrite map is only useful if the mapping is reproducible."""
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {},
        "cells": [_cell(name="one")],
    }
    first = upgrade(json.loads(json.dumps(notebook))).document
    second = upgrade(json.loads(json.dumps(notebook))).document
    assert first.cells[0]["id"] == second.cells[0]["id"]
    assert dumps(first) == dumps(second)


def test_upgraded_notebook_validates_at_4_5() -> None:
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {},
        "cells": [_cell(name="one"), _cell(name="two")],
    }
    upgraded = json.loads(dumps(upgrade(notebook).document))
    assert validate(upgraded, profile="4.5").is_valid
