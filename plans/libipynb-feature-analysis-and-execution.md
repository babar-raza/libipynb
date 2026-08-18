# libipynb: required capabilities, implementation design, and autonomous execution prompt

Date: 2026-08-18

## Executive decision

`libipynb` should be a zero-third-party-runtime-dependency, document-centric toolkit for reading, preserving, validating, creating, editing, analyzing, securing, converting, diffing, merging, and safely writing Jupyter notebook files. It should not be another thin JSON wrapper.

The product boundary must be explicit:

- The core library must not import or require `nbformat`, `jsonschema`, Jupyter, IPython, `nbclient`, `jupyter_client`, `ipykernel`, `nbconvert`, `nbdime`, Papermill, Jupytext, or Format Factory at runtime.
- Those mature projects should be used only as specification references, development/test oracles, licensed fixture sources, and interoperability targets.
- The central public abstraction should be `NotebookDocument`, backed by typed cell/output/MIME models but preserving unknown JSON fields and future minor-version content.
- Preservation is the default. Normalization, repair, cleaning, conversion, sanitization, and execution must be explicit operations that return diagnostics and change/loss reports.
- Notebook code is untrusted code. Loading, inspecting, validating, converting, diffing, or saving must never execute it. Execution must be an explicit optional subsystem and must never be described as a sandbox.
- A universal zero-dependency execution runtime is impossible: a Python, R, Julia, or other notebook necessarily requires its language runtime or kernel. `libipynb` can own orchestration and provide a standard-library Python subprocess backend; arbitrary Jupyter-kernel support must be an optional adapter with external runtime requirements disclosed honestly.

The official notebook format remains major version 4, minor version 5. Version 4.5 makes cell IDs mandatory; IDs must be unique within a notebook, 1–64 characters, using letters, digits, hyphen, and underscore. Notebook minor revisions are backward-compatible and may add fields, cell types, and output types, so a reader that discards unknown content is defective by design.

## Required capability model

The statuses below are requirements, not claims about the current implementation. The VS Code agent must prove each capability from code, tests, and observed behavior.

### 1. Dependency-free I/O and preservation

Required public behavior:

- Load from `str`, UTF-8 `bytes`, filesystem paths, text streams, and binary streams.
- Save to strings, bytes, streams, and paths.
- Detect invalid UTF-8, malformed JSON, duplicate object keys, trailing data, invalid top-level JSON types, unsupported major versions, and resource-limit violations with structured diagnostics.
- Enforce configurable limits before or during materialization: input bytes, nesting depth, object members, array entries, cells, outputs per cell, total decoded attachment/output bytes, individual string length, and total output bytes.
- Preserve all recognized and unrecognized fields, metadata namespaces, unknown future cell/output types, MIME entries, source representation, and notebook minor version unless the caller explicitly converts or normalizes.
- Provide two fidelity levels:
  - semantic round trip: the parsed JSON value is preserved, including unknown fields and ordering where practical;
  - no-op byte preservation: if a loaded document is unchanged, it can be written back exactly as read. Once changed, deterministic serialization applies.
- Never silently repair during read or validation. A separate repair operation returns the repaired document plus an itemized repair report.

Implementation approach:

- Use the standard library JSON machinery behind a guarded reader, with `object_pairs_hook` or an equivalent tokenizer path to detect duplicate keys.
- Keep a raw backing tree as the preservation source of truth. Typed views reference or wrap the backing nodes rather than reconstructing only known fields.
- Track document revision/dirty state and original bytes. Unknown dictionaries and lists must survive mutations to unrelated paths.
- Implement a purpose-built notebook validator rather than retaining `jsonschema` as a runtime dependency. Vendor the applicable Jupyter schemas only when licensing, attribution, provenance, and update instructions are included; otherwise encode the relevant rules in tables and tests.
- For very large notebooks, offer a scanning API that reports structure and sizes without base64-decoding every payload. True random access is not promised for ordinary JSON, but inspection must avoid unnecessary payload duplication.

### 2. Complete data model

Required types:

- `NotebookDocument`
- `CodeCell`, `MarkdownCell`, `RawCell`, and an `UnknownCell` preservation type
- `StreamOutput`, `DisplayDataOutput`, `ExecuteResultOutput`, `ErrorOutput`, and `UnknownOutput`
- `MimeBundle`, `Attachment`, notebook/cell/output metadata views
- `NotebookVersion`, `Diagnostic`, `ValidationReport`, `ChangeReport`, `LossReport`, and structured exception subclasses

Required behavior:

