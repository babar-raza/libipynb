"""LIBIPYNB-P7 acceptance check: the oracle scaffolding itself must skip
cleanly (not fail, not error) when a reference tool isn't installed, and
must genuinely pass -- not fail -- when the tool IS installed, and the
shared fixture builders must produce structurally valid notebooks before any
feature card is allowed to build real comparisons on top of this.

Gate G2 finding: the first version of the five `*_available` tests below
asserted `raise AssertionError(...)` whenever the fixture did NOT skip --
i.e. they were designed to fail the moment the reference tool is actually
present, which is exactly backwards and would have produced 5 hard failures
on the very first CI job that installs `libipynb[oracle]` (the entire
reason this scaffolding exists). Fixed: each test now performs a real,
minimal positive check when the tool is importable, and `pytest.importorskip`
itself (trusted stdlib behavior, not re-tested here) handles the skip path --
so the test body only ever runs when there is something genuine to assert.
"""

from __future__ import annotations

from libipynb import validate

from .conftest import parameterizable_notebook, representative_notebook


def test_representative_notebook_is_schema_valid() -> None:
    result = validate(representative_notebook())
    assert result.is_valid, list(result)


def test_parameterizable_notebook_is_schema_valid_and_tagged() -> None:
    doc = parameterizable_notebook()
    result = validate(doc)
    assert result.is_valid, list(result)
    tagged = [c for c in doc["cells"] if "parameters" in c.get("metadata", {}).get("tags", [])]
    assert len(tagged) == 1


def test_nbstripout_fixture_imports_the_real_package_when_available(nbstripout_available) -> None:
    import nbstripout

    assert nbstripout is not None


def test_nbdime_fixture_imports_the_real_package_when_available(nbdime_available) -> None:
    import nbdime

    assert nbdime is not None


def test_nbconvert_fixture_imports_the_real_package_when_available(nbconvert_available) -> None:
    import nbconvert

    assert nbconvert is not None


def test_nbclient_fixture_imports_the_real_package_when_available(nbclient_available) -> None:
    import nbclient

    assert nbclient is not None


def test_papermill_fixture_imports_the_real_package_when_available(papermill_available) -> None:
    import papermill

    assert papermill is not None


def test_oracle_tmp_notebook_fixture_writes_a_loadable_file(oracle_tmp_notebook) -> None:
    from libipynb import load

    path = oracle_tmp_notebook()
    doc = load(path)
    assert doc.cell_count == 3
