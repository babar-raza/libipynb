# Architecture

This document describes how `libipynb` is put together: the module map, the
dependency boundary between the core package and its optional extras, the
trust model for the two execution engines, and the shape of the data/validation
layer. It consolidates information that already lives in the source, tests,
and `SECURITY.md`/`README.md` -- it does not introduce new decisions.

## Module map

```
src/libipynb/
├── codec/          reader.py, writer.py
├── model/          attachments.py, cleanup.py, diff.py, document.py,
│                   editor.py, lifecycle.py, merge.py, metadata.py, output.py
├── validation/     rules.py, schema.py, validator.py, schemas/*.json
├── security/       limits.py, sanitizer.py, secrets.py, trust.py
├── execution/      exceptions.py, options.py, protocol.py, results.py
├── adapters/       execute.py, export.py, jupyter_execute.py
├── cli/            main.py, __main__.py
├── analytics/      notebook.py
├── _internal/      paths.py, probe.py
├── diagnostics.py
└── errors.py
```

- **`codec/`** -- JSON I/O boundary. `reader.py` parses `.ipynb` source
  (path, string, bytes, or stream) into the preservation-first backing
  mapping, with duplicate-key detection and resource-limit enforcement
  during parsing. `writer.py` serializes back out, using an atomic
  write-to-temp-then-rename pattern for file destinations.
- **`model/`** -- the typed document model and everything that operates on
  it: `document.py` (`NotebookDocument`, `Cell`/`CodeCell`/`MarkdownCell`/
  `RawCell`, `MimeBundle`), `editor.py` (batch cell editing via query/operation
  objects), `diff.py`/`merge.py` (structural diff and three-way merge by cell
  identity), `lifecycle.py` (`NotebookVersion`, `upgrade`/`downgrade`/
  `plan_downgrade`), `attachments.py` (attachment management), `cleanup.py`
  (normalization/stripping), `metadata.py`, `output.py`.
- **`validation/`** -- schema and semantic validation. `schema.py` runs
  digest-verified official nbformat JSON schemas (`validation/schemas/*.json`)
  via `jsonschema`; `rules.py` layers hand-written semantic checks (known
  cell/output types, profile selection) on top; `validator.py` is the
  profile-aware entry point (`declared` vs. `current`) that composes both.
- **`security/`** -- `limits.py` (`NotebookResourceLimits`, enforced during
  parsing), `sanitizer.py` (active-content detection/removal/quarantine),
  `secrets.py` (secret scanning), `trust.py` (`HmacNotebookNotary` HMAC-based
  trust signatures).
- **`execution/` + `adapters/`** -- optional execution backends and export
  adapters, kept out of the core import graph (see the dependency boundary
  section below). `execution/` is the public, backend-neutral surface
  (`ExecutionOptions`, `ExecutionResult`, `CellExecutionRecord`, the
  `NotebookExecutor` protocol) for the real Jupyter-kernel-protocol engine
  implemented in `adapters/jupyter_execute.py::LocalJupyterExecutor`.
  `adapters/execute.py::execute_notebook` is the separate, dependency-free
  subprocess execution adapter. `adapters/export.py` holds `HtmlExporter`
  (shells out to `python -m nbconvert`) and `JupytextExporter` (imports
  `jupytext` directly).
- **`cli/`** -- `main.py` implements the `libipynb` command (probe, inspect,
  validate, sanitize scan, upgrade/downgrade, strip, git filter
  install/uninstall, diff, merge, git diff/merge driver install/uninstall,
  execute, analytics, trust sign/verify/revoke). It is the one place in the
  core package that shells out to `git`.
- **`_internal/`** -- shared, dependency-free helpers used across layers
  without creating cross-layer import cycles: `paths.py` (filename-safety
  check shared by `model/attachments.py` and `adapters/export.py`, living
  here specifically so neither layer imports the other), `probe.py`
  (`ProbeResult`).
- **`analytics/`** -- `notebook.py`: structural analytics (cell/output type
  histograms, execution-error detection, average source length). No
  third-party dependency.

`diagnostics.py` (shared `Diagnostic`/`ValidationResult` types) and
`errors.py` (the exception hierarchy) sit at the top level since they're used
across nearly every other package.

## Core / optional-extras dependency boundary

This is enforced by a static AST-based check,
`tests/unit/test_import_boundary.py::test_no_source_file_imports_an_oracle_or_exec_extra_tool`,
which parses every `.py` file under `src/libipynb/` with `ast` (not a runtime
import check, so the boundary holds even for code paths the test suite never
executes) and fails if any file imports a forbidden top-level module.

**Forbidden everywhere in `src/libipynb/`, no exceptions:**
`nbdime`, `nbconvert`, `papermill`, `nbstripout`.

**Forbidden everywhere except one named file:** `jupyter_client`, `nbclient`.
The sole, scoped exception is `src/libipynb/adapters/jupyter_execute.py` --
the real kernel-protocol execution engine. The exception is keyed on the file
*path*, not just the module name: the test suite explicitly asserts that the
same imports are still flagged in any other file (e.g. `model/document.py`,
`adapters/execute.py`), and that the exception does not widen to cover
`nbdime`/`nbconvert`/`papermill`/`nbstripout` even inside
`jupyter_execute.py` itself.