- Typed, discoverable access without forcing users to manipulate raw nested dictionaries.
- Mapping interoperability (`to_dict`, `from_dict`, controlled raw access) without exposing accidental shared mutable state.
- Constructors for notebooks, all standard cell types, all four stored output types, MIME bundles, and attachments.
- Clone/copy semantics, equality modes, stable hashing/fingerprinting, and transactions or immutable snapshots for safe multi-step edits.
- Explicit source APIs that treat the on-disk string-or-list representation separately from the logical text value.
- Metadata helpers for standard namespaces (`kernelspec`, `language_info`, `jupyter`, tags, execution timing, slideshow, widgets) while preserving arbitrary vendor metadata.

Implementation approach:

- Use typed wrappers with validation at mutation boundaries, not lossy dataclass reconstruction.
- Keep raw extension dictionaries on every extensible node.
- Expose both logical values and storage-form controls for multiline strings and MIME data.
- Use a controlled root export surface rather than exporting every internal helper.

### 3. Version coverage and loss-aware conversion

Required coverage:

- Read, validate, preserve, and write notebook v3 and v4.0 through v4.5.
- Tolerantly read a future v4 minor version, preserve unknown content, and issue an `UNSUPPORTED_FUTURE_MINOR` warning; strict validation may reject rules it cannot prove.
- Reject unknown major versions by default, with a raw-preservation inspection mode if safely possible.
- Explicit upgrade/downgrade APIs with a `LossReport`; never pretend a lossy operation is lossless.

Conversion details that must be handled:

- v3 `worksheets` to the v4 flat `cells` list. Multiple worksheets require a caller-selected policy: fail, concatenate with recorded boundaries, or custom mapping.
- v3 `heading` cells to Markdown headings and the reverse only when representable.
- `input` to `source`, `prompt_number` to `execution_count`, `pyout` to `execute_result`, and `pyerr` to `error`.
- v3 per-MIME output keys to v4 `data` MIME bundles and corresponding reverse mapping.
- v4 attachments, cell IDs, richer metadata, arbitrary `+json` MIME values, and unknown v4 content when downgrading. These must generate specific loss entries when v3 cannot represent them.
- v4 minor changes: attachments in 4.1, arbitrary JSON/`+json` MIME values and authors in 4.2, official `metadata.jupyter` fields in 4.4, and mandatory IDs in 4.5.

Implementation approach:

- Conversion is a pipeline of named rules, each independently tested and each able to append to `LossReport`.
- Do not mutate the input document unless the API explicitly says `in_place=True`.
- Validate both before and after conversion, distinguishing invalid source, unsupported construct, and converter defect.

### 4. Cell identity and editing

Required operations:

- Find by index, ID, type, tag, name, metadata predicate, and source pattern.
- Insert, append, delete, replace, move, reorder, split, join, and clone cells.
- Manage tags and metadata without replacing unrelated metadata.
- Preserve existing valid IDs through all unrelated operations.
- Detect missing, invalid, and duplicate IDs.
- Generate IDs that satisfy JEP 62, with deterministic repair mode for reproducible pipelines and collision handling.
- Enforce or report expected uniqueness for cell names and uniqueness/no-comma rules for tags.

Implementation approach:

- Use cell ID as primary identity for v4.5 and as the primary alignment key for diff/merge.
- Offer `IdPolicy`: preserve, random-for-new, deterministic-for-repair, reject-invalid.
- A deterministic repair ID may hash stable cell content plus occurrence context and then use a deterministic collision suffix. It must not rewrite valid existing IDs.

### 5. Outputs, MIME bundles, attachments, and widgets

Required behavior:

- Full support for stored `stream`, `display_data`, `execute_result`, and `error` outputs plus preservation of future unknown output types.
- Correct `execution_count`, `stdout`/`stderr`, traceback, metadata, multiline string, binary base64, and JSON MIME semantics.
- MIME helpers to list, get, set, remove, choose preferred representation, validate base64, decode with size limits, and compute content digests without accidental text conversion.
- Attachment helpers to add, replace, rename, extract, resolve `attachment:` references, find orphans/missing references, and remove unused attachments.
- Extraction must prevent absolute paths, `..` traversal, reserved names, separator tricks, collisions, and overwrite by default.
- Widget state must be preserved and inspectable. Cleaning or removing widget state must be explicit because it can contain large blobs, uploaded files, or secrets.
- Output-clearing and normalization policies: clear all, clear selected cells, reset counts, remove execution timing, coalesce adjacent streams, retain errors, retain selected MIME types, strip transient/vendor metadata.

Implementation approach:

- Treat a MIME bundle as `dict[str, JSONValue]`; text types may be string/list and `application/*+json` may be any JSON value.
- Never render active MIME types merely to inspect them.
- Provide digest/size summaries so diff and inspection do not print raw base64 blobs.

### 6. Validation, diagnostics, linting, and repair

Validation must have layers:

