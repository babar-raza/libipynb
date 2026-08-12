# libipynb

A standalone, production-quality Python library for reading, writing, validating,
and manipulating Jupyter Notebook files (`.ipynb`). Built for correctness, security,
and nbformat 4.0--4.5 fidelity.

<!-- Badges (uncomment when published)
[![PyPI version](https://img.shields.io/pypi/v/libipynb)](https://pypi.org/project/libipynb/)
[![Python](https://img.shields.io/pypi/pyversions/libipynb)](https://pypi.org/project/libipynb/)
[![License](https://img.shields.io/pypi/l/libipynb)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)]()
-->

## Features

- **Load and dump** -- read and write `.ipynb` files with full round-trip fidelity
- **Typed model** -- `NotebookDocument`, `Cell`, `CodeCell`, `MarkdownCell`, and
  typed output objects instead of raw dicts
- **Validation** -- structural and semantic validation against nbformat 4.0--4.5
  with configurable profiles and rich diagnostics
- **Sanitization** -- detect and handle active content (scripts, iframes, SVG) in
  cell outputs with report, remove, or quarantine modes
- **Resource limits** -- configurable caps on input size, nesting depth, and entry
  count to prevent resource exhaustion
- **Diff and merge** -- structural notebook diffing and three-way merge with
  conflict detection
- **Version conversion** -- upgrade and downgrade notebooks between nbformat 4.x
  minor versions
- **Cell editing** -- query, filter, and batch-edit cells by type, tag, or content
- **Cleanup** -- strip outputs, normalize metadata, and remove empty cells
- **Attachments** -- manage cell-level MIME attachments with reference validation
- **Export adapters** -- convert notebooks to Markdown or Python scripts
- **CLI** -- `libipynb validate`, `libipynb inspect`, and `libipynb probe` commands
- **Analytics** -- cell type histograms, output analysis, and execution error detection
- **Trust** -- HMAC-based notebook trust and signature management

## Installation

```bash
pip install libipynb
```

Requires Python 3.11 or later. The only runtime dependency is `jsonschema`.

For development (tests, reference interoperability):

```bash
pip install libipynb[test,reference]
```

## Quick Start

### Load and inspect a notebook

```python
from libipynb import load

doc = load("analysis.ipynb")
print(f"Format: nbformat {doc.nbformat}.{doc.nbformat_minor}")
print(f"Cells:  {doc.cell_count}")

for cell in doc.cell_objects:
    print(f"  [{cell.cell_type}] {cell.source[:60]!r}")
```

### Validate a notebook

```python
from libipynb import validate

result = validate("analysis.ipynb")
if result.is_valid:
    print("Notebook is valid")
else:
    for diagnostic in result.errors:
        print(f"  {diagnostic.code}: {diagnostic.message}")
```

### Sanitize untrusted output

```python
from libipynb import load, sanitize

doc = load("untrusted.ipynb")
report = sanitize(doc)
for finding in report.findings:
    print(f"  {finding.media_type} at {finding.path}: {', '.join(finding.hazards)}")
```

### Round-trip a notebook

```python
from libipynb import load, dump

doc = load("input.ipynb")
# ... modify doc ...
dump(doc, "output.ipynb")
```

## Supported Versions

libipynb supports **nbformat 4.0 through 4.5**:

| nbformat minor | Cell IDs | Key features |
|---|---|---|
| 4.0 | No | Base notebook format |
| 4.1 | No | Attachment support |
| 4.2 | No | Raw cell `format` field |
| 4.3 | No | Cell-level metadata additions |
| 4.4 | No | Widget state in notebook metadata |
| 4.5 | Yes | Mandatory cell IDs (8-64 char `[a-zA-Z0-9_-]`) |

Version detection is automatic. Notebooks without explicit version fields are handled
gracefully with recovery actions recorded on the document.

## API Overview

### `libipynb.codec` -- Reading and Writing

| Function | Description |
|---|---|
| `load(source)` | Load a notebook from a file path, string, bytes, or stream |
| `loads(text)` | Load a notebook from a JSON string |
| `dump(doc, dest)` | Write a notebook to a file path or stream |
| `dumps(doc)` | Serialize a notebook to a JSON string |
| `probe(source)` | Detect whether a source is a valid `.ipynb` file |
| `roundtrip(source, dest)` | Load and re-serialize with minimal diff |

### `libipynb.model` -- Document Model

- **`NotebookDocument`** -- mutable typed view over a notebook with cell access,
  search (`find_cells`), mutation (`add_cell`, `remove_cell`, `clear_outputs`),
  and cleanup
- **`Cell`**, **`CodeCell`**, **`MarkdownCell`**, **`RawCell`** -- typed cell views
  with `source`, `cell_type`, `id`, `metadata`, `outputs`, `tags`
- **`NotebookVersion`** -- version descriptor with `upgrade()` and `downgrade()`
- **`diff_notebooks()`** / **`merge_notebooks()`** -- structural diff and three-way merge
- **`edit_cells()`** -- batch cell editing with query and operation objects
- **`cleanup()`** -- normalize and strip notebook content

### `libipynb.validation` -- Validation

- **`validate(source)`** -- profile-aware validation returning `ValidationResult`
  with typed `Diagnostic` objects (code, message, severity, location)
- **`validate_notebook_schema(mapping)`** -- raw schema validation
- Profiles: `declared` (default, uses the notebook's own version), `current` (strict 4.5)

### `libipynb.security` -- Security

- **`sanitize(doc)`** -- detect/remove/quarantine active content in outputs
- **`SanitizationPolicy`** -- configurable mode (`LOSSLESS`, `REMOVE`, `QUARANTINE`)
  and active MIME type set
- **`NotebookResourceLimits`** -- caps on input size (64 MB), output size (512 MB),
  decompressed size (2 GB), entries (100K), nesting depth (64)
- **`HmacNotebookNotary`** -- HMAC-based trust signatures

### `libipynb.adapters` -- Export and Execution

- **`MarkdownExporter`** / **`PythonScriptExporter`** -- convert notebooks to
  Markdown or `.py` files
- **`execute_notebook()`** -- execution adapter with result tracking

### `libipynb.analytics` -- Notebook Analytics

- `cell_type_histogram(doc)` -- count cells by type
- `output_type_histogram(doc)` -- count outputs by type
- `has_execution_errors(doc)` -- check for error outputs
- `average_source_length(doc)` -- mean source length across cells

## CLI

libipynb installs a command-line tool:

```bash
# Validate a notebook (exit 0 = valid, exit 1 = invalid)
libipynb validate notebook.ipynb

# Inspect notebook structure
libipynb inspect notebook.ipynb

# Probe whether a file is a valid .ipynb
libipynb probe notebook.ipynb
```

All commands output JSON to stdout:

```bash
$ libipynb validate notebook.ipynb
{"diagnostics": [], "valid": true}

$ libipynb inspect notebook.ipynb
{"cell_count": 12, "nbformat": 4, "nbformat_minor": 5}
```

## nbformat Interoperability

libipynb is designed as a standalone replacement for common `nbformat` operations.
It does **not** depend on `nbformat` at runtime, but it validates against the same
official nbformat 4.x JSON schemas.

When `nbformat` is installed (via the `reference` extra), the test suite runs
interoperability checks that verify:

- Round-trip fidelity: `nbformat.read` and `libipynb.load` produce equivalent
  document structures
- Validation agreement: both libraries accept and reject the same notebooks
- Version detection: both libraries detect the same nbformat version

This ensures libipynb can serve as a drop-in replacement in pipelines that
previously used `nbformat` directly.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and
code style guidelines.

## License

[Apache-2.0](LICENSE)
