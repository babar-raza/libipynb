# Contributing to libipynb

Thank you for your interest in contributing to libipynb.

## Development Setup

```bash
# Clone the repository
git clone https://gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb.git
cd libipynb

# Create and activate a virtual environment
python -m venv .venv
.venv/Scripts/activate    # Windows
# source .venv/bin/activate  # Linux/macOS

# Install in editable mode with all development dependencies
pip install -e ".[test,reference]"
```

The `test` extra installs pytest, Hypothesis, and PyYAML. The `reference` extra
installs `nbformat` for interoperability testing.

## Running Tests

```bash
# Run the full test suite
.venv/Scripts/pytest tests/ -v

# Run a specific test category
.venv/Scripts/pytest tests/unit/ -v
.venv/Scripts/pytest tests/integration/ -v
.venv/Scripts/pytest tests/security/ -v
.venv/Scripts/pytest tests/property/ -v

# Run interoperability tests (requires nbformat)
.venv/Scripts/pytest tests/interoperability/ -v

# Run with coverage
.venv/Scripts/pytest tests/ --cov=libipynb --cov-report=term-missing
```

## Project Structure

```
src/libipynb/
  __init__.py          # Public API surface
  codec/               # Reader (load/loads) and writer (dump/dumps)
  model/               # NotebookDocument, Cell types, diff, merge, lifecycle
  validation/          # Profile-aware structural and semantic validation
  security/            # Resource limits, sanitization, trust/notary
  adapters/            # Export (Markdown, Python script) and execution
  analytics/           # Cell and output statistics
  cli/                 # Command-line interface
  diagnostics.py       # Diagnostic, ValidationResult types
  errors.py            # Exception hierarchy

tests/
  unit/                # Unit tests for individual modules
  integration/         # Integration tests for obligation contracts
  interoperability/    # Parity tests against nbformat
  security/            # Adversarial input and resource limit tests
  property/            # Hypothesis property-based tests
  package/             # Namespace and packaging tests
  fixtures/            # Test notebook files (valid, invalid, adversarial, corpus)
```

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for formatting and linting:

```bash
# Format code
ruff format .

# Check for lint issues
ruff check .

# Auto-fix lint issues where possible
ruff check . --fix
```

Configuration is in `pyproject.toml`:
- Target: Python 3.11
- Line length: 100 characters

## Type Checking

The project uses strict mypy:

```bash
mypy src/libipynb
```

All public APIs must have complete type annotations.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(model): add cell attachment support
fix(codec): handle missing nbformat field
test(security): add resource limit enforcement tests
docs(readme): add CLI usage examples
refactor(validation): extract profile selection logic
```

## Adding Tests

- Place unit tests in `tests/unit/`
- Use the fixtures in `tests/fixtures/` for test data
- For new fixture files, update `tests/fixtures/PROVENANCE.md` with the origin
- Property-based tests use Hypothesis and go in `tests/property/`

## Reporting Issues

When reporting a bug, include:
- Python version (`python --version`)
- libipynb version (`python -c "import libipynb; print(libipynb.__version__)"`)
- A minimal notebook file that reproduces the issue
- The full traceback
