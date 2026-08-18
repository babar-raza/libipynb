"""Property-based tests for notebook roundtrip fidelity using Hypothesis."""

from __future__ import annotations

import base64
import json

from hypothesis import given, settings
from hypothesis import strategies as st

from libipynb import dumps, loads

# --- Strategies ---

_cell_types = st.sampled_from(["code", "markdown", "raw"])

_safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),  # exclude surrogates
        blacklist_characters=("\x00",),
    ),
    min_size=0,
    max_size=500,
)

_source_text = st.one_of(
    _safe_text,
    st.lists(_safe_text, max_size=5).map(lambda parts: "\n".join(parts)),
)

_simple_json_values = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**53), max_value=2**53),
        st.floats(allow_nan=False, allow_infinity=False),
        _safe_text,
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    blacklist_categories=("Cs",), blacklist_characters=("\x00",)
                ),
            ),
            children,
            max_size=4,
        ),
    ),
    max_leaves=20,
)

_metadata = st.dictionaries(
    st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",)),
    ),
    _simple_json_values,
    max_size=3,
)

_stream_output = st.fixed_dictionaries(
    {
        "output_type": st.just("stream"),
        "name": st.sampled_from(["stdout", "stderr"]),
        "text": _safe_text,
    }
)

_execute_result_output = st.fixed_dictionaries(
    {
        "output_type": st.just("execute_result"),
        "data": st.fixed_dictionaries({"text/plain": _safe_text}),
        "metadata": st.just({}),
        "execution_count": st.integers(min_value=1, max_value=999),
    }
)

# LIBIPYNB-Q13c: the strategy previously only ever generated stream/
# execute_result outputs -- error and display_data (the other two
# nbformat-defined output types) had never been exercised by this file's
# roundtrip properties.
_error_output = st.fixed_dictionaries(
    {
        "output_type": st.just("error"),
        "ename": st.text(
            min_size=1, max_size=40, alphabet=st.characters(blacklist_categories=("Cs",))
        ),
        "evalue": _safe_text,
        "traceback": st.lists(_safe_text, max_size=5),
    }
)

_display_data_output = st.fixed_dictionaries(
    {
        "output_type": st.just("display_data"),
        "data": st.fixed_dictionaries({"text/plain": _safe_text}),
        "metadata": st.just({}),
    }
)

_output = st.one_of(_stream_output, _execute_result_output, _error_output, _display_data_output)

# LIBIPYNB-Q13c: an attachment-bearing branch -- previously no strategy ever
# generated a cell carrying `attachments`, so that field's roundtrip fidelity
# was untested by this file entirely.
_attachment_name = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="._-"),
)
_attachment_payload = st.binary(min_size=0, max_size=50).map(
    lambda data: base64.b64encode(data).decode("ascii")
)
_attachments = st.dictionaries(
    _attachment_name,
    st.dictionaries(
        st.sampled_from(["image/png", "image/jpeg", "image/svg+xml"]),
        _attachment_payload,
        min_size=1,
        max_size=1,
    ),
    max_size=2,
)


def _make_cell(
    cell_type: str,
    source: str,
    metadata: dict,
    outputs: list,
    attachments: dict | None = None,
) -> dict:
    cell = {"cell_type": cell_type, "source": source, "metadata": metadata}
    if cell_type == "code":
        cell["outputs"] = outputs
        cell["execution_count"] = None
    if attachments:
        cell["attachments"] = attachments
    return cell


_code_cell = st.builds(
    _make_cell,
    cell_type=st.just("code"),
    source=_source_text,
    metadata=_metadata,
    outputs=st.lists(_output, max_size=3),
)

_markdown_cell = st.builds(
    _make_cell,
    cell_type=st.just("markdown"),
    source=_source_text,
    metadata=_metadata,
    outputs=st.just([]),
    # Only markdown/raw cells carry attachments in real nbformat documents
    # (referenced via an `attachment:` URI in source) -- code cells never do.
    attachments=st.one_of(st.just(None), _attachments),
)

_raw_cell = st.builds(
    _make_cell,
    cell_type=st.just("raw"),
    source=_source_text,
    metadata=_metadata,
    outputs=st.just([]),
    attachments=st.one_of(st.just(None), _attachments),
)

_cell = st.one_of(_code_cell, _markdown_cell, _raw_cell)


def _make_notebook(cells: list[dict], minor: int, nb_metadata: dict) -> dict:
    meta = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.0"},
    }
    meta.update(nb_metadata)
    return {"nbformat": 4, "nbformat_minor": minor, "metadata": meta, "cells": cells}


_notebook_dict_implicit_ids = st.builds(
    _make_notebook,
    cells=st.lists(_cell, min_size=0, max_size=8),
    minor=st.sampled_from([0, 1, 2, 3, 4]),
    nb_metadata=_metadata,
)