1. JSON/syntax validation.
2. Versioned structural validation for v3 and v4.0–4.5.
3. Cross-field semantic validation that schema alone cannot express: unique IDs, cell names, tag constraints, attachment references, execution-count consistency, MIME/base64 correctness, widget-state shape, and suspicious size relationships.
4. Policy linting: outputs committed, missing kernelspec, stale execution counts, hidden-source metadata, empty cells, oversized data, risky active content, secrets, non-deterministic metadata, and project-configured policies.

Required diagnostics:

- Stable machine-readable code, severity, JSON Pointer/path, message, version/spec rule, actual value summary, suggested action, and optional safe fix identifier.
- Collect-all and fail-fast modes.
- Strict and compatible profiles.
- Validation never mutates. Repair requires an explicit call, explicit repair policy, and before/after change report.

Implementation approach:

- Compile version rules into internal tables/functions to remain runtime-dependency-free.
- Unit-test every rule with a positive, negative, boundary, and wrong-version case.
- Differentially compare validation results with official `nbformat` in oracle tests, while documenting intentional compatibility differences.

### 7. Security, trust, and privacy

Required behavior:

- Loading and ordinary operations never execute code, import notebook-specified modules, fetch URLs, resolve external entities, render JavaScript, or open extracted files.
- Security scan for active/risky MIME (`text/html`, JavaScript MIME, SVG, widget views/state), suspicious Markdown/HTML links, embedded credentials/secrets, oversized payloads, path-like attachment names, and metadata likely to leak local paths or environment data.
- Sanitization profiles with an explicit report: conservative sharing, source-only, output-safe-list, metadata-safe-list, and custom policy.
- Jupyter-compatible or clearly namespaced HMAC trust/signature support using standard-library `hmac`, `hashlib`, and `sqlite3` or a pluggable local trust store. Signing means “trusted on this machine,” not “safe.”
- Secret detection must be conservative and explain false-positive risk; secret values must be redacted in diagnostics.
- No API may claim that subprocess execution is sandboxed. Timeouts and resource limits reduce damage but do not provide isolation.

Implementation approach:

- Separate `scan`, `sanitize`, `sign`, and `verify` APIs.
- Canonicalize only the content required by the chosen signature algorithm and prove compatibility with the reference implementation if “Jupyter-compatible” is claimed.
- Rendering APIs escape or remove active content by default; an explicit trusted mode may preserve it.

### 8. Deterministic and atomic serialization

Required behavior:

- Configurable indentation, newline, final newline, ASCII policy, key-order mode, multiline source representation, and canonical mode.
- Repeated serialization of the same logical document with the same options is byte-identical.
- Atomic path save: temporary file in the destination directory, flush, file `fsync`, permission handling, `os.replace`, best-effort directory `fsync`, and cleanup on failure.
- Optional optimistic concurrency check using original stat/digest so the library does not overwrite a file changed by another process.
- Symlink policy must be explicit; overwrite, backup, and permission behavior must be tested.
- Failed serialization or validation must leave the destination unchanged.

### 9. Transformations and cleaning pipelines

Required transforms:

- Clear/retain outputs and counts.
- Remove, allow-list, or rename metadata keys by JSON path.
- Normalize tags, cell IDs, source line representation, and stream outputs.
- Filter cells by tag/type/predicate.
- Strip or retain attachments and widget state.
- Redact secrets and paths.
- Parameterize a notebook by tagged parameter cell with language-aware adapters and an itemized provenance record.
- Compose transforms in a pipeline with dry-run, transactional application, per-transform reports, and idempotency tests.

Implementation approach:

- Transform functions return a new document by default plus `ChangeReport`.
- Every built-in transform must state whether it is lossless, reversible, and idempotent.
- A second application of an idempotent transform must produce no changes.

### 10. Structural diff, patch, and merge

Required behavior:

- Notebook-aware two-way diff over cells, source, metadata, outputs, MIME bundles, and attachments.
- Stable patch format with preconditions and versioning; apply, reverse where possible, and verify target fingerprints.
- Three-way merge returning a valid `MergeResult` plus structured conflicts.
- Align v4.5 cells primarily by ID; use sequence/content similarity fallback for notebooks without IDs.
- Treat generated fields such as execution counts and timing with configurable merge strategies.
- Avoid dumping base64 content; compare by media type, size, and digest, with optional decoded text diff for safe text MIME.
- Never silently choose one side of a real source conflict. Do not write ordinary Git conflict markers into JSON.

Implementation approach:

- Separate sequence alignment from field-level diff.
- Conflict objects include path/cell identity, base/local/remote summaries, candidate resolutions, and whether the conflict blocks serialization.
- Consult `nbdime` as the primary behavioral oracle, including generated-value conflict policies.

### 11. Inspection and reporting

Required reports:

