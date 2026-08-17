"""Fuzz libipynb.sanitize()'s markup scanner.

sanitize() parses cell source, attachment, and output MIME payloads with
Python's stdlib html.parser to classify (not render) active content --
exactly the kind of hand-written parser that benefits from fuzzing. This
target keeps the notebook shape fixed and fuzzes the markdown source and
MIME payload text a hostile notebook would vary.
"""

from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from libipynb import NotebookError
    from libipynb.model import NotebookDocument
    from libipynb.security import sanitize


def _fuzz_string(fdp: atheris.FuzzedDataProvider, max_len: int = 500) -> str:
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, max_len))


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    markdown_source = _fuzz_string(fdp, 500)
    html_payload = _fuzz_string(fdp, 500)
    svg_payload = _fuzz_string(fdp, 300)

    document = NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "m",
                    "metadata": {},
                    "source": markdown_source,
                },
                {
                    "cell_type": "code",
                    "id": "c",
                    "metadata": {},
                    "execution_count": None,
                    "source": "",
                    "outputs": [
                        {
                            "output_type": "display_data",
                            "data": {
                                "text/html": html_payload,
                                "image/svg+xml": svg_payload,
                            },
                            "metadata": {},
                        }
                    ],
                },
            ],
        }
    )

    try:
        sanitize(document)
    except NotebookError:
        pass  # A resource-limit trip on pathological fuzzed input is expected.


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
