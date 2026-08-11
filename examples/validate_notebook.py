"""Validate a Jupyter Notebook and report diagnostics.

Usage:
    python examples/validate_notebook.py
"""

from pathlib import Path

from libipynb import validate

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def validate_file(path: Path) -> None:
    """Validate a single notebook and print the result."""
    result = validate(path)
    status = "VALID" if result.is_valid else "INVALID"
    print(f"  {path.name}: {status}")
    for diagnostic in result:
        print(f"    [{diagnostic.severity.upper()}] {diagnostic.code}: {diagnostic.message}")


def main() -> None:
    # Validate a known-good notebook
    print("Valid notebooks:")
    for path in sorted((FIXTURES_DIR / "valid").glob("*.ipynb")):
        validate_file(path)

    print()

    # Validate notebooks with known issues
    print("Invalid notebooks:")
    for path in sorted((FIXTURES_DIR / "invalid").glob("*.ipynb")):
        validate_file(path)


if __name__ == "__main__":
    main()
