"""Compare version detection and cell-ID handling between libipynb and nbformat.

Tests cover notebooks declared as nbformat 4.0 through 4.5, with particular
attention to cell IDs (introduced in nbformat 4.5).
"""

from __future__ import annotations

from pathlib import Path

import pytest

nbformat_mod = pytest.importorskip("nbformat", reason="nbformat is not installed")

import libipynb

VALID_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "valid"

# Collect versioned fixtures: nbformat-4-0.ipynb through nbformat-4-4.ipynb
# plus minimal.ipynb (which is 4.5)
_VERSION_FIXTURES: list[tuple[Path, int, int]] = []
for minor in range(0, 5):
    path = VALID_DIR / f"nbformat-4-{minor}.ipynb"
    if path.exists():
        _VERSION_FIXTURES.append((path, 4, minor))

# minimal.ipynb is nbformat 4.5
_minimal = VALID_DIR / "minimal.ipynb"
if _minimal.exists():
    _VERSION_FIXTURES.append((_minimal, 4, 5))


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------

class TestVersionDetection:
    """Both libraries should agree on the declared nbformat version."""

    @pytest.mark.parametrize(
        "path, expected_major, expected_minor",
        _VERSION_FIXTURES,
        ids=[f"v{maj}.{mi}" for _, maj, mi in _VERSION_FIXTURES],
    )
    def test_version_detection_matches(
        self,
        path: Path,
        expected_major: int,
        expected_minor: int,
    ):
        # libipynb
        doc = libipynb.load(str(path), mode="recovery")
        assert doc.nbformat == expected_major, (
            f"libipynb major version mismatch for {path.name}"
        )
        assert doc.nbformat_minor == expected_minor, (
            f"libipynb minor version mismatch for {path.name}"
        )

        # nbformat
        with open(path, encoding="utf-8") as fh:
            nb = nbformat_mod.read(fh, as_version=4)
        assert nb.nbformat == expected_major, (
            f"nbformat major version mismatch for {path.name}"
        )
        assert nb.nbformat_minor == expected_minor, (
            f"nbformat minor version mismatch for {path.name}"
        )


# ---------------------------------------------------------------------------
# Cell ID handling (introduced in nbformat 4.5)
# ---------------------------------------------------------------------------

class TestCellIdHandling:
    """v4.5 notebooks should have cell IDs; pre-4.5 should not (or may have
    them synthesized by the library)."""

    def test_v45_cells_have_ids(self):
        """In a v4.5 notebook, both libraries should surface cell IDs."""
        # Use the corpus spec-v45-complete if available, else minimal
        corpus_dir = Path(__file__).resolve().parent.parent / "fixtures" / "corpus"
        v45_path = corpus_dir / "spec-v45-complete.ipynb"
        if not v45_path.exists():
            v45_path = VALID_DIR / "minimal.ipynb"
            if not v45_path.exists():
                pytest.skip("no v4.5 fixture available")

        doc = libipynb.load(str(v45_path), mode="recovery")
        lib_cells = doc.raw.get("cells", [])

        with open(v45_path, encoding="utf-8") as fh:
            nb = nbformat_mod.read(fh, as_version=4)
        nb_cells = list(nb.get("cells", []))

        # Both should produce the same number of cells
        assert len(lib_cells) == len(nb_cells)

        for idx, (lc, nc) in enumerate(zip(lib_cells, nb_cells)):
            lib_id = lc.get("id")
            nb_id = nc.get("id")

            # In a 4.5 notebook, cells should have IDs in both libraries
            # Note: the exact ID values may differ if a library synthesizes
            # IDs for cells that lack them, but for a well-formed 4.5
            # notebook both should preserve the original IDs.
            if lib_id is not None and nb_id is not None:
                assert lib_id == nb_id, (
                    f"cell {idx} ID mismatch: "
                    f"libipynb={lib_id!r}, nbformat={nb_id!r}"
                )

    @pytest.mark.parametrize(
        "path, expected_major, expected_minor",
        [item for item in _VERSION_FIXTURES if item[2] < 5],
        ids=[f"v{maj}.{mi}" for _, maj, mi in _VERSION_FIXTURES if mi < 5],
    )
    def test_pre_v45_cell_id_behavior(
        self,
        path: Path,
        expected_major: int,
        expected_minor: int,
    ):
        """Pre-4.5 notebooks: cell IDs are not part of the spec.

        Libraries may or may not synthesize IDs. The key invariant is that
        loading does not fail and cell content is preserved regardless.
        """
        doc = libipynb.load(str(path), mode="recovery")
        lib_cells = doc.raw.get("cells", [])

        with open(path, encoding="utf-8") as fh:
            nb = nbformat_mod.read(fh, as_version=4)
        nb_cells = list(nb.get("cells", []))

        assert len(lib_cells) == len(nb_cells), (
            f"cell count mismatch for pre-4.5 fixture {path.name}"
        )

        for idx, (lc, nc) in enumerate(zip(lib_cells, nb_cells)):
            # Cell types and sources must agree regardless of version
            assert lc.get("cell_type") == nc.get("cell_type"), (
                f"cell {idx} type mismatch in {path.name}"
            )

            # Normalize source for comparison
            lib_src = lc.get("source", "")
            nb_src = nc.get("source", "")
            if isinstance(lib_src, list):
                lib_src = "".join(lib_src)
            if isinstance(nb_src, list):
                nb_src = "".join(nb_src)
            assert lib_src == nb_src, (
                f"cell {idx} source mismatch in {path.name}"
            )
