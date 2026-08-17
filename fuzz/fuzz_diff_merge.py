"""Fuzz diff_notebooks()/merge_notebooks() -- structural diff and 3-way merge.

Structure-aware: builds three related-but-diverging notebooks (base, ours,
theirs) sharing some cell IDs and diverging on others, since the
interesting code here (LIS-based move detection, conflict classification)
is reached by having *some* structural overlap, not by three unrelated
random documents.
"""

from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from libipynb import NotebookError
    from libipynb.model import NotebookDocument, diff_notebooks, merge_notebooks

_CELL_IDS = ("a", "b", "c", "d", "e")


def _fuzz_string(fdp: atheris.FuzzedDataProvider, max_len: int = 100) -> str:
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, max_len))


def _fuzz_cells(fdp: atheris.FuzzedDataProvider) -> list[dict]:
    count = fdp.ConsumeIntInRange(0, len(_CELL_IDS))
    ids = list(_CELL_IDS[:count])
    # Occasionally permute order to exercise move detection.
    if fdp.ConsumeBool() and len(ids) > 1:
        ids.reverse()
    cells = []
    for cid in ids:
        if fdp.ConsumeBool():
            continue  # Occasionally drop a cell (simulates deletion).
        cells.append(
            {
                "cell_type": "code" if fdp.ConsumeBool() else "markdown",
                "id": cid,
                "metadata": {},
                "source": _fuzz_string(fdp, 200),
                "execution_count": None,
                "outputs": [],
            }
        )
    return cells


def _document(fdp: atheris.FuzzedDataProvider) -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": _fuzz_cells(fdp),
        }
    )


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    base = _document(fdp)
    ours = _document(fdp)
    theirs = _document(fdp)

    try:
        diff_notebooks(base, ours)
        merge_notebooks(base, ours, theirs)
    except NotebookError:
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
