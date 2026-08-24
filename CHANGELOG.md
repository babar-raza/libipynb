# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Everything below has landed on top of the `[0.1.0]` release below but has
not itself been tagged/published. (Restored 2026-08-24: this section and
the `[0.1.0]` entry below it had been conflated since 2026-08-17 -- several
commits kept editing the still-open `[0.1.0]` entry in place rather than
opening this section, which meant `[0.1.0]` no longer matched what was
actually tagged on 2026-08-12. `[0.1.0]` below is now restored to its
original, actually-released content; everything genuinely added or changed
afterward is recorded here instead.)

### Added

- **Full-parity closure** (LIBIPYNB-P1/P2/P3a/P3b/P3c/P6/P7/P8/P9,
  `plans/full-parity-plan.md`) -- line-level `DiffHunk`s for `diff_notebooks`
  (changed cell source reconstructed exactly, Hypothesis-verified); a
  per-cell `keep_output` metadata-flag/tag escape hatch for `cleanup`, plus
  an nbstripout-compatible default strip set for the CLI's `normalize`
  command (notebook-level `signature`/`widgets`; cell-level `ExecuteTime`/
  `collapsed`/`execution`/`heading_collapsed`/`hidden`/`scrolled`),
  configurable via `--keep-output`/`--keep-count`/`--extra-keys`/
  `--keep-metadata-keys` or `[tool.libipynb.normalize]` in `pyproject.toml`;
  git diff/merge driver installation (`diff --install-git`/`--uninstall-git`/
  `--git-status`) and git clean-filter integration (`normalize --install`/
  `--uninstall`/`--status`); cross-tool oracle test scaffolding
  (`tests/oracle/`) with real, passing comparisons against installed
  `nbstripout`/`nbdime` (stripping matches nbstripout except two documented,
  intentional divergences; merge behavior confirmed to never splice literal
  conflict markers or resolve silently, unlike either of nbdime's own merge
  strategies); a static import-boundary test
  (`tests/unit/test_import_boundary.py`) proving `src/libipynb` never
  imports the `oracle` extra and imports the `exec` extra only inside the
  one file that implements it; a doc-drift test tying the README's CLI
  command list/count to `cli/main.py`'s actual subcommands
- **Real Jupyter-kernel execution** (`libipynb[exec]`, LIBIPYNB-P4a-1/P4b/P4c,
  `plans/full-parity-plan.md` Gate G6 sign-off) -- `libipynb.execution`:
  `LocalJupyterExecutor` (sync `execute()`/async `execute_async()`), backed
  by `nbclient`, alongside the original subprocess `execute_notebook`
  adapter (neither replaces the other). Typed `ExecutionOptions` (kernel
  selection, per-cell/startup timeouts, `stop_on_error`,
  `interrupt_on_timeout`, `skip_tag`-tagged cells, `record_timing`,
  non-mutating-by-default `in_place`, `on_event` lifecycle callback) and
  `ExecutionResult`/`CellExecutionRecord` (rich outputs -- `stream`/
  `display_data`/`execute_result`/`error`/multi-MIME -- structured errors
  reported as values, never raised, for a cell error, a timeout, a missing
  kernel, or a dead kernel). Requires explicit `acknowledge_unsandboxed=True`
  (Python) / `--acknowledge-unsandboxed` (CLI, new `execute` command) --
  **not a sandbox**, same posture as the subprocess adapter. Fidelity: only
  `outputs`/`execution_count`/(opt-in) timing metadata are ever written
  back; cell id, source form, attachments, and unknown metadata are never
  touched. **Oracle-verified**
  (`tests/oracle/test_nbclient_execution_parity.py`, real
  `nbconvert --execute` installed): deterministic outputs and
  execution-count sequencing agree exactly.
- **Secret/PII scanning** -- `security.secrets.scan_for_secrets` -- pattern-
  based detection of likely credentials (AWS/GitHub/Slack tokens, PEM
  private keys, JWTs, generic key=value assignments, URL-embedded
  credentials, and credential-shaped metadata keys) across cell source,
  output text, tracebacks, and metadata. Report-only; findings carry a
  redacted preview, never the matched text. A clean report is not proof a
  notebook is free of secrets -- only that none of the configured patterns
  matched.
