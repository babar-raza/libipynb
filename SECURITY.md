# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Pre-release, actively maintained |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly by emailing
the maintainer directly rather than opening a public issue. Include:

- A description of the vulnerability
- Steps to reproduce or a minimal notebook file that triggers it
- The potential impact

You can expect an initial response within 48 hours.

## Security Features

libipynb includes built-in protections against common notebook-related security risks.

### Resource Limits

All parsing and processing operations enforce configurable resource limits to prevent
denial-of-service through crafted notebooks:

| Limit | Default | Description |
|---|---|---|
| `max_input_bytes` | 64 MB | Maximum size of raw notebook input |
| `max_output_bytes` | 512 MB | Maximum size of serialized output |
| `max_decompressed_bytes` | 2 GB | Maximum decoded/decompressed content size |
| `max_entries` | 2,000,000 | Maximum total JSON object keys and array elements |
| `max_nesting_depth` | 64 | Maximum nesting depth of JSON structures |
| `max_scan_tokens` | 200,000 | Maximum markup tokens `sanitize()` parses per scan |

Limits are enforced during parsing via `NotebookResourceLimits`. To customize:

```python
from libipynb import load
from libipynb.security import IPYNB_DEFAULT_LIMITS

custom_limits = IPYNB_DEFAULT_LIMITS.with_overrides(
    max_input_bytes=10 * 1024 * 1024,  # 10 MB
    max_entries=10_000,
)
doc = load("notebook.ipynb", limits=custom_limits)
```

Exceeding any limit raises `NotebookResourceLimitError`.

**Shape-dependent protection, explicitly:** `max_entries` is enforced incrementally
during JSON *object* construction (via `object_pairs_hook`), but Python's `json`
module has no equivalent hook for *array* construction -- a large flat array of
scalars or a single large flat object is fully decoded before the post-parse
`enforce_structure()` walk gets a chance to reject it. This is a confirmed
limitation of the standard library, not an oversight; the worst case remains
bounded by `max_input_bytes` (checked before parsing begins) and
`max_decompressed_bytes`, which together limit a flat-scalar-array payload to on
the order of `max_input_bytes / 2` elements (a minimal legal array element is at
least 2 bytes) before `json.loads()` is even invoked. A notebook's own `cells`
array (an array of objects, not scalars) does not have this gap -- it is
protected incrementally like any other nested-object structure.

### Duplicate Key Detection

Python's `json.loads` silently keeps the last value when a JSON object contains
duplicate keys. This can hide malicious payloads -- an attacker might place
dangerous content under a key that appears earlier in the JSON, knowing the later
(benign) value will be the one that survives.

libipynb detects duplicate keys during parsing:

| Parse mode | Behavior |
|---|---|
| `strict` | Raises `NotebookParseError` with code `IPYNB_DUPLICATE_KEY` |
| `preservation` | Records a recovery action; keeps last value |
| `recovery` | Records a recovery action; keeps last value |

### Atomic File Writes

`dump()` writes notebooks to disk using a write-to-temp-then-rename pattern.
This prevents partial writes from corrupting the target file if the process is
interrupted or the disk fills up. The stream-write path (writing to a file-like
object) is unchanged, as streams cannot support atomic semantics.

### Content Sanitization

The `sanitize()` function detects active content in cell outputs -- scripts,
iframes, event handlers, and other executable payloads embedded in MIME bundles.
Three modes are available:

| Mode | Behavior |
|---|---|
| `LOSSLESS` | Report findings only; do not modify the notebook (default) |
| `REMOVE` | Remove unsafe MIME types from output bundles |
| `QUARANTINE` | Move unsafe content to a quarantine metadata field |

Active MIME types detected by default:
- `text/html`, `text/javascript`, `application/javascript`
- `image/svg+xml` (may contain embedded scripts)
- `application/ecmascript`, `text/ecmascript`
- `application/x-javascript`, `text/x-javascript`

HTML content is further inspected for dangerous elements (`<script>`, `<iframe>`,
`<object>`, `<embed>`, `<form>`, etc.) and attributes (`onclick`, `onerror`,
`javascript:` URIs).

### Trust and Signatures

`HmacNotebookNotary` provides HMAC-based notebook signing compatible with Jupyter's
trust model. Trusted notebooks skip sanitization in rendering environments; untrusted
notebooks have their active outputs sanitized.

### Path Safety

Export and attachment operations validate paths to prevent directory traversal
attacks. Paths containing `..` components, absolute paths, and other traversal
patterns are rejected.

## Design Principles

- **Defense in depth**: Resource limits are enforced at the parser level before any
  model objects are constructed. Sanitization operates on the typed model after parsing.
- **No rendering**: The sanitizer does not attempt to render or rewrite HTML/SVG into
  a safe subset. Unsafe content is removed entirely or quarantined for external review.
- **Fail-closed**: Unknown cell types and output types are preserved for round-trip
  fidelity but flagged as `preservation_only` in the typed model.
- **Minimal dependencies**: The only runtime dependency is `jsonschema` (for schema
  validation). The core load/validate/dump/sanitize path performs no network access,
  no subprocess execution, and no dynamic code loading. Four opt-in features spawn a
  subprocess or a full kernel process, never imported by the core path
  (`tests/unit/test_import_boundary.py` enforces this): the dependency-free
  subprocess-based execution adapter (`adapters/execute.py::execute_notebook` --
  stdlib only, no extra required), the real Jupyter-kernel-protocol execution engine
  (`adapters/jupyter_execute.py::LocalJupyterExecutor`, `libipynb[exec]` --
  launches and communicates with an actual `ipykernel` process, the most
  security-relevant of the four since it runs arbitrary cell code against a live
  kernel rather than a one-shot subprocess), `HtmlExporter` (`adapters/export.py`,
  shells out to `python -m nbconvert`, `libipynb[export]`), and the CLI's git
  integration (`cli/main.py`, shells out to the `git` executable to read and write
  repository/global `git config` and `.gitattributes` when installing or
  uninstalling the diff/merge driver).
