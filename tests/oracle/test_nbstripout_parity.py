"""LIBIPYNB-P2 Gate G8: real oracle comparison against installed `nbstripout`.

This is the sub-task every P2 status note in plans/full-parity-plan.md
explicitly flagged as skipped "because no oracle tools are installed on
this machine" -- now that `nbstripout` is installed (`libipynb[oracle]`),
this file is the actual byte-for-byte comparison, not just a description
of intended behavior.

Two real, genuine divergences were found by actually running real
nbstripout (not assumed, not guessed) -- both documented here rather than
silently normalized away or papered over:

1. **Cell IDs.** nbstripout's default behavior REGENERATES cell IDs
   (sequential "0", "1", ... unless `--keep-id` is passed), because it
   treats Jupyter's own ephemeral per-kernel-run IDs as diff noise.
   libipynb's cell IDs are deliberately content-derived and stable, and
   `normalize` never touches them under any flag. Intentional design
   difference, not a bug -- excluded from the field-level equivalence
   comparison below and separately proven/documented in its own test.

2. **`source`/output-text serialization form.** nbstripout writes notebooks
   through nbformat's own writer, which canonicalizes multi-line text
   fields (`source`, stream `text`, MIME `data` text values) from a plain
   string into a list-of-lines. libipynb's `dump()`/`normalize` preserves
   whichever representation was originally read. Both are valid, equivalent
   nbformat per the spec (a reader must accept either), but the literal
   bytes written to disk differ. The stripping-behavior comparison below
   normalizes both sides' text fields before comparing (that comparison is
   about *which fields get removed*, not *how surviving text is
   serialized*) -- the serialization difference itself has its own,
   separate, explicit test rather than being silently absorbed into the
   normalization helper.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from libipynb import load
from libipynb.model.cleanup import CleanupPolicy, cleanup

_NBSTRIPOUT_DEFAULT_NOTEBOOK_METADATA_KEYS = frozenset({"signature", "widgets"})
_NBSTRIPOUT_DEFAULT_CELL_METADATA_KEYS = frozenset(
    {"ExecuteTime", "collapsed", "execution", "heading_collapsed", "hidden", "scrolled"}
)


def _fixture_notebook() -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "signature": "sha256:deadbeef",
            "widgets": {"state": {"a": 1}},
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "custom_notebook_key": "keep me",
        },
        "cells": [
            {
                "cell_type": "code",
                "id": "alpha",
                "metadata": {
                    "ExecuteTime": {"start_time": "2026-01-01T00:00:00", "end_time": "x"},
                    "collapsed": True,
                    "custom_cell_key": "keep me too",
                },
                "execution_count": 7,
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": ["hello\n"]},
                    {
                        "output_type": "execute_result",
                        "execution_count": 7,
                        "data": {"text/plain": ["7"]},
                        "metadata": {},
                    },
                ],
                "source": "print('hello')\n7",
            },
            {
                "cell_type": "markdown",
                "id": "beta",
                "metadata": {},
                "source": "# A heading",
            },
        ],
    }


def _run_real_nbstripout(notebook: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    path = tmp_path / "nbstripout_target.ipynb"
    path.write_text(json.dumps(notebook), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "nbstripout", str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(path.read_text(encoding="utf-8"))


def _run_libipynb_normalize(notebook: dict[str, Any]) -> dict[str, Any]:
    document = load(json.dumps(notebook), mode="preservation")
    cleanup(
        document,
        policy=CleanupPolicy(
            notebook_metadata_keys=_NBSTRIPOUT_DEFAULT_NOTEBOOK_METADATA_KEYS,
            cell_metadata_keys=_NBSTRIPOUT_DEFAULT_CELL_METADATA_KEYS,
        ),
    )
    return document.raw


def _as_text(value: Any) -> Any:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "".join(value)
    return value


def _normalize_text_fields(node: Any) -> Any:
    """Recursively join any list-of-lines text field back into a single
    string, so the two tools' differing source/output-text serialization
    convention (documented in this module's docstring, divergence #2)
    doesn't mask a real difference elsewhere. Only ever changes str<->list
    representation, never removes or reorders a key."""
    if isinstance(node, dict):
        return {key: _normalize_text_fields(_as_text(value)) for key, value in node.items()}
    if isinstance(node, list):
        return [_normalize_text_fields(item) for item in node]
    return node


def _strip_ids(notebook: dict[str, Any]) -> dict[str, Any]:
    """Remove the one documented, intentional divergence (cell IDs) before
    comparing everything else field-for-field."""
    clone = json.loads(json.dumps(notebook))
    for cell in clone.get("cells", []):
        cell.pop("id", None)
    return clone


def _for_comparison(notebook: dict[str, Any]) -> dict[str, Any]:
    """Both documented divergences removed: this is what "the same set of
    fields survived stripping, with the same content" means once the two
    tools' unrelated formatting choices are set aside."""
    return _normalize_text_fields(_strip_ids(notebook))


def test_default_stripping_matches_real_nbstripout_except_two_documented_divergences(
    nbstripout_available, tmp_path: Path
) -> None:
    fixture = _fixture_notebook()
    real_result = _run_real_nbstripout(fixture, tmp_path)
    libipynb_result = _run_libipynb_normalize(fixture)

    assert _for_comparison(real_result) == _for_comparison(libipynb_result), (
        "libipynb's normalize (nbstripout-compatible policy) diverges from real "
        "nbstripout on a field other than the two documented divergences "
        "(cell ids, source/text serialization form)"
    )


def test_source_serialization_form_is_the_second_documented_divergence(
    nbstripout_available, tmp_path: Path
) -> None:
    """Divergence #2 from this module's docstring, proven directly: real
    nbstripout's underlying nbformat writer canonicalizes `source` to a
    list-of-lines; libipynb's writer preserves the original representation.
    Both are valid nbformat -- this documents the literal-bytes difference,
    it does not claim either is wrong."""
    fixture = _fixture_notebook()
    real_result = _run_real_nbstripout(fixture, tmp_path)
    libipynb_result = _run_libipynb_normalize(fixture)

    assert isinstance(real_result["cells"][1]["source"], list), (
        "if real nbstripout ever stops canonicalizing source to a list, this "
        "test and the divergence note in this module's docstring need updating"
    )
    assert isinstance(libipynb_result["cells"][1]["source"], str), (
        "libipynb's normalize must preserve source's original representation, "
        "not silently rewrite it to match nbstripout's serialization choice"
    )
    # Semantically identical once normalized, per the nbformat spec's own
    # equivalence of the two representations:
    assert _as_text(real_result["cells"][1]["source"]) == libipynb_result["cells"][1]["source"]


def test_cell_id_handling_is_the_one_documented_divergence(
    nbstripout_available, tmp_path: Path
) -> None:
    fixture = _fixture_notebook()
    real_result = _run_real_nbstripout(fixture, tmp_path)
    libipynb_result = _run_libipynb_normalize(fixture)

    real_ids = [cell.get("id") for cell in real_result["cells"]]
    libipynb_ids = [cell.get("id") for cell in libipynb_result["cells"]]

    assert real_ids != ["alpha", "beta"], (
        "if real nbstripout ever stops regenerating cell ids by default, this "
        "test (and the divergence note in this module's docstring and in "
        "README.md's comparison table) needs updating, not silently left stale"
    )
    assert libipynb_ids == ["alpha", "beta"], (
        "libipynb's normalize must never touch cell ids -- they are the "
        "content-derived stability guarantee the rest of the diff/merge engine "
        "depends on"
    )


def test_keep_output_matches_real_nbstripout(nbstripout_available, tmp_path: Path) -> None:
    fixture = _fixture_notebook()
    path = tmp_path / "keep_output.ipynb"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", "nbstripout", "--keep-output", str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    real_result = json.loads(path.read_text(encoding="utf-8"))

    document = load(json.dumps(fixture), mode="preservation")
    cleanup(
        document,
        policy=CleanupPolicy(
            notebook_metadata_keys=_NBSTRIPOUT_DEFAULT_NOTEBOOK_METADATA_KEYS,
            cell_metadata_keys=_NBSTRIPOUT_DEFAULT_CELL_METADATA_KEYS,
            output_types=frozenset(),
        ),
    )
    libipynb_result = document.raw

    assert real_result["cells"][0]["outputs"] != []
    assert libipynb_result["cells"][0]["outputs"] != []
    assert _for_comparison(real_result) == _for_comparison(libipynb_result)
