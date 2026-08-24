"""Optional notebook analytics."""

from .notebook import (
    attachment_size_summary,
    average_source_length,
    cell_type_histogram,
    execution_errors,
    has_execution_errors,
    largest_cells,
    metadata_size_breakdown,
    notebook_byte_size,
    output_size_histogram,
    output_type_histogram,
)

__all__ = [
    "attachment_size_summary",
    "average_source_length",
    "cell_type_histogram",
    "execution_errors",
    "has_execution_errors",
    "largest_cells",
    "metadata_size_breakdown",
    "notebook_byte_size",
    "output_size_histogram",
    "output_type_histogram",
]
