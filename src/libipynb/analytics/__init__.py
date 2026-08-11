"""Optional notebook analytics."""

from .notebook import (
    ipynb_average_source_length,
    ipynb_cell_type_histogram,
    ipynb_has_execution_errors,
    ipynb_output_type_histogram,
)

__all__ = [
    "ipynb_average_source_length",
    "ipynb_cell_type_histogram",
    "ipynb_has_execution_errors",
    "ipynb_output_type_histogram",
]