# LIBIPYNB-Q13c: an explicit-cell-id branch alongside the implicit-only one
# above. The strategy above deliberately never generates nbformat_minor 5,
# because 4.5 requires every cell to carry a valid, unique `id` and nothing
# in it synthesized one (IPYNB-ID-001: only the explicit `upgrade()` path
# synthesizes ids) -- so minor-5 roundtrip fidelity was entirely untested by
# this file. This composite strategy generates a genuine 4.5 notebook with
# real, unique, valid ids instead.
_cell_id = st.text(
    alphabet=st.characters(
        whitelist_categories=(),
        whitelist_characters="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    ),
    min_size=1,
    max_size=64,
)


@st.composite
def _notebook_with_explicit_cell_ids(draw: st.DrawFn) -> dict:
    cells_without_id = draw(st.lists(_cell, min_size=0, max_size=8))
    ids = draw(
        st.lists(
            _cell_id, min_size=len(cells_without_id), max_size=len(cells_without_id), unique=True
        )
    )
    cells = [{**cell, "id": cell_id} for cell, cell_id in zip(cells_without_id, ids)]
    nb_metadata = draw(_metadata)
    return _make_notebook(cells, minor=5, nb_metadata=nb_metadata)


_notebook_dict = st.one_of(_notebook_dict_implicit_ids, _notebook_with_explicit_cell_ids())


# --- Tests ---


@given(nb=_notebook_dict)
@settings(max_examples=200, deadline=5000)
def test_load_dump_preserves_cell_count(nb: dict) -> None:
    doc = loads(json.dumps(nb), mode="recovery")
    reloaded = json.loads(dumps(doc, profile="declared"))
    assert len(reloaded["cells"]) == len(nb["cells"])


@given(nb=_notebook_dict)
@settings(max_examples=200, deadline=5000)
def test_load_dump_preserves_cell_types(nb: dict) -> None:
    doc = loads(json.dumps(nb), mode="recovery")
    reloaded = json.loads(dumps(doc, profile="declared"))
    original_types = [c["cell_type"] for c in nb["cells"]]
    roundtrip_types = [c["cell_type"] for c in reloaded["cells"]]
    assert roundtrip_types == original_types


@given(nb=_notebook_dict)
@settings(max_examples=200, deadline=5000)
def test_load_dump_preserves_source_content(nb: dict) -> None:
    doc = loads(json.dumps(nb), mode="recovery")
    reloaded = json.loads(dumps(doc, profile="declared"))
    for orig, rt in zip(nb["cells"], reloaded["cells"]):
        orig_src = orig["source"]
        rt_src = rt["source"]
        if isinstance(orig_src, list):
            orig_src = "".join(orig_src)
        if isinstance(rt_src, list):
            rt_src = "".join(rt_src)
        assert rt_src == orig_src


@given(nb=_notebook_dict)
@settings(max_examples=200, deadline=5000)
def test_load_dump_preserves_nbformat_version(nb: dict) -> None:
    doc = loads(json.dumps(nb), mode="recovery")
    reloaded = json.loads(dumps(doc, profile="declared"))
    assert reloaded["nbformat"] == 4


@given(nb=_notebook_dict)
@settings(max_examples=200, deadline=5000)
def test_double_roundtrip_is_stable(nb: dict) -> None:
    raw = json.dumps(nb)
    doc1 = loads(raw, mode="recovery")
    out1 = dumps(doc1, profile="declared")
    doc2 = loads(out1, mode="recovery")
    out2 = dumps(doc2, profile="declared")
    assert out1 == out2


@given(metadata=_metadata)
@settings(max_examples=200, deadline=5000)
def test_arbitrary_metadata_survives_roundtrip(metadata: dict) -> None:
    nb = _make_notebook(
        [
            {
                "cell_type": "code",
                "source": "x",
                "metadata": metadata,
                "outputs": [],
                "execution_count": None,
            }
        ],
        minor=4,
        nb_metadata={},
    )
    doc = loads(json.dumps(nb), mode="recovery")
    reloaded = json.loads(dumps(doc, profile="declared"))
    assert reloaded["cells"][0]["metadata"] == metadata


@given(source=_source_text)
@settings(max_examples=200, deadline=5000)
def test_arbitrary_unicode_source_survives_roundtrip(source: str) -> None:
    nb = _make_notebook(
        [
            {
                "cell_type": "code",
                "source": source,
                "metadata": {},
                "outputs": [],
                "execution_count": None,
            }
        ],
        minor=4,
        nb_metadata={},
    )
    doc = loads(json.dumps(nb), mode="recovery")
    reloaded = json.loads(dumps(doc, profile="declared"))
    assert reloaded["cells"][0]["source"] == source
