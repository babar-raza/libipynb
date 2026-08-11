"""Failure-first tests for lossless, read-only typed metadata adapters."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import pytest
from libipynb import (
    NotebookDocument,
    cell_metadata,
    dumps,
    load,
    loads,
    notebook_metadata,
    output_metadata,
)
from libipynb.model import MetadataShapeError

VALID_DIR = Path(__file__).resolve().parent / "fixtures" / "valid"


def _document() -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "name": "python3",
                    "display_name": "Python 3",
                    "language": "python",
                    "vendor_kernel": {"keep": True},
                },
                "language_info": {
                    "name": "python",
                    "version": "3.13",
                    "mimetype": "text/x-python",
                    "file_extension": ".py",
                    "codemirror_mode": {"name": "ipython", "version": 3},
                    "pygments_lexer": "ipython3",
                    "vendor_language": ["keep"],
                },
                "title": "Vendor Notebook",
                "authors": [
                    {
                        "name": "Ada Lovelace",
                        "affiliation": "Analytical Engine Institute",
                    },
                    {"orcid": "0000-0000-0000-0000"},
                ],
                "org.example": {"notebook": "keep"},
            },
            "cells": [
                {
                    "cell_type": "code",
                    "id": "code",
                    "metadata": {
                        "tags": ["parameters", "production"],
                        "slideshow": {
                            "slide_type": "slide",
                            "vendor_slide": "keep",
                        },
                        "jupyter": {
                            "source_hidden": True,
                            "outputs_hidden": False,
                            "vendor_jupyter": "keep",
                        },
                        "execution": {
                            "iopub.status.busy": "2026-07-26T00:00:00Z",
                            "iopub.execute_input": "2026-07-26T00:00:01Z",
                            "shell.execute_reply": "2026-07-26T00:00:02Z",
                            "iopub.status.idle": "2026-07-26T00:00:03Z",
                            "shell.execute_reply.started": "2026-07-26T00:00:02Z",
                            "vendor_timing": "4",
                        },
                        "org.example": {"cell": "keep"},
                    },
                    "source": "value = 1",
                    "execution_count": 1,
                    "outputs": [
                        {
                            "output_type": "display_data",
                            "data": {
                                "text/plain": "1",
                                "text/html": "<b>1</b>",
                            },
                            "metadata": {
                                "text/html": {
                                    "isolated": True,
                                    "vendor_render": "keep",
                                },
                                "org.example": {"output": "keep"},
                            },
                        }
                    ],
                }
            ],
        }
    )


def test_real_fixture_kernelspec_adapter_is_exact_and_non_mutating() -> None:
    document = load(VALID_DIR / "minimal.ipynb")
    before = deepcopy(document.raw)

    adapter = notebook_metadata(document)
    kernel = adapter.kernelspec

    assert kernel is not None
    assert kernel.name == "python3"
    assert kernel.display_name == "Python 3"
    assert kernel.language == "python"
    assert kernel.to_dict() == before["metadata"]["kernelspec"]
    assert adapter.language_info is None
    assert document.raw == before


def test_notebook_metadata_typed_fields_preserve_unknown_namespaces() -> None:
    document = _document()
    adapter = notebook_metadata(document)

    kernel = adapter.kernelspec
    language = adapter.language_info

    assert kernel is not None and language is not None
    assert kernel.extras == {"vendor_kernel": {"keep": True}}
    assert language.name == "python"
    assert language.version == "3.13"
    assert language.codemirror_mode == {"name": "ipython", "version": 3}
    assert language.extras == {"vendor_language": ["keep"]}
    assert adapter.extras == {"org.example": {"notebook": "keep"}}
    assert adapter.to_dict() == document.raw["metadata"]


def test_notebook_metadata_models_title_and_authors_with_preserved_extras() -> None:
    document = _document()
    adapter = notebook_metadata(document)

    assert adapter.title == "Vendor Notebook"
    authors = adapter.authors
    assert authors is not None and len(authors) == 2
    assert authors[0].name == "Ada Lovelace"
    assert authors[0].extras == {
        "affiliation": "Analytical Engine Institute"
    }
    assert authors[1].name is None
    assert authors[1].extras == {"orcid": "0000-0000-0000-0000"}
    assert authors[1].to_dict() == {"orcid": "0000-0000-0000-0000"}
    assert "title" not in adapter.extras
    assert "authors" not in adapter.extras


def test_notebook_metadata_title_and_authors_are_absent_when_not_declared() -> None:
    document = load(VALID_DIR / "minimal.ipynb")
    adapter = notebook_metadata(document)

    assert adapter.title is None
    assert adapter.authors is None


def test_cell_metadata_models_jupyter_visibility_with_preserved_extras() -> None:
    document = _document()
    cell_adapter = cell_metadata(document.cell_objects[0])

    jupyter = cell_adapter.jupyter
    assert jupyter is not None
    assert jupyter.source_hidden is True
    assert jupyter.outputs_hidden is False
    assert jupyter.extras == {"vendor_jupyter": "keep"}
    assert jupyter.to_dict() == {
        "source_hidden": True,
        "outputs_hidden": False,
        "vendor_jupyter": "keep",
    }
    assert "jupyter" not in cell_adapter.extras


def test_cell_metadata_jupyter_visibility_fields_are_each_independently_optional() -> None:
    document = NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "raw",
                    "id": "raw-cell",
                    "metadata": {"jupyter": {"source_hidden": True}},
                    "source": "",
                }
            ],
        }
    )
    cell_adapter = cell_metadata(document.cell_objects[0])

    jupyter = cell_adapter.jupyter
    assert jupyter is not None
    assert jupyter.source_hidden is True
    assert jupyter.outputs_hidden is None
    assert jupyter.extras == {}


def test_cell_and_output_adapters_cover_common_namespaces() -> None:
    document = _document()
    cell_adapter = cell_metadata(document.cell_objects[0])
    output_adapter = output_metadata(
        document.cell_objects[0].output_objects[0]
    )

    assert cell_adapter.tags == ("parameters", "production")
    assert cell_adapter.slideshow is not None
    assert cell_adapter.slideshow.slide_type == "slide"
    assert cell_adapter.slideshow.extras == {"vendor_slide": "keep"}
    assert cell_adapter.execution is not None
    assert cell_adapter.execution.iopub_status_busy == "2026-07-26T00:00:00Z"
    assert cell_adapter.execution.iopub_execute_input == "2026-07-26T00:00:01Z"
    assert cell_adapter.execution.shell_execute_reply == "2026-07-26T00:00:02Z"
    assert cell_adapter.execution.iopub_status_idle == "2026-07-26T00:00:03Z"
    assert cell_adapter.execution.extras == {
        "shell.execute_reply.started": "2026-07-26T00:00:02Z",
        "vendor_timing": "4",
    }
    assert cell_adapter.extras == {"org.example": {"cell": "keep"}}

    html = output_adapter.mime("text/html")
    assert html is not None
    assert html.values == {
        "isolated": True,
        "vendor_render": "keep",
    }
    assert output_adapter.mime("image/png") is None
    assert output_adapter.extras == {
        "org.example": {"output": "keep"}
    }


def test_adapters_are_defensive_snapshots_and_roundtrip_is_lossless() -> None:
    document = _document()
    before = deepcopy(document.raw)
    adapter = notebook_metadata(document)
    exported = adapter.to_dict()

    exported["org.example"]["notebook"] = "changed copy"
    document.raw["metadata"]["org.example"]["notebook"] = "changed source"

    assert adapter.extras == {"org.example": {"notebook": "keep"}}
    document.raw.clear()
    document.raw.update(before)
    assert loads(dumps(document)).raw == before


@pytest.mark.parametrize(
    "mutate, access, message",
    [
        (
            lambda value: value.raw["metadata"].update(kernelspec="bad"),
            lambda value: notebook_metadata(value).kernelspec,
            "kernelspec",
        ),
        (
            lambda value: value.cells[0]["metadata"].update(
                tags=["duplicate", "duplicate"]
            ),
            lambda value: cell_metadata(value.cell_objects[0]).tags,
            "unique",
        ),
        (
            lambda value: value.cells[0]["metadata"].update(
                tags=["a,b"]
            ),
            lambda value: cell_metadata(value.cell_objects[0]).tags,
            "comma",
        ),
        (
            lambda value: value.cells[0]["outputs"][0]["metadata"].update(
                {"text/html": "bad"}
            ),
            lambda value: output_metadata(
                value.cell_objects[0].output_objects[0]
            ).mime("text/html"),
            "text/html",
        ),
        (
            lambda value: value.raw["metadata"].update(title=123),
            lambda value: notebook_metadata(value).title,
            "title",
        ),
        (
            lambda value: value.raw["metadata"].update(authors="bad"),
            lambda value: notebook_metadata(value).authors,
            "authors",
        ),
        (
            lambda value: value.raw["metadata"].update(authors=["bad"]),
            lambda value: notebook_metadata(value).authors,
            "author",
        ),
        (
            lambda value: value.cells[0]["metadata"].update(jupyter="bad"),
            lambda value: cell_metadata(value.cell_objects[0]).jupyter,
            "jupyter",
        ),
        (
            lambda value: value.cells[0]["metadata"]["jupyter"].update(
                source_hidden="yes"
            ),
            lambda value: cell_metadata(value.cell_objects[0]).jupyter,
            "source_hidden",
        ),
    ],
)
def test_malformed_known_metadata_fails_explicitly(
    mutate: Callable[[NotebookDocument], object],
    access: Callable[[NotebookDocument], object],
    message: str,
) -> None:
    document = _document()
    mutate(document)

    with pytest.raises(MetadataShapeError, match=message):
        access(document)
