"""Operations over notebook output MIME bundles."""

from __future__ import annotations

from typing import Any

from .document import Output


def get_output_representation(output: dict[str, Any], mime_type: str) -> Any:
    return Output(output).get_representation(mime_type)


def add_output_representation(output: dict[str, Any], mime_type: str, value: Any) -> dict[str, Any]:
    Output(output).add_representation(mime_type, value)
    return output


def remove_output_mime_type(output: dict[str, Any], mime_type: str) -> bool:
    return Output(output).remove_representation(mime_type)