- **Export adapters** -- `HtmlExporter` (one-directional export to
  self-contained HTML via the real `nbconvert`, `libipynb[export]`) and
  `JupytextExporter` (round-trips to/from Jupytext's paired text formats via
  the real `jupytext` library, `libipynb[export]`)
- **CLI** -- `execute`, `analytics`, `trust` subcommands (12 total, up from
  8): `execute` requires `--acknowledge-unsandboxed`, refuses to overwrite
  the source notebook via `-o` unless `--force` is also given, and has
  stable exit codes (0 = every cell succeeded, 1 = the run completed but a
  cell errored/timed out/the kernel died, 2 = usage error)
- **Analytics** -- `cell_type_histogram`, `output_type_histogram`,
  `has_execution_errors`, `average_source_length`
- **Trust** -- `HmacNotebookNotary` for HMAC-based notebook trust signatures
- **GitHub Actions CI** (`.github/workflows/ci.yml`, LIBIPYNB-Q26) --
  quality (ruff/mypy), coverage (`fail_under=85`), a Python 3.11/3.12/3.13
  test matrix (Linux full, Windows/macOS core subset), and a package job
  that builds and smoke-tests a real installed wheel -- alongside the
  existing internal GitLab CI, which continues to govern the GitLab mirror
  unchanged; plus `oracle.yml`/`fuzz.yml`/`staleness-check.yml`/
  `release.yml`/`mutation.yml` (LIBIPYNB-Q27-Q31), all schedule-as-code
  (closing the "the GitLab schedule was never actually created" gap the
  same tiers had before) and independently verified via real local
  execution (`act`), not just YAML review
- **Mutation testing** (`mutmut`, LIBIPYNB-Q31) -- scoped to
  `codec/writer.py` for now (a real, working baseline: 268 mutants, 186
  killed, 61 survived, 75.3% score); a nightly CI job gates on a 70%
  mutation-score floor
- **Papermill-style parameter injection** (`inject_parameters()`,
  `libipynb run`, LIBIPYNB-Q35) -- inserts a code cell assigning
  parameters into a cell tagged `"parameters"`, matching real Papermill's
  own tag convention and generated Python source exactly (oracle-verified
  byte-for-byte for every supported value type: scalars, `None`,
  non-finite floats, unicode/escaped strings, nested lists/dicts).
  Python-only; raises `UnsupportedLanguageError`/
  `UnsupportedParameterTypeError` for anything outside that scope rather
  than guessing or silently stringifying the way real papermill's own
  fallback does -- a deliberate, documented divergence. The CLI's `run`
  subcommand injects and, by default, executes the result through the
  real kernel engine (`--acknowledge-unsandboxed` required, same posture
  as `execute`; `--no-execute` skips both that requirement and running
  anything)

### Fixed

- A real kernel-process leak on `asyncio` task cancellation in the kernel
  execution engine (nbclient's own cleanup path does not reliably run when
  the enclosing task is cancelled), plus a deeper, nbclient-internal
  cancel/dead-kernel race that could non-deterministically convert an
  external cancellation into an unrelated `DeadKernelError` -- both
  root-caused and fixed with regression tests; the second fix classifies
  "was cancellation requested" via `Task.cancelling()` (Python 3.11+)
  rather than pattern-matching on whichever exception the race happens to
  produce, verified deterministic across 20 repeated real-kernel
  cancellation trials (previously ~50% surfaced the race)