- Notebook version, validity, cell counts/types/tags, languages/kernel metadata, execution state, output types/MIME types, attachment/widget sizes, unknown fields/types, risky content, and resource usage.
- Dependency/import hints may be provided as heuristic findings, clearly labeled as non-authoritative and language-specific.
- Compact terminal summary and stable JSON report suitable for CI.
- Fingerprint modes: complete document, source-only, content excluding generated execution data, and per-cell.

### 12. Conversion and export

Native, dependency-free targets should include:

- v3/v4 `.ipynb` conversion.
- Python percent-script (`# %%`) import/export with documented round-trip rules.
- Markdown export/import using explicit cell markers for round-trip mode.
- Standalone safe HTML report with escaped source, Markdown-preserving fallback, output selection, and extracted/embedded resource policies.
- Plain text/JSON inspection reports.

Boundaries:

- Do not claim full-fidelity Markdown rendering, syntax highlighting, PDF, LaTeX, Reveal.js, or arbitrary-language script conversion without the required engines.
- Provide an exporter interface for optional adapters. `nbconvert` and Jupytext are oracles, not runtime dependencies.
- Every importer/exporter declares fidelity level and emits a `LossReport`.

### 13. Explicit optional execution

The core document package must work without any execution dependency.

Required execution abstraction:

- `NotebookExecutor` protocol/interface.
- Execution options: working directory, environment allow/deny policy, notebook/cell/startup timeout, output byte limit, stop/continue-on-error, allowed error names, skip/only tags, selected cells, reset outputs, execution counts, hooks/events, cancellation, checkpoint/autosave policy, and kernel/backend selection.
- Structured result containing executed notebook, status, per-cell timings, diagnostics, error/timeout/cancellation information, and whether the output notebook was atomically saved.
- Execution must only occur through explicitly named methods/CLI commands.

Shipped dependency-free backend:

- A standard-library Python subprocess executor for trusted local Python notebooks.
- Use a long-lived child process with a framed protocol so state persists across cells.
- Compile each cell, execute statements, evaluate the final expression when possible, capture `stdout`, `stderr`, a safe `text/plain` representation, and structured exceptions.
- Enforce output limits; kill the whole child process group on timeout/cancellation; avoid `shell=True`; pass an explicit working directory and environment; checkpoint atomically.
- Do not promise IPython magics, comms, widgets, rich display protocol, arbitrary kernels, or OS-level sandboxing. Unsupported constructs must be diagnosed, not silently mis-executed.

Optional arbitrary-kernel backend:

- A separately installed adapter may use `jupyter_client`/`pyzmq`, or a future independently implemented messaging transport. It may not become a core dependency.
- Consult `nbclient` for timeout, hooks, error, kernel-death, stream, rich output, widget, and execution-timing behavior.
- Consult Papermill for tagged parameters, progress, autosave, provenance, and failure metadata.

### 14. CLI and developer usability

Expected command surface (names may adapt to the existing design):

- `libipynb inspect`
- `libipynb validate`
- `libipynb lint`
- `libipynb repair`
- `libipynb format`
- `libipynb clean`
- `libipynb extract`
- `libipynb convert`
- `libipynb diff`
- `libipynb patch`
- `libipynb merge`
- `libipynb scan-security`
- `libipynb sanitize`
- `libipynb sign` / `verify`
- `libipynb parameterize`
- `libipynb execute`

CLI requirements:

- `-` for stdin/stdout where safe, stable exit codes, human and JSON output, quiet mode, dry-run, diff preview, no-color mode, glob handling without shell dependence, atomic in-place edits, and refusal to mix binary notebook output with diagnostics on stdout.
- CLI and public Python API must exercise the same service layer.
- Every command has examples and failure-mode documentation.

### 15. Quality, compatibility, and publication evidence

Required evidence:

- A specification traceability matrix for v3 and v4.0–4.5.
- Unit tests for every public method and every schema/semantic rule.
- Round-trip and no-op preservation tests, including unknown fields/types and string/list source representations.
- Differential oracle tests against `nbformat` for read/write/validate/convert; `nbdime` for diff/merge; `nbconvert` and Jupytext for supported conversions; `nbclient` and Papermill for execution behavior; JupyterLab/Notebook and ipywidgets fixtures for interoperability.
- A licensed, provenance-recorded real-world corpus spanning Markdown/raw/code cells, every output type, large/binary MIME bundles, attachments, widgets, multiple kernels/languages, malformed notebooks, v3, every v4 minor, and future-minor synthetic cases.
- Property/metamorphic tests: read-write-read equivalence, deterministic writes, idempotent transforms, patch application, diff symmetry properties where applicable, merge invariants, failed atomic write leaves original intact.
- Mutation testing or equivalent defect-seeding for validators/converters.
- Fuzzing for JSON, base64, paths, nesting, and corrupted outputs; no crashes or unbounded allocation within documented limits.
- Performance benchmarks with recorded fixture sizes and thresholds, not ungrounded “fast” claims.
- Clean-environment packaging proof: wheel/sdist build, install, import, CLI smoke, typing, lint, tests, licenses/notices, no donor-repo or Format Factory coupling, and zero undeclared runtime dependencies.
- Consumer proof: create/load → inspect → mutate → validate → atomically save → reload; plus diff/patch/merge and explicit execution examples.

