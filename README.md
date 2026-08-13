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
- **Diff and merge** -- structural notebook diffing (with line-level hunks inside
  changed cell source) and three-way merge with conflict detection, both exposed
  from the CLI and installable as real git diff/merge drivers
- **Version conversion** -- upgrade and downgrade notebooks between nbformat 4.x
  minor versions
- **Cell editing** -- query, filter, and batch-edit cells by type, tag, or content
- **Cleanup** -- strip outputs, execution counts, and selected metadata, with an
  nbstripout-compatible default set and git clean-filter integration
  (`normalize --install`)
- **Attachments** -- manage cell-level MIME attachments with reference validation
- **Export adapters** -- convert notebooks to Markdown or Python scripts
- **CLI** -- 9 commands (`probe`, `inspect`, `validate`, `sanitize`, `upgrade`,
  `normalize`, `convert`, `diff`, `merge`), all with JSON output
- **Analytics** -- cell type histograms, output analysis, and execution error detection
- **Trust** -- HMAC-based notebook trust and signature management
- **Secret scanning** -- pattern-based detection of API keys, tokens, and credentials
  in cell source, outputs, and metadata (`libipynb.security.scan_for_secrets`)

## Compared to the wider notebook toolchain

libipynb is being built out as one library covering what teams otherwise reach for
several separate tools for. Current state, honestly:

- ✅ shipped and covered by real tests in this repository
- 🚧 partially shipped -- some of the capability exists, some is designed but not built
- ⛔ not yet implemented

A ✅ next to `nbstripout`/`nbdime` specifically means a real, byte-for-byte
oracle comparison was run against the actual installed tool (`libipynb[oracle]`)
and passed, with every intentional divergence explicitly proven and documented
rather than assumed -- see `tests/oracle/test_nbstripout_parity.py` and
`test_nbdime_parity.py`. `nbconvert`/`papermill` are not yet compared this way
(the capability they'd be compared against doesn't exist yet -- see Roadmap);
`tests/oracle/`'s fixtures for them still skip cleanly when the tool isn't
installed and import-check when it is, per `plans/full-parity-plan.md` Gate G8.