- Internal GitLab URL removed from packaging metadata (`pyproject.toml`'s
  `[project.urls]`, `CONTRIBUTING.md`'s clone instructions) -- no public
  host existed yet at the time; omitted entirely rather than replaced with
  a guessed placeholder
- `SECURITY.md`'s "no subprocess execution" claim corrected -- four opt-in
  features genuinely and intentionally use subprocess (the execution
  adapter, the HTML exporter, and the CLI's git integration), now
  enumerated explicitly rather than claimed absent
- Dead `pyyaml` test-extra dependency removed (never imported anywhere);
  an explicit `nbformat` pin added to the `exec` extra (previously relying
  on `nbclient`'s own transitive dependency)
- **8 confirmed P0 defects** found by an independent forensic audit
  (LIBIPYNB-Q16 through Q23), each with a regression test written to fail
  first: subprocess-execution output truncation losing every downstream
  cell's results (truncation was applied to the raw stream before parsing,
  not after); kernel-output truncation using an `any()` short-circuit that
  silently corrupted binary MIME payloads past the first oversized output;
  non-standard JSON constants (`NaN`/`Infinity`/`-Infinity`) accepted by
  the strict reader and `validate()`; atomic file writes losing the
  destination's file permissions, skipping `fsync`, and having no defined
  symlink policy; a missing `tests/__init__.py` breaking full-suite pytest
  collection from the repo root; corpus fixture hashes being
  line-ending-dependent instead of content-canonical; the oracle CI job
  never actually provisioning a real kernel (`ipykernel`) despite its own
  comment claiming to compare against one; and a PDF-export-backend
  detection fixture that was a `shutil.which()`-only presence check -- a
  false positive for a present-but-non-functional LaTeX install
- **LIBIPYNB-Q56**: `mypy --strict` and the full test suite are now
  reproducible in a genuinely fresh install, not just this project's own
  long-lived dev environment -- `nbformat` exact-pinned in the `test`
  extra (a bare floor let a fresh install resolve a newer version than the
  vendored schema digests are computed against) and the CI `mypy` job now
  installs the `exec`/`export` extras it actually needs to resolve every
  conditional import under `src/libipynb/`

### Changed

- Test coverage: 87.92% (752 tests) -> 89.07% (874 tests) -> 89.05% (879
  tests) across the full-parity and kernel-execution work above

## [0.1.0] - 2026-08-12

First publication-ready release.

### Added

- **Codec** -- `load`, `loads`, `dump`, `dumps`, `probe`, `roundtrip` for
  reading and writing `.ipynb` files with full round-trip fidelity
- **Typed model** -- `NotebookDocument`, `Cell`, `CodeCell`, `MarkdownCell`,
  `RawCell` with typed properties (`source`, `cell_type`, `id`, `metadata`,
  `outputs`, `tags`)
- **Validation** -- profile-aware structural and semantic validation against
  nbformat 4.0--4.5 with rich `Diagnostic` objects (code, message, severity,
  source location)
- **Sanitization** -- active content detection and handling in cell outputs
  with `LOSSLESS`, `REMOVE`, and `QUARANTINE` modes
- **Resource limits** -- configurable caps on input size (64 MB), output size
  (512 MB), decompressed size (2 GB), entries (100K), and nesting depth (64)
- **Duplicate-key detection** -- JSON objects with duplicate keys are rejected
  in strict mode (`IPYNB_DUPLICATE_KEY`); recorded as recovery actions in
  preservation/recovery modes
- **Atomic file writes** -- `dump()` uses write-to-temp-then-rename to prevent
  partial writes from corrupting notebook files on disk
- **Diff and merge** -- structural notebook diffing (`diff_notebooks`) and
  three-way merge (`merge_notebooks`) with conflict detection
- **Version conversion** -- `upgrade` and `downgrade` between nbformat 4.x
  minor versions with cell ID generation for 4.5
- **Cell editing** -- `edit_cells` for query-based batch cell modification
- **Cleanup** -- `cleanup` to strip outputs, normalize metadata, and remove
  empty cells with configurable policy
- **Attachments** -- `manage_attachments` for cell-level MIME attachment
  management with reference validation
- **Export adapters** -- `MarkdownExporter` and `PythonScriptExporter` for
  notebook conversion
- **Execution adapter** -- `execute_notebook` with per-cell result tracking
- **CLI** -- 8 commands: `probe`, `inspect`, `validate`, `sanitize`, `upgrade`,
  `diff`, `normalize`, `convert` -- all with JSON output
- **Analytics** -- `cell_type_histogram`, `output_type_histogram`,
  `has_execution_errors`, `average_source_length`
- **Trust** -- `HmacNotebookNotary` for HMAC-based notebook trust signatures
- **Error hierarchy** -- `NotebookError` base with `NotebookParseError`,
  `NotebookValidationError`, `NotebookWriteError`, `NotebookSecurityError`,
  `NotebookResourceLimitError`, `NotebookExecutionError`
- **nbformat interoperability tests** -- round-trip, validation, and version
  detection parity checks against `nbformat 5.10`
- **Property-based tests** -- Hypothesis-driven round-trip and validation
  fuzzing
- **Security tests** -- adversarial input, resource exhaustion, active content,
  path traversal, duplicate-key detection, and atomic write test suites
- **88% test coverage** with 666 tests (85% threshold enforced)
