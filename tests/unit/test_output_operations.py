"""Direct tests for model/output.py wrapper functions."""

from __future__ import annotations

from libipynb.model.output import (
    add_output_representation,
    get_output_representation,
    remove_output_mime_type,
)


def _display_data(mime: str, value: object) -> dict:
    return {
        "output_type": "display_data",
        "data": {mime: value},
        "metadata": {},
    }


def test_get_output_representation() -> None:
    output = _display_data("text/plain", "hello")
    assert get_output_representation(output, "text/plain") == "hello"


def test_get_output_representation_missing() -> None:
    output = _display_data("text/plain", "hello")
    assert get_output_representation(output, "text/html") is None


def test_add_output_representation() -> None:
    output = _display_data("text/plain", "hello")
    result = add_output_representation(output, "text/html", "<b>hello</b>")
    assert result["data"]["text/html"] == "<b>hello</b>"
    assert result is output


def test_remove_output_mime_type() -> None:
    output = _display_data("text/plain", "hello")
    assert remove_output_mime_type(output, "text/plain") is True
    assert "text/plain" not in output["data"]


def test_remove_output_mime_type_missing() -> None:
    output = _display_data("text/plain", "hello")
    assert remove_output_mime_type(output, "text/html") is False
