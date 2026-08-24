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
- **Export adapters** -- convert notebooks to Markdown, Python scripts, any
  format the real `nbconvert` CLI supports -- HTML, slides, PDF, WebPDF, ...
  (`NbconvertExporter`, shells out to `nbconvert`, `libipynb[export]`; see
  [Export formats](#export-formats) below for the PDF/slides caveat), or
  to/from Jupytext's paired text formats (`JupytextExporter`,
  `libipynb[export]`)
- **Execution** -- two opt-in engines: a dependency-free subprocess adapter, and a
  real local Jupyter-kernel-protocol engine (`libipynb[exec]`) with rich outputs,
  sync/async APIs, and structured results (`libipynb.execution`)
- **Parameters** -- Papermill-compatible parameter injection into a tagged
  `parameters` cell (`inject_parameters()`/`libipynb run`) -- same tag
  convention, same generated Python source, oracle-verified byte-for-byte
  against real `papermill` for every supported value type
- **CLI** -- 13 commands (`probe`, `inspect`, `validate`, `sanitize`, `upgrade`,
  `normalize`, `convert`, `diff`, `merge`, `execute`, `run`, `analytics`,
  `trust`), all with JSON output
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

A ✅ in this table means a real, byte-for-byte oracle comparison was run
against the actual installed reference tool (`libipynb[oracle]`) and passed,
with every intentional divergence explicitly proven and documented rather
than assumed -- see `tests/oracle/test_nbstripout_parity.py`,
`test_nbdime_parity.py`, `test_nbclient_execution_parity.py`, and
`test_papermill_parity.py`. `tests/oracle/`'s fixtures skip cleanly when a
given reference tool isn't installed and import-check when it is, per
`plans/full-parity-plan.md` Gate G8.

| Capability | Reference tool | Status | Notes |
|---|---|---|---|
| Programmatic read/write/model | `nbformat` | ✅ | Independent implementation; tested for interoperability against real `nbformat` when the `reference` extra is installed |
| Strip outputs for version control | `nbstripout` | ✅ | nbstripout-compatible default strip set, `--keep-output`/`--keep-count`/`--extra-keys`/`--keep-metadata-keys`, `[tool.libipynb.normalize]` config, and git clean-filter install/uninstall/status (fail-closed on filter failure, matching nbstripout's own default). **Oracle-verified** (`tests/oracle/test_nbstripout_parity.py`, real `nbstripout` installed): output/metadata/execution-count stripping matches byte-for-byte, with two documented, intentional divergences -- libipynb never rewrites cell IDs (nbstripout regenerates them by default) or the `source`/output-text serialization form (string vs. list-of-lines; both valid nbformat) |
| Structural diff/merge | `nbdime` | ✅ | Cell-identity diff with line-level source hunks, three-way merge with explicit conflict reporting, git diff/merge driver integration (`diff --install-git`); no visual/web diff viewer yet. **Oracle-verified** (`tests/oracle/test_nbdime_parity.py`, real `nbdime` installed): no-conflict merges agree; on a genuine conflict, real `nbmerge`'s default strategy splices literal `<<<<<<<`/`=======`/`>>>>>>>` markers into cell source -- libipynb never does this, by design, now proven against the real tool rather than assumed. `nbmerge --merge-strategy use-base` reaches the same base-wins *value* as libipynb but resolves silently (exit 0, no conflict signal); libipynb always surfaces the conflict via `MergeReport` even when the resolved value matches |
| Headless execution | `jupyter nbconvert --execute` | ✅ | Real Jupyter-kernel-protocol engine (`libipynb[exec]`, `libipynb.execution.LocalJupyterExecutor`, backed by `nbclient`) alongside the original dependency-free subprocess adapter (`libipynb.adapters.execute_notebook`) -- neither replaces the other. Rich outputs (`display_data`/`execute_result`/multi-MIME/`error`), sync and async APIs, per-cell timeouts with interrupt, skip-tagged cells, non-mutating-by-default write-back. **Oracle-verified** (`tests/oracle/test_nbclient_execution_parity.py`, real `nbconvert --execute` installed): deterministic cell outputs and execution-count sequencing agree exactly, once nbformat's own string-vs-list-of-lines text-serialization form is normalized (the same already-documented divergence found for `nbstripout`). Not language-restricted the way the subprocess adapter is, but only Python/`ipykernel` is actually tested here (no R/Julia kernel installed in this environment) -- see Gate G6 sign-off, `plans/full-parity-plan.md` §7 |
| Parameterized pipelines | `papermill` | ✅ | Papermill-compatible parameter injection (`inject_parameters()`/`libipynb run`) -- same `parameters`/`injected-parameters` tag convention, same generated Python source. **Oracle-verified** (`tests/oracle/test_papermill_parity.py`, real `papermill` installed): generated source matches byte-for-byte for every supported value type. Python-only, and explicitly rejects an unsupported parameter type rather than real papermill's silent stringify-fallback -- both documented, deliberate divergences; see `libipynb.model.parameters`'s module docstring for the full list |

### Roadmap

Multi-language kernel output-quirk handling (`plans/full-parity-plan.md`
`P4a-2`) remains **not yet implemented** -- the execution engine's
architecture does not block it (non-Python kernels already run through the
same real kernel protocol; no language allowlist exists in
`LocalJupyterExecutor` the way the subprocess adapter has one), but it has no
dedicated work or a reproducible non-Python CI fixture yet. See that plan for
the full design and current status.

### Security posture: notebook execution is not sandboxed

Both execution engines (`libipynb.adapters.execute_notebook` and
`libipynb.execution.LocalJupyterExecutor`) run **trusted local code**, not
untrusted code in a sandbox. The kernel or subprocess runs with this
process's own permissions: it can read/write files, start other processes,
use the network, and inspect environment variables to the same extent the
calling user could. Per-cell/per-run timeouts and kernel interruption are
operational controls against a hung cell, not an isolation boundary;
disabling stdin reduces interactive blocking, not attacker capability. Both
engines require an explicit `acknowledge_unsandboxed=True` (Python API) or
`--acknowledge-unsandboxed` (CLI) before running anything, precisely so this
is never invoked by accident. **Only execute notebooks you already trust.**
True untrusted execution needs an external isolation boundary (container,
VM, or a purpose-built remote execution service) -- `libipynb.execution.
NotebookExecutor` is a backend-neutral protocol specifically so such a
backend could implement it later without changing calling code, not because
one ships today.

## Installation

```bash
pip install libipynb
```

Requires Python 3.11 or later. The only runtime dependency is `jsonschema`.

For development (tests, reference interoperability):

```bash
pip install libipynb[test,reference]
```

For real Jupyter-kernel execution (`libipynb.execution.LocalJupyterExecutor`,
`libipynb execute`):

```bash
pip install "libipynb[exec]"
```

This installs `jupyter_client`/`nbclient` and `ipykernel` (a real kernel
implementation), but a kernel still has to be *registered* before
`jupyter_client` can find it: `python -m ipykernel install --user`. Everything
else in libipynb, including the original dependency-free
`libipynb.adapters.execute_notebook` subprocess adapter, works with none of
this installed.

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
dump(doc, "output.ipynb", profile="declared")  # preserves the loaded notebook's own version
```

`profile="declared"` preserves whatever nbformat version `input.ipynb` already
declares (what "round-trip" means here). Omitting `profile` targets nbformat
4.5 specifically and requires the source to already be 4.5 — call `upgrade()`
first if it isn't (see [Supported Versions](#supported-versions) below); this
is a deliberate safety rail, not an oversight — see `dump`/`dumps` in the API
table above for why.

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

**nbformat 3 and earlier are not supported (LIBIPYNB-Q34, decision-gated
investigation, not an oversight):** nbformat 4 replaced nbformat 3 as
Jupyter's default notebook format in 2015 -- over a decade before this
writing -- and every notebook produced by any actively maintained Jupyter
installation since has been nbformat 4.x; a genuinely still-in-use v3
notebook is now vanishingly rare. `nbformat` itself (this project's own
schema/oracle reference) already ships and maintains the v1→v2→v3→v4
upgrade chain for exactly this legacy case, so re-implementing it natively
here would duplicate, not add, coverage. If you have an old v3 notebook,
upgrade it once with the reference implementation before using libipynb:

```python
import nbformat
nb = nbformat.read("old-notebook.ipynb", as_version=4)
nbformat.write(nb, "old-notebook.ipynb")  # now nbformat 4.x, usable by libipynb
```

(`pip install nbformat` -- already a transitive dependency of this
project's own `test`/`reference` extras, or install it standalone.)

## Platform support

The internal GitLab mirror's CI (`.gitlab-ci.yml`) runs exclusively on Linux
(`python:3.11`/`3.12`/`3.13-slim` containers). GitHub Actions
(`.github/workflows/ci.yml`, LIBIPYNB-Q26) additionally runs a Windows and
macOS leg (Python 3.12, the core `unit`/`integration`/`security` suite --
not the slower property suite or the Linux-only `fuzz`/oracle/exec-heavy
tiers) on every push and pull request, superseding the scope limitation
LIBIPYNB-P9 originally recorded here. The library and CLI are pure Python
with no platform-conditional code paths outside `adapters/execute.py`'s
POSIX-only `max_memory_bytes` enforcement (which refuses rather than
silently no-ops on Windows) and the `fuzz/` harnesses (Linux-only, outside
`tests/` and never required for the normal suite). If you hit a
Windows/macOS-specific issue, please report it -- the core suite is now
gated there, but the property/fuzz/oracle tiers still are not.

## API Overview

See [ARCHITECTURE.md](ARCHITECTURE.md) for the module map, the core/optional-extras
dependency boundary, and the execution trust model behind the APIs below.

### `libipynb.codec` -- Reading and Writing

| Function | Description |
|---|---|
| `load(source)` | Load a notebook from a file path, string, bytes, or stream |
| `loads(text)` | Load a notebook from a JSON string |
| `dump(doc, dest)` | Write a notebook to a file path or stream. Default `profile` (omitted/`None`) validates the *entire* document against the nbformat 4.5 schema on every call and requires the document already be declared 4.5 — call `upgrade()` first otherwise. Pass `profile="declared"` for a cheap passthrough that preserves the document's own declared version and skips re-validation. For a path destination: atomic (temp-then-rename), preserves the destination's existing permissions, fsyncs for durability (POSIX), and writes *through* a symlink destination rather than replacing it — see [SECURITY.md](SECURITY.md#atomic-file-writes) for the full guarantee. |
| `dumps(doc)` | Serialize a notebook to a JSON string (same profile behavior as `dump`) |
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
- **`inject_parameters(doc, params)`** -- Papermill-style parameter injection into
  a cell tagged `"parameters"` (`libipynb.model.parameters`). Python-only;
  raises `UnsupportedLanguageError`/`UnsupportedParameterTypeError` rather than
  guessing or silently stringifying an unrecognized value the way real
  papermill's own fallback does -- see the module's docstring for the full
  rationale. Returns a `ParameterInjectionReport`; `dry_run=True` previews the
  placement without mutating anything

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
  decompressed size (2 GB), entries (2M), nesting depth (64), sanitizer scan tokens (200K)
- **`HmacNotebookNotary`** -- HMAC-based trust signatures

### `libipynb.adapters` -- Export and Execution

- **`MarkdownExporter`** / **`PythonScriptExporter`** -- convert notebooks to
  Markdown or `.py` files
- **`NbconvertExporter(fmt=...)`** -- one-directional export to any format
  the real `nbconvert` CLI supports (`html`, `slides`, `pdf`, `webpdf`,
  `script`, `markdown`, `rst`, `asciidoc`, ...) by shelling out to
  `python -m nbconvert --to <fmt>` (`libipynb[export]`) -- never imports
  `nbconvert` as a Python module, the same "wrap the real tool without a
  Python import dependency" pattern `execute_notebook()` and the git
  diff/merge driver integration also use. Text formats are captured via
  `--stdout` (`ExportResult.content` is `str`); `pdf`/`webpdf` cannot go
  through `--stdout` (nbconvert's own text-codec writer corrupts binary
  output there) and are instead written to a real file via `--output-dir`
  and read back (`ExportResult.content` is `bytes`). `HtmlExporter` is a
  thin, backward-compatible alias for `NbconvertExporter(fmt="html")`.
  Tested directly against the real installed tool, not mocked
  (`tests/integration/test_obligation_html_jupytext_export.py`) -- see
  [Export formats](#export-formats) below for the `pdf`/`webpdf` runtime
  requirement
- **`JupytextExporter`** -- round-trips a notebook to/from Jupytext's paired
  text formats via the real `jupytext` library (`libipynb[export]`);
  unlike `HtmlExporter`, `jupytext` is imported directly since it is not on
  `test_import_boundary.py`'s forbidden list

#### Export formats

`NbconvertExporter` is deliberately adapter-only for every format,
including `pdf`/`webpdf` (LIBIPYNB-Q37: a first-party PDF/slides renderer
was evaluated and rejected -- building a LaTeX or Chromium-based renderer
from scratch would be large, risky, and duplicate what `nbconvert` and its
own backends already solve well; wrapping the real tool honestly is this
project's established pattern everywhere else too, not a new exception).
Two formats need more than `libipynb[export]` alone at *runtime* -- neither
extra bundles them, matching real `nbconvert`'s own separate requirement:

- **`pdf`** needs a working LaTeX toolchain (`xelatex` or `pdflatex` on
  `PATH`) -- e.g. TeX Live or MiKTeX, installed separately.
- **`webpdf`** needs a working Playwright/Chromium install
  (`pip install playwright && playwright install chromium`).

If neither is available, calling `NbconvertExporter(fmt="pdf")` (or
`"webpdf"`) still raises a clean `NotebookError` (`code=
"export_tool_failed"`), never an uncaught exception -- but, verified
directly (this dev environment has neither installed): the message is
nbconvert's own real subprocess stderr wrapped as-is, not a synthesized
"please install X" hint, since nbconvert itself (not this adapter) is the
one that knows the LaTeX/Chromium backend is missing.

- **`execute_notebook()`** -- opt-in execution adapter with result tracking.
  **Still not a full sandbox**, but narrower than a bare subprocess: by
  default it runs in a fresh temporary working directory (`isolate_cwd`,
  cleaned up after), with a minimal environment instead of the caller's
  full one (`isolate_env`, extend via `extra_env`), and captured output is
  capped at 10 MiB (`max_output_bytes`) -- a *cumulative* budget shared
  across the whole run's cells (not per-cell independent, unlike
  `LocalJupyterExecutor`'s identically-named option below): once the
  running total is reached, each subsequent cell's own stdout is shortened
  to whatever remains and flagged via that cell's own
  `CellExecutionResult.stdout_truncated`; `ExecutionReport.output_truncated`
  is `True` iff any cell's was. Every cell always gets an explicit result
  -- one oversized cell never erases an unrelated later cell's own,
  already-complete output. A memory limit (`max_memory_bytes`) is enforced
  on POSIX only -- requesting one on Windows raises rather than silently
  running unlimited. CPU-time limiting and network-access denial are
  **not** implemented. Never called by `load`/`validate`/`diff`/`upgrade`/
  `save` -- it is the sole, explicit entry point into code execution,
  requires `acknowledge_unsandboxed=True`, and should only be pointed at
  notebooks you already trust to execute.

### `libipynb.execution` -- Real Jupyter-Kernel Execution (`libipynb[exec]`)

Second, opt-in execution backend alongside `libipynb.adapters.execute_notebook`
above -- neither replaces the other (see "Security posture" earlier in this
README, and the module's own docstring for the full design). Importing
`libipynb.execution` itself never requires `nbclient`/`jupyter_client` to be
installed; only constructing `LocalJupyterExecutor` does, and that failure is
a structured `MissingExecutionDependencyError`, not a bare `ImportError`.

```python
from libipynb import NotebookDocument
from libipynb.execution import ExecutionOptions, LocalJupyterExecutor

document = NotebookDocument.from_file("analysis.ipynb")

result = LocalJupyterExecutor().execute(
    document,
    options=ExecutionOptions(
        kernel_name="python3",  # None (default): use the notebook's own kernelspec
        cell_timeout=60,
        stop_on_error=True,
        acknowledge_unsandboxed=True,  # required -- see "Security posture" above
    ),
)

from libipynb import dump

dump(result.notebook, "analysis.executed.ipynb")
```

Async equivalent, for callers already running an event loop:

```python
result = await LocalJupyterExecutor().execute_async(document, options=options)
```

- **`ExecutionOptions`** -- typed, validated, frozen: `kernel_name`,
  `working_directory`, `cell_timeout`/`kernel_startup_timeout`,
  `stop_on_error`, `interrupt_on_timeout` (default `True` -- a timed-out cell
  interrupts the kernel and is reported as that cell's own error, rather than
  aborting the whole run), `skip_tag` (default `"skip-execution"`, matching
  `nbclient`'s own default -- tagged cells are never sent to the kernel and
  keep their existing outputs untouched), `record_timing` (default `False`),
  `in_place` (default `False` -- execution returns a fresh document by
  default; the caller's original is never mutated unless this is `True`),
  `acknowledge_unsandboxed`, `extra_env`, `on_event` (a lifecycle callback for
  progress reporting: `cell_started`/`cell_finished`/etc.)
- **`ExecutionResult`** -- `notebook` (the executed document), `cell_records`
  (one `CellExecutionRecord` per cell, including markdown/raw and
  never-executed/skipped cells), `kernel_name` (the kernel that actually
  launched), `timed_out`/`timed_out_cell_index`, `stopped_early`,
  `kernel_launch_error`/`kernel_death_error` (both `None` on a normal run --
  populated instead of raising, so a missing kernel or a kernel that dies
  mid-run is a value you check, not an exception you must catch),
  `completed`/`succeeded`/`first_error` properties
- **`CellExecutionRecord`** -- per-cell diagnostic: `outputs` (nbformat-schema
  output dicts -- `stream`/`display_data`/`execute_result`/`error`),
  `execution_count`, `error` (`ExecutionCellError`: `ename`/`evalue`/
  `traceback`), `executed`/`skipped`, `started_at`/`finished_at`,
  `output_truncated` (`True` when `max_output_bytes` shortened or omitted
  something in this cell's own outputs), `omitted_mime_types` (MIME type
  keys, e.g. `"image/png"`, removed entirely -- not corrupted -- because a
  base64-encoded binary representation exceeded `max_output_bytes`; distinct
  from ordinary text truncation, which keeps a shortened value in place)
- **`NotebookExecutor`** -- the backend-neutral `Protocol` both `execute()`/
  `execute_async()` satisfy; a future non-local backend (container, VM,
  remote service) could implement this same contract without any change to
  calling code -- nothing in this project ships one today
- Fidelity: only `outputs`/`execution_count`/(if `record_timing=True`)
  `metadata.execution` are ever written; cell `id`, `source` (in whatever
  string/list-of-lines form it was read), attachments, and unknown extension
  metadata are never touched, by construction (never round-tripped through
  `nbformat`'s own writer) -- see `adapters/jupyter_execute.py`'s "Fidelity
  strategy" docstring
- Cleanup: every kernel launched by `execute()`/`execute_async()` is shut
  down before the call returns, including on a cell error, a timeout, or
  `asyncio` task cancellation (verified directly in this project's own test
  suite -- a real kernel-process leak on cancellation was found and fixed
  during this feature's own implementation, not assumed safe)

### `libipynb.analytics` -- Notebook Analytics

- `cell_type_histogram(doc)` -- count cells by type
- `output_type_histogram(doc)` -- count outputs by type
- `has_execution_errors(doc)` -- check for error outputs
- `average_source_length(doc)` -- mean source length across cells

## CLI

libipynb installs a command-line tool with 13 subcommands:

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

# Execute a notebook through a real local Jupyter kernel (requires
# libipynb[exec] + an installed kernel). --acknowledge-unsandboxed is
# required -- this runs arbitrary notebook code with no sandbox, only for
# notebooks you already trust. Refuses to overwrite SOURCE via -o unless
# --force is also given. Exit 0 = every cell succeeded; exit 1 = the run
# completed but a cell errored/timed out/the kernel died; exit 2 = usage
# error (missing --acknowledge-unsandboxed, missing libipynb[exec], etc.)
libipynb execute notebook.ipynb -o executed.ipynb --acknowledge-unsandboxed

# Papermill-compatible parameter injection (same tag convention, same
# generated Python source -- oracle-verified against real papermill) into
# a cell tagged "parameters", then execute by default (same
# --acknowledge-unsandboxed/--force/exit-code rules as `execute` above).
# -p accepts repeated NAME VALUE pairs with papermill's own type
# inference (True/False/None/int/float/string); --parameters-file reads a
# JSON {name: value} object instead. --no-execute skips running it
# (and the exec extra/--acknowledge-unsandboxed requirement) and just
# writes the parameterized notebook.
libipynb run notebook.ipynb -p alpha 0.9 -p name run-1 --acknowledge-unsandboxed -o out.ipynb
libipynb run notebook.ipynb --parameters-file params.json --no-execute -o parameterized.ipynb

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
