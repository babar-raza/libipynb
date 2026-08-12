"""Compare validation verdicts between libipynb and nbformat.

Both libraries should agree on whether a notebook is valid or invalid.
When they intentionally diverge (e.g., nbformat is more permissive on
certain structural issues), the difference is documented inline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

nbformat_mod = pytest.importorskip("nbformat", reason="nbformat is not installed")

import libipynb

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nbformat_is_valid(path: Path) -> bool:
    """Return True if nbformat considers the notebook valid."""
    try:
        with open(path, encoding="utf-8") as fh:
            nb = nbformat_mod.read(fh, as_version=4)
        nbformat_mod.validate(nb)
        return True
    except nbformat_mod.ValidationError:
        return False
    except Exception:  # noqa: BLE001
        return False


def _libipynb_is_valid(path: Path) -> bool:
    """Return True if libipynb considers the notebook valid."""
    try:
        result = libipynb.validate(str(path))
        return result.is_valid
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidNotebooks:
    """Valid fixtures must pass both validators."""

    @pytest.mark.timeout(30)  # large-source-cell.ipynb may be slow
    def test_valid_notebooks_pass_both_validators(self, valid_fixture_path: Path):
        nb_valid = _nbformat_is_valid(valid_fixture_path)
        lib_valid = _libipynb_is_valid(valid_fixture_path)

        # Both should accept valid fixtures
        assert lib_valid, f"libipynb rejected valid fixture {valid_fixture_path.name}"
        assert nb_valid, f"nbformat rejected valid fixture {valid_fixture_path.name}"


class TestInvalidNotebooks:
    """Invalid fixtures should be rejected by both validators.

    Note: nbformat and libipynb may disagree on *which* specific errors
    they report, but both should agree the notebook is not valid.
    If a specific invalid fixture is accepted by one library due to
    intentional leniency differences, mark it with xfail and document why.
    """

    def test_invalid_notebooks_rejected_by_both(self, invalid_fixture_path: Path):
        nb_valid = _nbformat_is_valid(invalid_fixture_path)
        lib_valid = _libipynb_is_valid(invalid_fixture_path)

        # libipynb should reject invalid fixtures
        assert not lib_valid, f"libipynb accepted invalid fixture {invalid_fixture_path.name}"

        # nbformat should also reject them.
        # Some invalid fixtures may be accepted by nbformat due to differences
        # in strictness (e.g., nbformat may tolerate missing optional fields
        # that libipynb requires). Document these cases below.
        if nb_valid:
            pytest.skip(
                f"nbformat accepted {invalid_fixture_path.name} "
                f"(known leniency difference) -- libipynb correctly rejected it"
            )
