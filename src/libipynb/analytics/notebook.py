"""Read-only notebook summaries; analytics do not participate in conformance."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from ..codec.reader import Source, load


def _model(value: Source | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return load(value, mode="recovery").raw


def _list_or_empty(value: object) -> list[Any]:
    """`.get(key, [])` only substitutes its default when `key` is
    *absent* -- a permissively-loaded notebook (``mode="preservation"``/
    ``"recovery"``) can legitimately carry an explicit JSON ``null`` for
    ``cells``/``outputs`` (confirmed directly: ``{"cells": null, ...}``
    loads successfully under both modes), which `.get(key, [])` passes
    through unchanged, crashing every caller that then iterates the
    result. Coerces anything that isn't actually a list -- ``None`` or
    otherwise -- to an empty one instead."""
    return value if isinstance(value, list) else []


def _code_cell_outputs(cell: Mapping[str, Any]) -> list[Any]:
    """Only code cells have a meaningful ``outputs`` field in valid
    nbformat -- matches this codebase's own established convention
    elsewhere (``model/document.py``, ``model/cleanup.py``,
    ``adapters/export.py``, ``validation/rules.py`` all gate output/
    execution-related processing on ``cell_type == "code"``). An earlier
    version of this module's `output_type_histogram` had no such filter,
    while the newer `execution_errors` did -- an inconsistency that made
    ``has_execution_errors`` (built on the former) and `execution_errors`
    (the latter) able to disagree about the very same notebook.
    Reconciled here: every output-inspecting function in this module now
    shares this one scope."""
    if cell.get("cell_type") != "code":
        return []
    return _list_or_empty(cell.get("outputs"))


def cell_type_histogram(
    value: Source | Mapping[str, Any],
) -> dict[str, int]:
    cells = _list_or_empty(_model(value).get("cells"))
    return dict(
        sorted(
            Counter(
                str(cell.get("cell_type", "unknown")) for cell in cells if isinstance(cell, Mapping)
            ).items()
        )
    )


def output_type_histogram(
    value: Source | Mapping[str, Any],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for cell in _list_or_empty(_model(value).get("cells")):
        if not isinstance(cell, Mapping):
            continue
        for output in _code_cell_outputs(cell):
            if isinstance(output, Mapping):
                counter[str(output.get("output_type", "unknown"))] += 1
    return dict(sorted(counter.items()))


def has_execution_errors(value: Source | Mapping[str, Any]) -> bool:
    return output_type_histogram(value).get("error", 0) > 0


def _text_length(value: object) -> int:
    """`source`/output `text` fields are nbformat's well-known dual
    representation -- a single string, or a list of line-strings that
    concatenate to the same content. Both are valid; measure either
    shape's total character count identically. Character count, not byte
    count -- matches `average_source_length`'s pre-existing, established
    convention, which this helper was factored out of. Only ``None`` is
    special-cased to 0 (a permissively-loaded notebook can carry an
    explicit ``"source": null``) -- any other falsy-but-present value
    (``0``, ``False``, ``""``) still measures via ``str(value)``,
    matching the original inline logic this replaced exactly for every
    case except ``None`` itself."""
    if value is None:
        return 0
    if isinstance(value, list):
        return len("".join(str(line) for line in value))
    return len(str(value))


def _text_byte_length(value: object) -> int:
    """Same dual-shape handling as `_text_length`, but UTF-8 *byte*
    count -- for the size-in-bytes analytics below, where a character
    count would misrepresent on-disk footprint for any non-ASCII
    content."""
    if value is None:
        return 0
    if isinstance(value, list):
        return len("".join(str(line) for line in value).encode("utf-8"))
    return len(str(value).encode("utf-8"))


def average_source_length(value: Source | Mapping[str, Any]) -> float:
    cells = [
        cell for cell in _list_or_empty(_model(value).get("cells")) if isinstance(cell, Mapping)
    ]
    if not cells:
        return 0.0
    sizes = [_text_length(cell.get("source", "")) for cell in cells]
    return sum(sizes) / len(sizes)


def largest_cells(
    value: Source | Mapping[str, Any], *, top_n: int = 5
) -> list[dict[str, int | str]]:
    """The `top_n` cells with the longest `source`, largest first --
    useful for spotting notebooks with a few outsized cells dragging up
    the average, which `average_source_length` alone can't reveal.
    `top_n` must be a positive integer; ties keep original cell order."""
    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    cells = [
        cell for cell in _list_or_empty(_model(value).get("cells")) if isinstance(cell, Mapping)
    ]
    entries: list[tuple[int, str, int]] = [
        (index, str(cell.get("cell_type", "unknown")), _text_length(cell.get("source", "")))
        for index, cell in enumerate(cells)
    ]
    entries.sort(key=lambda entry: (-entry[2], entry[0]))
    return [
        {"index": index, "cell_type": cell_type, "source_length": source_length}
        for index, cell_type, source_length in entries[:top_n]
    ]


def notebook_byte_size(value: Source | Mapping[str, Any]) -> int:
    """Total size, in UTF-8 bytes, of the notebook as canonical JSON --
    a proxy for on-disk footprint independent of the source's own
    formatting (this session's own indentation/key order, if the input
    was already a dict, doesn't affect the result). ``default=str``
    keeps this resilient to a directly-passed ``Mapping`` containing a
    non-JSON-native value (e.g. a caller-constructed dict with a
    ``datetime`` in it) rather than raising -- a file/bytes/path input
    can never hit this, since the codec's own JSON parser only ever
    produces plain JSON-native types."""
    model = _model(value)
    return len(json.dumps(model, sort_keys=True, default=str).encode("utf-8"))


def metadata_size_breakdown(value: Source | Mapping[str, Any]) -> dict[str, int]:
    """Byte size of notebook-level `metadata` versus the summed byte size
    of every cell's own `metadata` -- surfaces metadata bloat (e.g. a
    heavy `widgets` block, or many cells each carrying a large editor-
    specific metadata blob) that `notebook_byte_size` alone can't
    distinguish from genuine content."""
    model = _model(value)
    notebook_metadata = model.get("metadata", {})
    notebook_metadata_bytes = len(
        json.dumps(
            notebook_metadata if isinstance(notebook_metadata, Mapping) else {}, default=str
        ).encode("utf-8")
    )
    cell_metadata_bytes = 0
    for cell in _list_or_empty(model.get("cells")):
        if not isinstance(cell, Mapping):
            continue
        cell_metadata = cell.get("metadata", {})
        if isinstance(cell_metadata, Mapping):
            cell_metadata_bytes += len(json.dumps(cell_metadata, default=str).encode("utf-8"))
    return {
        "notebook_metadata_bytes": notebook_metadata_bytes,
        "cell_metadata_bytes": cell_metadata_bytes,
    }


def execution_errors(value: Source | Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every error output in the notebook, individually -- unlike
    `has_execution_errors`'s single boolean, this names which cell(s)
    failed and with what, e.g. for surfacing a per-cell error report
    rather than only a whole-notebook yes/no. Scope (code cells only)
    matches `output_type_histogram`'s -- see `_code_cell_outputs`."""
    errors: list[dict[str, Any]] = []
    for cell_index, cell in enumerate(_list_or_empty(_model(value).get("cells"))):
        if not isinstance(cell, Mapping):
            continue
        for output in _code_cell_outputs(cell):
            if isinstance(output, Mapping) and output.get("output_type") == "error":
                errors.append(
                    {
                        "cell_index": cell_index,
                        "ename": str(output.get("ename", "")),
                        "evalue": str(output.get("evalue", "")),
                    }
                )
    return errors