## Oracle policy

The mature ecosystem is used adversarially, not copied blindly:

| Oracle | What to compare | What not to inherit automatically |
|---|---|---|
| Jupyter `nbformat` | schemas, constructors, read/write, version conversion, validation, trust compatibility | runtime dependency, mutating validation/repair behavior, accidental quirks |
| JupyterLab / Notebook | real notebooks, save/reopen/render smoke, unknown metadata preservation | UI implementation |
| `nbdime` | cell alignment, structured diff, merge decisions, generated-field handling | web UI and Git integration dependencies |
| `nbconvert` | exporter boundaries, resource extraction, cleaning behavior | Pandoc/TeX/browser/template stack as core dependencies |
| Jupytext | marked text formats and round-trip expectations | every text dialect or lossy default |
| `nbclient` | execution state machine, timeouts, hooks, error and kernel-death behavior | implicit Jupyter dependency in core |
| Papermill | tagged parameters, progress, autosave, failure metadata | storage engines and broad dependency graph |
| ipywidgets | saved widget-state fixtures and security/privacy cases | widget runtime |

Rules:

1. Pin oracle versions in the development lockfile/evidence.
2. Record whether each oracle comparison is exact, normalized, compatible-but-different, or intentionally divergent.
3. Never call self-round-trip testing interoperability evidence.
4. Keep oracle packages out of core runtime metadata.
5. Preserve fixture licenses, attribution, source URL/commit, and checksum.

## Definition of “all gaps filled”

A feature is not complete because a method exists or a happy-path test passes. It is complete only when:

- the supported behavior and boundary are documented;
- public API and CLI behavior are implemented where applicable;
- positive, negative, boundary, malformed, preservation, and resource-limit tests pass;
- the relevant oracle/corpus evidence passes or a justified divergence is recorded;
- deterministic/idempotent/atomic behavior is proven where applicable;
- no unknown data is silently discarded;
- no unsupported behavior is implied by docs;
- packaging and clean-consumer proof pass;
- the evidence bundle points to exact commands, versions, artifacts, and results.

---

# Copy-ready autonomous VS Code agent prompt

## Mission

Work directly in the current `libipynb` repository. Thoroughly compare the existing implementation against the complete capability contract in this document, find both missing breadth and shallow implementations, create an evidence-backed execution plan, and then implement that plan until every in-scope gap is either closed and proven or blocked by a genuine external-authority constraint.

Do not stop after analysis or planning. Do not ask me ordinary engineering questions. Make sound, conservative decisions from the repository, specifications, tests, and the rules below. Continue through implementation, tests, documentation, packaging, and evidence. Do not publish, push, merge, release, or mutate any external repository without an explicit approval gate.

## Product goal

Produce a professional, independent, all-in-one Python toolkit for the `.ipynb` format—not a thin JSON wrapper.

“All-in-one” means the complete notebook document lifecycle is available from this package: robust I/O, preservation, a typed document model, v3 and v4.0–4.5, validation, linting, explicit repair, construction/editing, IDs, metadata, outputs, MIME bundles, attachments, widget-state handling, cleaning, security scanning/sanitization, signatures/trust, deterministic and atomic serialization, inspection, parameterization, native conversions, structural diff/patch/merge, CLI, and explicit optional execution.

It does **not** mean pretending that language runtimes, arbitrary Jupyter kernels, Pandoc, TeX, browsers, or OS sandboxes can be embedded without dependencies. The core must work without them. Ship a dependency-free standard-library Python subprocess executor if feasible and robust; keep arbitrary Jupyter-kernel support behind an optional adapter. Never claim subprocess execution is sandboxed.

## Hard constraints