**Not on the forbidden list at all:** `nbformat`. It is a declared
`reference`/`test`-extra dependency, used by `tests/interoperability/` and
other test-only oracle comparisons, and also needed inside
`jupyter_execute.py` to build the execution-time notebook representation
`nbclient` expects. `jsonschema` is likewise never forbidden -- it is the
one runtime dependency of the core package itself (used by
`validation/schema.py`).

Net result, stated plainly:

- **Core** (`import libipynb` with no extras installed) has **zero**
  third-party runtime dependencies except `jsonschema`.
- **`nbclient`/`jupyter_client`** (real Jupyter-kernel execution) are
  importable from exactly one file, `adapters/jupyter_execute.py`, gated
  behind the `exec` extra (`pip install libipynb[exec]`).
- **`nbconvert`/`jupytext`** (export) are importable only from
  `adapters/export.py`, gated behind the `export` extra. `nbconvert` itself
  is never imported as a Python module even there -- `HtmlExporter` shells
  out to `python -m nbconvert` as a subprocess instead, so `nbconvert`'s
  presence in `test_import_boundary.py`'s forbidden list is never actually
  violated by `adapters/export.py`; only `jupytext` is imported directly
  (it is not on the forbidden list).
- **`nbformat`/`nbdime`/`nbstripout`/`papermill`** (oracle/reference
  comparison) are used only from the test suite (`tests/oracle/`,
  `tests/interoperability/`, and other test-only modules), gated behind the
  `oracle`/`reference`/`test` extras in `pyproject.toml`, and never imported
  by `src/libipynb/` (with the single documented exception of `nbformat`
  inside `jupyter_execute.py`, described above).

## Execution trust boundary

`libipynb` ships two independent, both fully opt-in execution engines. Neither
is a sandbox, and both are disclosed as such in `SECURITY.md` and `README.md`:

- **`adapters/execute.py::execute_notebook`** -- the dependency-free
  subprocess engine, stdlib only, no extra required. Runs one-shot with
  basic OS-level limits: by default a fresh temporary working directory
  (`isolate_cwd`) and a minimal environment (`isolate_env`), captured output
  capped at 10 MiB (`max_output_bytes`), and an optional memory limit
  (`max_memory_bytes`, POSIX only -- requesting one on Windows raises rather
  than silently running unlimited). CPU-time limiting and network-access
  denial are not implemented.
- **`adapters/jupyter_execute.py::LocalJupyterExecutor`** -- the real
  Jupyter-kernel-protocol engine (`libipynb[exec]`). It launches and
  communicates with an actual, longer-lived `ipykernel` process via the
  Jupyter messaging protocol, executing every cell against that live kernel
  rather than running once and exiting. `SECURITY.md` and `README.md` both
  call this out as the more security-relevant of the two engines, since it
  is a fuller, stateful execution environment rather than a one-shot
  subprocess.

Both engines run **trusted local code, not untrusted code in a sandbox**: the
kernel or subprocess runs with the calling process's own permissions --
it can read/write files, start other processes, use the network, and inspect
environment variables to the same extent the calling user could. Per-cell/
per-run timeouts and kernel interruption are operational controls against a
hung cell, not an isolation boundary.

Both require an explicit, affirmative opt-in before running anything --
`acknowledge_unsandboxed=True` on the Python API (`execute_notebook`'s
keyword argument, and the equivalent field on `ExecutionOptions` for
`LocalJupyterExecutor`), or `--acknowledge-unsandboxed` on the CLI -- so
unsandboxed execution is never invoked by accident. Only execute notebooks
you already trust; true untrusted execution needs an external isolation
boundary (container, VM, or a purpose-built remote execution service), which
is why `libipynb.execution.NotebookExecutor` is defined as a backend-neutral
`Protocol` -- so such a backend could implement it later without changing
calling code -- even though none ships today.

## Data-model / validation architecture

`NotebookDocument` (`model/document.py`) wraps a single raw,
preservation-first backing `dict` (exposed via its `raw` property). Typed
cell and output wrappers (`Cell`, `CodeCell`, `MarkdownCell`, `RawCell`,
`MimeBundle`) hold a reference to a sub-mapping of that same backing
structure rather than copying or replacing it -- so unknown or
future/vendor-extension fields that the typed wrappers don't model explicitly
still round-trip untouched through load → edit → save.

Validation is layered, not a single runtime call into a generic
schema-validation service:

- `validation/schema.py` runs structural validation against **vendored**
  copies of the official nbformat 4.0-4.5 JSON schemas
  (`src/libipynb/validation/schemas/nbformat.v4.*.schema.json`), each
  checked against a recorded SHA-256 digest (`SCHEMA_DIGESTS`) so a vendored
  copy silently drifting from the upstream `nbformat` project's schema would
  be caught. This is the one place `jsonschema` is imported directly.
- `validation/rules.py` layers hand-written semantic rules on top (known
  cell/output type checks, profile selection for `declared` vs. `current`).
- `validation/validator.py` is the profile-aware public entry point
  (`validate()`) that composes schema and semantic diagnostics into one
  `ValidationResult`; it does not import `jsonschema` itself -- that
  dependency stays encapsulated inside `schema.py`, one file away from the
  API surface callers actually use.

## See also

- `SECURITY.md` -- full security disclosure, resource limits, sanitization,
  and the execution trust-boundary language this document summarizes.
- `README.md` -- API overview, CLI reference, and installation/extras
  instructions.
- `tests/unit/test_import_boundary.py` -- the enforced, self-testing source
  of truth for the dependency boundary described above.
