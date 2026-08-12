"""Compare libipynb load/dump against nbformat read/write.

These tests verify structural equivalence — cell types, source content, and
output structure — rather than byte-for-byte identity.  Intentional differences
are documented inline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat", reason="nbformat is not installed")

import libipynb

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _libipynb_cells(path: Path) -> list[dict]:
    """Load with libipynb and return the raw cell dicts."""
    doc = libipynb.load(str(path), mode="recovery")
    return doc.raw.get("cells", [])


def _nbformat_cells(path: Path) -> list[dict]:
    """Load with nbformat and return the raw cell dicts."""
    with open(path, encoding="utf-8") as fh:
        nb = nbformat.read(fh, as_version=4)
    return list(nb.get("cells", []))


def _normalize_source(source) -> str:
    """Collapse source to a single string for comparison.

    Both libraries may store source as a string or list-of-strings;
    normalizing avoids false negatives from representation differences.
    """
    if isinstance(source, list):
        return "".join(source)
    return source if isinstance(source, str) else str(source)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadProducesSameStructure:
    """Cell count, cell types, and source content must agree."""

    def test_load_produces_same_structure_as_nbformat(self, valid_fixture_path: Path):
        lib_cells = _libipynb_cells(valid_fixture_path)
        nb_cells = _nbformat_cells(valid_fixture_path)

        assert len(lib_cells) == len(nb_cells), (
            f"cell count mismatch: libipynb={len(lib_cells)}, nbformat={len(nb_cells)}"
        )

        for idx, (lc, nc) in enumerate(zip(lib_cells, nb_cells)):
            assert lc.get("cell_type") == nc.get("cell_type"), f"cell {idx} type mismatch"

            lib_src = _normalize_source(lc.get("source", ""))
            nb_src = _normalize_source(nc.get("source", ""))
            assert lib_src == nb_src, f"cell {idx} source mismatch"

            # Output count should match for code cells
            if lc.get("cell_type") == "code":
                lib_outputs = lc.get("outputs", [])
                nb_outputs = nc.get("outputs", [])
                assert len(lib_outputs) == len(nb_outputs), f"cell {idx} output count mismatch"
                for oi, (lo, no) in enumerate(zip(lib_outputs, nb_outputs)):
                    assert lo.get("output_type") == no.get("output_type"), (
                        f"cell {idx} output {oi} type mismatch"
                    )


class TestWriteRoundtripMatchesNbformat:
    """Load with libipynb, dump, reload — compare against nbformat."""

    def test_write_roundtrip_matches_nbformat(self, valid_fixture_path: Path):
        # Round-trip through libipynb
        doc = libipynb.load(str(valid_fixture_path), mode="recovery")
        serialized = libipynb.dumps(doc, profile="declared")
        reloaded = libipynb.load(serialized, mode="recovery")

        # Load same file with nbformat for reference
        nb_cells = _nbformat_cells(valid_fixture_path)
        rt_cells = reloaded.raw.get("cells", [])

        assert len(rt_cells) == len(nb_cells), (
            f"round-trip cell count mismatch: libipynb={len(rt_cells)}, nbformat={len(nb_cells)}"
        )

        for idx, (rc, nc) in enumerate(zip(rt_cells, nb_cells)):
            assert rc.get("cell_type") == nc.get("cell_type"), (
                f"cell {idx} type diverged after round-trip"
            )

            rt_src = _normalize_source(rc.get("source", ""))
            nb_src = _normalize_source(nc.get("source", ""))
            assert rt_src == nb_src, f"cell {idx} source diverged after round-trip"


class TestCorpusNotebooksLoadIdentically:
    """Corpus fixtures should load identically under both libraries."""

    def test_corpus_notebooks_load_identically(self, corpus_fixture_path: Path):
        lib_cells = _libipynb_cells(corpus_fixture_path)
        nb_cells = _nbformat_cells(corpus_fixture_path)

        assert len(lib_cells) == len(nb_cells), (
            f"corpus cell count mismatch: libipynb={len(lib_cells)}, nbformat={len(nb_cells)}"
        )

        for idx, (lc, nc) in enumerate(zip(lib_cells, nb_cells)):
            assert lc.get("cell_type") == nc.get("cell_type"), f"corpus cell {idx} type mismatch"

            lib_src = _normalize_source(lc.get("source", ""))
            nb_src = _normalize_source(nc.get("source", ""))
            assert lib_src == nb_src, f"corpus cell {idx} source mismatch"

            # Compare output types for code cells
            if lc.get("cell_type") == "code":
                lib_outputs = lc.get("outputs", [])
                nb_outputs = nc.get("outputs", [])
                assert len(lib_outputs) == len(nb_outputs), (
                    f"corpus cell {idx} output count mismatch"
                )
                for oi, (lo, no) in enumerate(zip(lib_outputs, nb_outputs)):
                    assert lo.get("output_type") == no.get("output_type"), (
                        f"corpus cell {idx} output {oi} type mismatch"
                    )