1. Final distribution and import namespace: `libipynb`; central public type: `NotebookDocument` unless the existing public contract has a stronger, evidenced alternative.
2. Zero third-party **core runtime** dependencies. Remove runtime reliance on `nbformat`, `jsonschema`, Jupyter, IPython, `nbclient`, `jupyter_client`, `ipykernel`, `nbconvert`, `nbdime`, Papermill, Jupytext, Format Factory, sibling libraries, or donor-repository paths/imports/build steps. Standard-library use is allowed. Oracle packages may exist only in clearly separated development/test extras.
3. Zero `format_factory` imports or paths and no user-facing “Format Factory” branding in the independent product. Preserve legally required provenance/notices in the proper legal files rather than marketing it as part of the product.
4. The donor/source repository, if present, is read-only. Do not patch it. Do not create a shadow second IPYNB implementation.
5. Preserve notebook fidelity by default: IDs, metadata, unknown fields, future minor-version cell/output types, MIME bundles, attachments, widget state, output data, string/list source forms, and versions. Any loss must be explicit in a `LossReport`.
6. Loading, validating, inspecting, converting, diffing, merging, or saving must never execute notebook code or active output.
7. Execution is explicit, optional, trusted-local only, and never described as a sandbox.
8. Validation must not mutate. Repair/normalization/sanitization must be separate explicit operations with change reports.
9. Writes that target a path must be deterministic and atomic. Failed work must not corrupt the destination.
10. Preserve existing useful behavior and public compatibility unless evidence shows it is wrong. Do not perform a rewrite merely for aesthetic consistency.
11. Do not use destructive Git commands (`reset --hard`, `clean`, broad checkout/restore), do not discard unrelated user changes, and do not use stash as a convenience. Inspect repository status before every commit. Make small, intentional commits only if repository governance permits them.
12. Use the repository’s existing environment, commands, hooks, plans, taskcards, state machine, and evidence conventions. On the user’s Windows workstation, use the established `.venv` and Git Bash workflow where applicable. Do not invent a parallel governance system if one already exists; surgically harden the authoritative one.
13. No fabricated facts, benchmarks, test counts, compatibility claims, or completion claims. Evidence must come from observed commands and artifacts.
14. Do not treat the human as a blocker unless external authority is genuinely required. If one lane is blocked, record it and continue all safe independent lanes.
15. If the same approach fails twice, stop repeating it. Re-read the relevant code/specification, identify the false assumption, and redesign from first principles.

## Authoritative capability contract

Treat every capability in the preceding analysis as an audit requirement. At minimum, cover all 15 areas:

1. dependency-free I/O and preservation;
2. complete typed data model;
3. v3 and v4.0–4.5 plus future-minor preservation and loss-aware conversion;
4. cell identity and editing;
5. outputs, MIME bundles, attachments, and widgets;
6. layered validation, diagnostics, linting, and repair;
7. security, trust, and privacy;
8. deterministic and atomic serialization;
9. transformations and cleaning pipelines;
10. structural diff, patch, and three-way merge;
11. inspection/reporting;
12. dependency-free native conversion/export with honest fidelity boundaries;
13. explicit optional execution;
14. CLI and developer usability;
15. quality, interoperability, packaging, and publication evidence.

Do not reduce these to checkboxes. Test depth, error branches, preservation behavior, limits, idempotency, and interoperability.

## Required working sequence

### Phase 0 — establish authority and protect the workspace

1. Locate and read completely: `AGENTS.md` files, README, package metadata, architecture docs, plans, taskcards, state files, inventories, governance/publication rules, test configuration, CI, hooks, evidence/certification machinery, and any independent-library extraction standard.
2. Inspect Git status, branch, worktrees, recent relevant commits, ignored files, and existing changes. Record what predates this task. Never overwrite unrelated work.
3. Locate the actual production package(s), legacy/shadow implementations, tests, corpus, CLI, docs, build configuration, and any donor/Format Factory coupling.
4. Identify the authoritative plan/state artifacts. Update those rather than creating competing plans. If none exist, create the minimum taskcard/state/ledger artifacts needed for resumable execution.
5. Capture a reproducible baseline: environment, Python version(s), installed package metadata, test/lint/type/build commands, current failures, package imports, wheel metadata, and source/test LOC only as orientation—not as quality evidence.

### Phase 1 — feasibility and architecture boundary

Write a short evidence-backed feasibility decision before implementation, then continue immediately.

It must separately decide:

- zero-third-party core document toolkit: expected feasible;
- internal versioned validation without runtime `jsonschema`: expected feasible;
- dependency-free Python subprocess execution: feasible with documented semantic limits;
- full IPython/Jupyter rich execution without IPython/Jupyter/ZeroMQ dependencies: do not claim feasible unless proven;
- arbitrary-language execution: requires external runtime/kernel and therefore must remain an optional adapter;
- full-fidelity PDF/LaTeX/browser rendering: optional adapter, not core.

Record the chosen boundary in architecture and user documentation. Do not use infeasible ambitions to block all feasible work.

### Phase 2 — build a specification and oracle ledger

Create or update one authoritative traceability matrix with one row per normative rule/capability. Include:

- requirement ID;
- format version(s);
- normative source URL and pinned revision/version;
- affected public API/CLI;
- implementation file/symbol;
- test/evidence location;
- oracle and expected comparison;
- status: `UNKNOWN`, `ABSENT`, `THIN`, `PARTIAL`, `COMPLETE`, `BLOCKED_EXTERNAL`;
- exact gap and next action.

