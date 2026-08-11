"""Property-based tests for notebook roundtrip fidelity using Hypothesis."""

from __future__ import annotations

import json

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from libipynb import loads, dumps, load, NotebookDocument


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
            st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",))),
            children,
            max_size=4,
        ),
    ),
    max_leaves=20,
)

_metadata = st.dictionaries(
    st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",))),
    _simple_json_values,
    max_size=3,
)

_stream_output = st.fixed_dictionaries({
    "output_type": st.just("stream"),
    "name": st.sampled_from(["stdout", "stderr"]),
    "text": _safe_text,
})

_execute_result_output = st.fixed_dictionaries({
    "output_type": st.just("execute_result"),
    "data": st.fixed_dictionaries({"text/plain": _safe_text}),
    "metadata": st.just({}),
    "execution_count": st.integers(min_value=1, max_value=999),
})

_output = st.one_of(_stream_output, _execute_result_output)


def _make_cell(cell_type: str, source: str, metadata: dict, outputs: list) -> dict:
    cell = {"cell_type": cell_type, "source": source, "metadata": metadata}
    if cell_type == "code":
        cell["outputs"] = outputs
        cell["execution_count"] = None
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
)

_raw_cell = st.builds(
    _make_cell,
    cell_type=st.just("raw"),
    source=_source_text,
    metadata=_metadata,
    outputs=st.just([]),
)

_cell = st.one_of(_code_cell, _markdown_cell, _raw_cell)


def _make_notebook(cells: list[dict], minor: int, nb_metadata: dict) -> dict:
    meta = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.0"},
    }
    meta.update(nb_metadata)
    return {"nbformat": 4, "nbformat_minor": minor, "metadata": meta, "cells": cells}


_notebook_dict = st.builds(
    _make_notebook,
    cells=st.lists(_cell, min_size=0, max_size=8),
    minor=st.sampled_from([0, 1, 2, 3, 4]),
    nb_metadata=_metadata,
)


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
        [{"cell_type": "code", "source": "x", "metadata": metadata, "outputs": [], "execution_count": None}],
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
        [{"cell_type": "code", "source": source, "metadata": {}, "outputs": [], "execution_count": None}],
        minor=4,
        nb_metadata={},
    )
    doc = loads(json.dumps(nb), mode="recovery")
    reloaded = json.loads(dumps(doc, profile="declared"))
    assert reloaded["cells"][0]["source"] == source
