"""Load a Jupyter Notebook and inspect its structure.

Usage:
    python examples/load_and_inspect.py
"""

from pathlib import Path

from libipynb import load

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "valid" / "code-and-markdown.ipynb"


def main() -> None:
    doc = load(FIXTURE)

    print(f"Notebook format: nbformat {doc.nbformat}.{doc.nbformat_minor}")
    print(f"Total cells:     {doc.cell_count}")
    print(f"Code cells:      {len(doc.code_cells)}")
    print(f"Markdown cells:  {len(doc.markdown_cells)}")
    print()

    # Access the typed cell objects
    for i, cell in enumerate(doc.cell_objects):
        source_preview = cell.source.replace("\n", "\\n")
        if len(source_preview) > 70:
            source_preview = source_preview[:67] + "..."
        print(f"  Cell {i}: [{cell.cell_type:>8}] {source_preview}")

    # Show metadata
    metadata = doc.metadata
    kernel = metadata.get("kernelspec", {})
    if kernel:
        print(f"\nKernel: {kernel.get('display_name', 'unknown')}")


if __name__ == "__main__":
    main()
