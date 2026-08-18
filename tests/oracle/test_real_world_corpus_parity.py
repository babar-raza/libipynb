"""LIBIPYNB-Q2 (real-world corpus sourcing) Gate G6: the piece that
actually satisfies `plans/gate-status-g1-g7.md`'s stated G6 criterion --
"real-world licensed corpus reopens/validates in the applicable upstream
tools" -- not vendoring alone. Iterates every vendored real-world fixture
(see tests/fixtures/PROVENANCE.md's "Vendored real-world fixtures" table
and tests/integration/test_obligation_corpus_integrity.py's
REAL_WORLD_HASHES) through the same real, installed reference tools the
rest of tests/oracle/ already cross-checks against.

Deliberately empty (each test collects as a single, visibly SKIPPED case
-- "got empty parameter set for (path)" -- rather than silently vanishing)
until at least one real fixture is vendored. This is the honest, disclosed
state, not a false-positive "passing" claim about a corpus that does not
exist yet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libipynb import NotebookDocument, load, validate
from libipynb.execution import ExecutionOptions, LocalJupyterExecutor
from tests.integration.test_obligation_corpus_integrity import FIXTURES, REAL_WORLD_HASHES


def _real_world_fixture_paths() -> list[Path]:
    return [
        FIXTURES / category / filename
        for category, files in REAL_WORLD_HASHES.items()
        for filename in files
    ]


@pytest.mark.parametrize("path", _real_world_fixture_paths(), ids=lambda p: p.name)
def test_real_world_fixture_loads_and_validates_via_libipynb(path: Path) -> None:
    """Baseline: libipynb's own strict load + schema validation, mirroring
    the synthetic-fixture bar in test_obligation_corpus_integrity.py --
    the first thing any vendored real-world fixture must clear regardless
    of which oracle tools happen to be installed."""
    document = load(path, mode="strict")
    report = validate(document.raw)
    assert report.is_valid, [d.message for d in report]


@pytest.mark.parametrize("path", _real_world_fixture_paths(), ids=lambda p: p.name)
def test_real_world_fixture_round_trips_through_nbformat(path: Path) -> None:
    """Cross-checks against real, installed `nbformat` -- a genuine
    external tool re-opening content this project vendored, not a
    self-round-trip (which this project's own oracle-test conventions
    explicitly refuse to count as interoperability evidence)."""
    nbformat = pytest.importorskip("nbformat", reason="nbformat is not installed")
    raw = json.loads(path.read_text(encoding="utf-8"))
    nbformat.validate(raw)  # raises on schema disagreement


@pytest.mark.parametrize("path", _real_world_fixture_paths(), ids=lambda p: p.name)
def test_real_world_fixture_executes_if_it_has_a_python_kernelspec(path: Path) -> None:
    """Only meaningful for fixtures declaring a runnable Python kernel --
    skips cleanly (not a failure) for fixtures chosen specifically to
    exercise a different kernel/language, or no kernelspec at all."""
    pytest.importorskip("nbclient", reason="nbclient (exec extra) is not installed")
    kernelspec = pytest.importorskip(
        "jupyter_client.kernelspec", reason="jupyter_client (exec extra) is not installed"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    declared_kernel = raw.get("metadata", {}).get("kernelspec", {}).get("name")
    if declared_kernel not in kernelspec.find_kernel_specs():
        pytest.skip(f"kernelspec {declared_kernel!r} not installed in this environment")

    document = NotebookDocument(raw)
    result = LocalJupyterExecutor().execute(
        document, options=ExecutionOptions(acknowledge_unsandboxed=True, cell_timeout=60)
    )
    assert result.kernel_launch_error is None
    assert result.kernel_death_error is None