| Capability | Reference tool | Status | Notes |
|---|---|---|---|
| Programmatic read/write/model | `nbformat` | ✅ | Independent implementation; tested for interoperability against real `nbformat` when the `reference` extra is installed |
| Strip outputs for version control | `nbstripout` | ✅ | nbstripout-compatible default strip set, `--keep-output`/`--keep-count`/`--extra-keys`/`--keep-metadata-keys`, `[tool.libipynb.normalize]` config, and git clean-filter install/uninstall/status (fail-closed on filter failure, matching nbstripout's own default). **Oracle-verified** (`tests/oracle/test_nbstripout_parity.py`, real `nbstripout` installed): output/metadata/execution-count stripping matches byte-for-byte, with two documented, intentional divergences -- libipynb never rewrites cell IDs (nbstripout regenerates them by default) or the `source`/output-text serialization form (string vs. list-of-lines; both valid nbformat) |
| Structural diff/merge | `nbdime` | ✅ | Cell-identity diff with line-level source hunks, three-way merge with explicit conflict reporting, git diff/merge driver integration (`diff --install-git`); no visual/web diff viewer yet. **Oracle-verified** (`tests/oracle/test_nbdime_parity.py`, real `nbdime` installed): no-conflict merges agree; on a genuine conflict, real `nbmerge`'s default strategy splices literal `<<<<<<<`/`=======`/`>>>>>>>` markers into cell source -- libipynb never does this, by design, now proven against the real tool rather than assumed. `nbmerge --merge-strategy use-base` reaches the same base-wins *value* as libipynb but resolves silently (exit 0, no conflict signal); libipynb always surfaces the conflict via `MergeReport` even when the resolved value matches |
| Headless execution | `jupyter nbconvert --execute` | 🚧 | Lightweight subprocess-based execution adapter only (Python-only, no rich outputs, no write-back into the notebook); a real Jupyter-kernel-protocol engine is designed but **not yet implemented** -- see Roadmap |
| Parameterized pipelines | `papermill` | ⛔ | **Not yet implemented** -- see Roadmap |

### Roadmap

Real Jupyter kernel-protocol execution (multi-language, rich outputs) and
papermill-style parameter injection are designed in `plans/full-parity-plan.md`
but intentionally not implemented yet: both widen the code-execution attack
surface of this library, and that plan's own Gate G6 requires an explicit,
dated maintainer security sign-off before implementation starts, not just
before shipping. See that plan for the full design and current status.

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

## Platform support

CI (`.gitlab-ci.yml`) runs exclusively on Linux (`python:3.11`/`3.12`/`3.13-slim`
containers). **Windows and macOS are not covered by CI** and are best-effort only --
this is a deliberate, recorded scope limitation (see `plans/full-parity-plan.md`
LIBIPYNB-P9), not a silent gap. The library and CLI are pure Python with no
platform-conditional code paths outside `adapters/execute.py`'s POSIX-only
`max_memory_bytes` enforcement (which refuses rather than silently no-ops on
Windows) and the `fuzz/` harnesses (Linux-only, outside `tests/` and never
required for the normal suite). If you hit a Windows/macOS-specific issue,
please report it -- it has not been exercised by an automated gate.

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
- **`NotebookVersion`** -- immutable version descriptor (`major`, `minor`);
  `upgrade()`, `downgrade()`, and `plan_downgrade()` are module-level functions
  in `libipynb.model.lifecycle` that operate on a document, not methods on
  this class
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
- **`execute_notebook()`** -- opt-in execution adapter with result tracking.
  **Still not a full sandbox**, but narrower than a bare subprocess: by
  default it runs in a fresh temporary working directory (`isolate_cwd`,
  cleaned up after), with a minimal environment instead of the caller's
  full one (`isolate_env`, extend via `extra_env`), and captured output is
  capped at 10 MiB (`max_output_bytes`). A memory limit (`max_memory_bytes`)
  is enforced on POSIX only -- requesting one on Windows raises rather than
  silently running unlimited. CPU-time limiting and network-access denial
  are **not** implemented. Never called by `load`/`validate`/`diff`/
  `upgrade`/`save` -- it is the sole, explicit entry point into code
  execution, requires `acknowledge_unsandboxed=True`, and should only be
  pointed at notebooks you already trust to execute.

### `libipynb.analytics` -- Notebook Analytics

- `cell_type_histogram(doc)` -- count cells by type
- `output_type_histogram(doc)` -- count outputs by type
- `has_execution_errors(doc)` -- check for error outputs
- `average_source_length(doc)` -- mean source length across cells

## CLI

libipynb installs a command-line tool with 11 subcommands:

```bash
# Probe whether a file is a valid .ipynb
libipynb probe notebook.ipynb

# Inspect notebook structure
libipynb inspect notebook.ipynb

# Validate a notebook (exit 0 = valid, exit 1 = invalid)
libipynb validate notebook.ipynb

# Scan for active content and security hazards (report-only, no mutation)
libipynb sanitize notebook.ipynb

# Upgrade to nbformat 4.5 and print the conversion ledger
libipynb upgrade notebook.ipynb -o upgraded.ipynb

# Preview what would be stripped, without writing anything (--dry-run and
# -o are mutually exclusive in effect: with --dry-run, -o is ignored)
libipynb normalize notebook.ipynb --dry-run

# Actually strip outputs, execution counts, and nbstripout-compatible
# metadata (signature/widgets/ExecuteTime/collapsed/execution/...)
libipynb normalize notebook.ipynb -o cleaned.ipynb

# Register libipynb as a git clean filter for *.ipynb (nbstripout --install
# equivalent); --uninstall / --status also available; --keep-output,
# --keep-count, --extra-keys, and --keep-metadata-keys tune what's stripped,
# also configurable via [tool.libipynb.normalize] in pyproject.toml
libipynb normalize --install

# Convert between nbformat 4.x minor versions (accepts data loss on downgrade)
libipynb convert notebook.ipynb --target 4.0 --accept-loss -o downgraded.ipynb

# Diff two notebooks by cell identity (exit 0 = no changes, exit 1 = changes found)
libipynb diff before.ipynb after.ipynb

# Three-way merge by cell identity (exit 0 = no conflicts, exit 1 = conflicts
# found; the merged notebook is still written either way -- unresolved
# fields keep the base's value, never either side's conflicting value)
libipynb merge base.ipynb ours.ipynb theirs.ipynb -o merged.ipynb

# Register libipynb as git's diff AND merge driver for *.ipynb (nbdime
# 'config-git --enable' equivalent) -- plain `git diff`/`git merge` then
# transparently use libipynb for .ipynb files; --uninstall-git/--git-status
# also available
libipynb diff --install-git

# Report structural analytics: cell/output type histograms, execution
# errors, average source length
libipynb analytics notebook.ipynb

# Sign, verify, or revoke content-addressed trust using a persistent
# (SQLite) HMAC store; the secret is read from an environment variable,
# never accepted as a CLI argument, so it never lands in shell history
export LIBIPYNB_TRUST_SECRET="$(openssl rand -hex 32)"
libipynb trust notebook.ipynb --sign --store trust.db --secret-env LIBIPYNB_TRUST_SECRET
libipynb trust notebook.ipynb --verify --store trust.db --secret-env LIBIPYNB_TRUST_SECRET
```

All commands output JSON to stdout (upgrade/normalize/convert/merge write
the ledger to stderr instead when the converted/merged notebook itself is
streamed to stdout, i.e. when `-o/--output` is omitted):

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
