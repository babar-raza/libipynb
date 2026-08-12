"""Read-only notebook summaries; analytics do not participate in conformance."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from ..codec.reader import Source, load


def _model(value: Source | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return load(value, mode="recovery").raw


def cell_type_histogram(
    value: Source | Mapping[str, Any],
) -> dict[str, int]:
    cells = _model(value).get("cells", [])
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
    for cell in _model(value).get("cells", []):
        if not isinstance(cell, Mapping):
            continue
        for output in cell.get("outputs", []):
            if isinstance(output, Mapping):
                counter[str(output.get("output_type", "unknown"))] += 1
    return dict(sorted(counter.items()))


def has_execution_errors(value: Source | Mapping[str, Any]) -> bool:
    return output_type_histogram(value).get("error", 0) > 0


def average_source_length(value: Source | Mapping[str, Any]) -> float:
    cells = [cell for cell in _model(value).get("cells", []) if isinstance(cell, Mapping)]
    if not cells:
        return 0.0
    sizes = []
    for cell in cells:
        source = cell.get("source", "")
        sizes.append(len("".join(source) if isinstance(source, list) else str(source)))
    return sum(sizes) / len(sizes)
