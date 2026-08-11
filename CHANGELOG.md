# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0.dev0] - Unreleased

Initial development release extracted from the Format Factory monorepo.

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
- **CLI** -- `libipynb validate`, `libipynb inspect`, `libipynb probe` commands
  with JSON output
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
  and path traversal test suites
