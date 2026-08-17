# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- **Diff and merge** -- structural notebook diffing (`diff_notebooks`, with
  line-level `DiffHunk`s for changed cell source, reconstructed exactly via a
  Hypothesis-verified property) and three-way merge (`merge_notebooks`) with
  conflict detection; both exposed from the CLI (`diff`, `merge`) and
  installable as real git diff/merge drivers (`diff --install-git`,
  nbdime `config-git` equivalent)
- **Version conversion** -- `upgrade` and `downgrade` between nbformat 4.x
  minor versions with cell ID generation for 4.5
- **Cell editing** -- `edit_cells` for query-based batch cell modification
- **Cleanup** -- `cleanup` to strip outputs, execution counts, and selected
  metadata with configurable policy, plus a per-cell `keep_output`
  metadata-flag/tag escape hatch (default-on). The CLI's `normalize`
  command applies an nbstripout-compatible default strip set (notebook-level
  `signature`/`widgets`; cell-level `ExecuteTime`/`collapsed`/`execution`/
  `heading_collapsed`/`hidden`/`scrolled`), configurable via
  `--keep-output`/`--keep-count`/`--extra-keys`/`--keep-metadata-keys` or
  `[tool.libipynb.normalize]` in `pyproject.toml`, and can install itself as
  a real git clean filter (`normalize --install`/`--uninstall`/`--status`,
  nbstripout `--install` equivalent)
- **Attachments** -- `manage_attachments` for cell-level MIME attachment
  management with reference validation
- **Export adapters** -- `MarkdownExporter` and `PythonScriptExporter` for
  notebook conversion
- **Execution adapter** -- `execute_notebook` with per-cell result tracking.
  Opt-in only (`acknowledge_unsandboxed=True` required); runs in a separate
  OS subprocess, and by default in an isolated temp working directory
  (`isolate_cwd`) with a minimal environment (`isolate_env`, extend via
  `extra_env`) and a capped, truncation-reported output size
  (`max_output_bytes`). A memory limit (`max_memory_bytes`) is enforced on
  POSIX only; requesting one on Windows raises rather than silently running
  unlimited. Still **not a full sandbox** -- CPU-time limiting and network
  denial are not implemented. Never invoked by
  `load`/`validate`/`diff`/`upgrade`/`save`.
- **Real Jupyter-kernel execution** (`libipynb[exec]`, LIBIPYNB-P4a-1/P4b/P4c,
  `plans/full-parity-plan.md` Gate G6 sign-off) -- `libipynb.execution`:
  `LocalJupyterExecutor` (sync `execute()`/async `execute_async()`), backed
  by `nbclient`, alongside the original subprocess `execute_notebook`
  adapter above (neither replaces the other). Typed `ExecutionOptions`
  (kernel selection, per-cell/startup timeouts, `stop_on_error`,
  `interrupt_on_timeout`, `skip_tag`-tagged cells, `record_timing`,
  non-mutating-by-default `in_place`, `on_event` lifecycle callback) and
  `ExecutionResult`/`CellExecutionRecord` (rich outputs -- `stream`/
  `display_data`/`execute_result`/`error`/multi-MIME -- structured errors
  reported as values, never raised, for a cell error, a timeout, a missing
  kernel, or a dead kernel). Requires explicit `acknowledge_unsandboxed=True`
  (Python) / `--acknowledge-unsandboxed` (CLI, new `execute` command) --
  **not a sandbox**, same posture as the subprocess adapter. Fidelity: only
  `outputs`/`execution_count`/(opt-in) timing metadata are ever written back;
  cell id, source form, attachments, and unknown metadata are never touched.
  **Oracle-verified** (`tests/oracle/test_nbclient_execution_parity.py`,
  real `nbconvert --execute` installed): deterministic outputs and
  execution-count sequencing agree exactly. A real kernel-process leak on
  `asyncio` task cancellation (nbclient's own cleanup path does not reliably
  run on cancellation in this environment) was found and fixed during this
  feature's own implementation, with a regression test proving the fix via
  `psutil` child-process tracking.
- **Secret/PII scanning** -- `security.secrets.scan_for_secrets` -- pattern-
  based detection of likely credentials (AWS/GitHub/Slack tokens, PEM
  private keys, JWTs, generic key=value assignments, URL-embedded
  credentials, and credential-shaped metadata keys) across cell source,
  output text, tracebacks, and metadata. Report-only; findings carry a
  redacted preview, never the matched text. A clean report is not proof a
  notebook is free of secrets -- only that none of the configured patterns
  matched.
- **CLI** -- 12 commands: `probe`, `inspect`, `validate`, `sanitize`,
  `upgrade`, `diff`, `merge`, `normalize`, `convert`, `execute`, `analytics`,
  `trust` -- all with JSON output. `diff` gains `--install-git`/
  `--uninstall-git`/`--git-status` (git diff/merge driver integration);
  `normalize` gains git clean-filter integration (see Cleanup above);
  `execute` is new (see Real Jupyter-kernel execution above) --
  `--acknowledge-unsandboxed` required, refuses to overwrite the source
  notebook via `-o` unless `--force` is also given, stable exit codes
  (0 = every cell succeeded, 1 = the run completed but a cell errored/timed
  out/the kernel died, 2 = usage error)
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
- **Import-boundary test** -- static proof (`tests/unit/test_import_boundary.py`)
  that `src/libipynb` never imports the `oracle` extra
  (`nbdime`/`nbconvert`/`papermill`/`nbstripout`), and imports the `exec`
  extra (`jupyter_client`/`nbclient`) only inside the one file that
  implements it (`adapters/jupyter_execute.py`) -- a narrow, self-testing
  exception mirroring the existing `subprocess`-import allowlist pattern in
  `tests/integration/test_obligation_security_baseline.py`; both extras
  added to `pyproject.toml`, neither in core `dependencies`
- **Cross-tool oracle scaffolding** -- `tests/oracle/`, a `pytest.importorskip`-
  gated fixture set (matching the existing nbformat-oracle pattern in
  `tests/interoperability/`) for future comparison tests against real
  `nbstripout`/`nbdime`/`nbconvert`/`papermill` installs; none of those tools
  are installed in this project's own `.venv`, so these tests currently skip
  cleanly rather than exercise a live comparison -- see
  `plans/full-parity-plan.md` Gate G8 for what "parity" is allowed to claim
- **87.92% test coverage** with 752 passed, 9 skipped (up from 88.36%/704
  passed/4 skipped before this batch -- coverage dipped slightly because
  some new CLI branches, e.g. malformed-config-file fallbacks, aren't yet
  independently exercised; still above the 85% threshold)
- **89.07% test coverage** with 874 passed, 4 skipped (up from 88.30%/781
  passed/4 skipped -- LIBIPYNB-P4a-1/P4b/P4c's real Jupyter-kernel
  execution engine, `ruff`/`mypy` clean; 41 of the new tests are real-kernel
  integration tests, not mocked)