Sources and oracles to inspect directly:

- official Jupyter notebook v3 and v4.0–4.5 schemas and format description;
- JEP 62 cell IDs;
- current `nbformat` source/tests for read/write/validate/convert/signing;
- `nbdime` source/tests for structural diff and merge;
- `nbconvert` and Jupytext for conversion/export boundaries;
- `nbclient` and Papermill for execution/parameterization state machines;
- ipywidgets saved-state fixtures and security implications;
- real notebooks from upstream Jupyter projects with compatible licenses.

Pin oracle versions/commits. Record fixture provenance, license, checksum, and purpose. Oracle dependencies belong only in development/test extras or isolated compatibility jobs.

### Phase 3 — audit the current implementation adversarially

For each capability, inspect implementation, public API, CLI, tests, docs, and observed behavior. A symbol name is not evidence.

Classify as `THIN` when any of these apply:

- only a happy path exists;
- it rebuilds known fields and drops unknown data;
- it handles only v4.5 or only one cell/output type;
- validation delegates to a dependency without owned behavior/error contract;
- a “round trip” only tests the library against itself;
- repair occurs silently;
- errors are generic strings without paths/codes;
- atomicity/determinism/idempotency is claimed but not fault-tested;
- diff is line/JSON diff rather than notebook-structural;
- merge silently prefers one side;
- sanitizer only clears outputs;
- attachment extraction is path-unsafe;
- execution calls `exec` in-process, has no process kill/timeout/output limits, or implies sandboxing;
- CLI merely exposes a subset of internal functions and lacks stable exit/JSON behavior;
- tests mock away the behavior being claimed;
- docs promise unsupported conversions/rendering/execution.

Run focused probes for every suspicious path. Add characterization tests before changing mature behavior. Build a gap ledger containing:

- capability ID;
- current evidence;
- gap classification and severity;
- user impact/security/data-loss risk;
- root cause;
- required implementation;
- tests/oracles/corpus needed;
- dependencies and file ownership;
- acceptance command;
- documentation/evidence updates.

### Phase 4 — make the execution plan taskcard-driven

Convert every gap into bounded taskcards. Each taskcard must define:

- objective and non-goals;
- owned files/symbols;
- prerequisites;
- normative requirements;
- implementation steps;
- positive/negative/boundary/malformed/security/resource-limit tests;
- oracle/corpus comparison;
- acceptance commands;
- evidence outputs;
- rollback/failure handling;
- completion criteria.

Plan dependency order, not convenience order:

1. errors/diagnostics/limits and preservation-capable raw model;
2. guarded I/O and serialization;
3. typed model and constructors;
4. versioned structural/semantic validation;
5. IDs and core editing;
6. v3/v4 conversion;
7. MIME/attachments/widgets;
8. transforms/cleaning/security/trust;
9. inspect/report;
10. diff/patch/merge;
11. native converters;
12. CLI;
13. Python subprocess execution and optional adapter boundary;
14. performance, packaging, docs, evidence, and final audit.

Parallelize only independent taskcards with disjoint file ownership and explicit integration points. Keep one coordinator responsible for shared public exports, package metadata, authoritative state, and final integration. Do not let parallel work create competing APIs or duplicate implementations.

### Phase 5 — execute, do not pause after planning

Immediately implement the plan in dependency order.

For every taskcard:

1. mark it in progress in authoritative state;
2. add/strengthen tests that expose the real gap;
3. implement the smallest coherent production change that closes the whole taskcard, not only the first failing example;
4. run focused tests, then related suite, then full gates at integration points;
5. run relevant oracle and corpus checks;
6. inspect diffs for unknown-field loss, accidental normalization, new coupling, and documentation drift;
7. update traceability, gap ledger, docs, changelog/state, and evidence;
8. mark complete only when every acceptance criterion has observed evidence.

Do not lower tests, weaken validation, delete difficult fixtures, xfail real defects, or redefine requirements to manufacture green status. If a reference library behaves incorrectly or differently, preserve the fixture and record an intentional, justified divergence.

### Phase 6 — required execution-engine design

Keep execution in an explicit optional subsystem. The base package must import and operate when execution extras and Jupyter packages are absent.

For the standard-library Python backend:

- execute in a separate, long-lived Python child process so variables persist between cells;
- use a framed machine protocol, not fragile parsing of mixed stdout;
- never use `shell=True`;
- capture stdout/stderr separately and preserve output ordering as far as the protocol can prove;
- compile cells and evaluate a final expression where semantically safe;
- create v4 outputs and counts correctly;
- convert exceptions into `error` outputs and structured execution diagnostics;
- implement cell/notebook timeout, cancellation, output byte limits, process-group termination, working directory, environment filtering, stop/continue-on-error, skip/only tags, hooks/events, timings, and atomic checkpoints;
- clearly reject or diagnose unsupported IPython magics, shell escapes, comms/widgets, rich display, stdin prompts, and non-Python kernels;
- test process death, timeout, infinite output, malformed protocol, partial checkpoint, keyboard cancellation, and cleanup;
- place a prominent warning in API/CLI/docs: trusted code only; not a sandbox; code can access files, processes, network, and credentials available to it.