def output_size_histogram(value: Source | Mapping[str, Any]) -> dict[str, int]:
    """Total byte size per `output_type`, summed across the whole
    notebook -- `output_type_histogram` counts *how many* outputs of each
    type exist; this measures how large they are, which a count alone
    can't reveal (one huge `display_data` payload vs. many tiny ones
    look identical in a count-only histogram). Scope (code cells only)
    matches `output_type_histogram`'s -- see `_code_cell_outputs`."""
    sizes: Counter[str] = Counter()
    for cell in _list_or_empty(_model(value).get("cells")):
        if not isinstance(cell, Mapping):
            continue
        for output in _code_cell_outputs(cell):
            if not isinstance(output, Mapping):
                continue
            output_type = str(output.get("output_type", "unknown"))
            size = 0
            text = output.get("text")
            if text is not None:
                size += _text_byte_length(text)
            data = output.get("data")
            if isinstance(data, Mapping):
                size += sum(_text_byte_length(payload) for payload in data.values())
            traceback = output.get("traceback")
            if isinstance(traceback, list):
                size += sum(_text_byte_length(line) for line in traceback)
            sizes[output_type] += size
    return dict(sorted(sizes.items()))


def attachment_size_summary(value: Source | Mapping[str, Any]) -> dict[str, int]:
    """Count and total byte size of every cell attachment (base64
    payload string length, not decoded-binary length -- proportional to
    on-disk footprint, matching `notebook_byte_size`'s own convention).
    Only string payloads are counted -- matching real nbformat's schema
    (an attachment MIME payload is always a base64 string) and this
    codebase's own established convention (`adapters/export.py`'s
    `_collect_resources` likewise only treats a string payload as real
    attachment content); anything else is malformed/adversarial content,
    not a real attachment, and contributes neither to the count nor the
    byte total rather than being counted with a nonsensical size."""
    count = 0
    total_bytes = 0
    for cell in _list_or_empty(_model(value).get("cells")):
        if not isinstance(cell, Mapping):
            continue
        attachments = cell.get("attachments")
        if not isinstance(attachments, Mapping):
            continue
        for bundle in attachments.values():
            if not isinstance(bundle, Mapping):
                continue
            for payload in bundle.values():
                if not isinstance(payload, str):
                    continue
                count += 1
                total_bytes += _text_byte_length(payload)
    return {"count": count, "total_bytes": total_bytes}
