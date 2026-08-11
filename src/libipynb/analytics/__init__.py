"""Optional notebook analytics."""

from .notebook import (
    average_source_length,
    cell_type_histogram,
    has_execution_errors,
    output_type_histogram,
)

__all__ = [
    "average_source_length",
    "cell_type_histogram",
    "has_execution_errors",
    "output_type_histogram",
]