If an arbitrary-kernel adapter already exists, isolate it as an optional extra and test it against pinned `nbclient` behavior. Do not let it leak imports into core.

### Phase 7 — evidence gates

The following gates must pass before claiming completion:

#### G1: independence

- clean-environment import and CLI smoke with only declared core dependencies;
- core runtime dependency list is empty;
- repository-wide scan finds no prohibited runtime/path/build/test/docs coupling;
- no shadow implementation or donor-path dependency.

#### G2: specification

- v3 and every v4.0–4.5 traceability row has code and test evidence;
- future v4 minor preservation is proven;
- all cell/output/MIME/attachment/widget cases are covered;
- strict validation and tolerant preservation are distinct.

#### G3: fidelity and safety

- no-op byte preservation and semantic read-write-read tests pass;
- unknown fields/types survive unrelated edits;
- conversion losses are reported;
- resource limits, duplicate keys, malformed JSON/base64, path traversal, active MIME, and redaction tests pass;
- validation is non-mutating and repair/sanitize are explicit.

#### G4: editing and workflows

- create/load/inspect/mutate/validate/atomic-save/reload consumer proof passes;
- built-in transforms prove documented idempotency;
- diff/patch/merge invariants and conflicts are proven;
- native conversion fidelity/loss reports pass.

#### G5: execution

- core remains usable with all Jupyter packages absent;
- Python subprocess backend passes state, output, error, timeout, cancellation, process-death, output-limit, and atomic-checkpoint cases;
- unsupported behavior is diagnosed honestly;
- no sandbox claim exists.

#### G6: interoperability

- pinned `nbformat` differential tests pass or document justified divergences;
- `nbdime`, conversion, widget, and execution oracle matrices are current;
- real-world licensed corpus reopens/validates in the applicable upstream tools;
- self-round-trip results are not labeled interoperability.

#### G7: publication readiness

- full tests, lint, type checks, build, wheel/sdist install, CLI, docs examples, license/notices, manifest, and clean-consumer smoke pass;
- public API is controlled and documented;
- benchmark results and limitations are factual;
- evidence bundle is complete and reproducible;
- no push, publication, or release has occurred without approval.

## Required final deliverables

Do not return a narrative-only summary. Leave these in the repository’s authoritative locations:

1. updated plan/taskcards and machine-readable state;
2. specification/capability traceability matrix;
3. current implementation audit and closed gap ledger;
4. production implementation and tests;
5. oracle lock/provenance and real-world corpus manifest;
6. architecture/security/execution-boundary documentation;
7. complete API and CLI documentation with runnable examples;
8. benchmark and compatibility reports;
9. packaging/independence audit;
10. reproducible evidence bundle with commands, versions, outputs, and checksums;
11. final concise report listing commits/files changed, gates passed, remaining blockers, and exact resume instructions.

The final status may be `COMPLETE`, `BLOCKED_EXTERNAL`, or `FAILED_INTERNAL`—never vague “mostly complete.” A blocker is valid only when it requires external authority, unavailable credentials/service, or an irreducible platform/runtime dependency. An implementation difficulty, failing test, weak current design, or missing internal feature is work to perform, not a reason to stop.

## Primary references

- Jupyter notebook format description: https://nbformat.readthedocs.io/en/latest/format_description.html
- Current nbformat API: https://nbformat.readthedocs.io/en/latest/api.html
- Official v4.5 schema: https://github.com/jupyter/nbformat/blob/main/nbformat/v4/nbformat.v4.5.schema.json
- Official v3 schema: https://github.com/jupyter/nbformat/blob/main/nbformat/v3/nbformat.v3.schema.json
- JEP 62 cell IDs: https://jupyter.org/enhancement-proposals/62-cell-id/cell-id.html
- nbdime: https://nbdime.readthedocs.io/
- nbclient execution: https://nbclient.readthedocs.io/en/latest/client.html
- Papermill execution: https://papermill.readthedocs.io/en/latest/usage-execute.html
- Jupyter Server notebook trust/security: https://jupyter-server.readthedocs.io/en/latest/operators/security.html
- ipywidgets embedding/saved state: https://ipywidgets.readthedocs.io/en/latest/embedding.html
- nbconvert architecture: https://nbconvert.readthedocs.io/en/latest/architecture.html
- Jupytext formats: https://jupytext.readthedocs.io/en/latest/formats.html
