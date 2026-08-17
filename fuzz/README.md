# Coverage-guided fuzzing (LIBIPYNB-V3)

Four `atheris`-based fuzz targets for the boundaries that process untrusted
input directly:

- `fuzz_parser.py` -- `libipynb.loads()` on raw bytes (the actual untrusted
  boundary: nothing has validated this input yet).
- `fuzz_validator.py` -- `libipynb.validate()` on JSON-shaped-but-otherwise
  fuzzed documents.
- `fuzz_sanitizer.py` -- `libipynb.sanitize()`'s markup scanner, fed fuzzed
  cell source/output text (the component that parses potentially hostile
  HTML/Markdown without rendering it).
- `fuzz_diff_merge.py` -- `diff_notebooks()`/`merge_notebooks()` on pairs/
  triples of fuzzed-but-structurally-plausible notebooks.

## Platform note

`atheris` does not build on native Windows (no published wheels, and
building from source fails: `error: [WinError 193] %1 is not a valid Win32
application`). It installs and runs cleanly on Linux, which is what this
project's CI already targets exclusively (`.gitlab-ci.yml` uses
`python:3.1x-slim` containers). These targets are meant to run there, or
under WSL for local iteration -- not on a bare Windows checkout.

This directory is intentionally outside `tests/` (`pyproject.toml`'s
`testpaths = ["tests"]`), so pytest never tries to collect it, and the
`atheris` dependency never needs to be installed for the normal test suite.

## Running locally (Linux / WSL)

```bash
pip install atheris
python fuzz/fuzz_parser.py -max_total_time=60
python fuzz/fuzz_validator.py -max_total_time=60
python fuzz/fuzz_sanitizer.py -max_total_time=60
python fuzz/fuzz_diff_merge.py -max_total_time=60
```

Each target treats the library's own `NotebookError` hierarchy (and, where
noted, a small set of other explicitly-expected exceptions) as "handled
input, not a bug" and lets anything else propagate -- that propagation is
what `atheris`/libFuzzer records as a crash and a minimized reproducer.

## What a clean run does and does not prove

A time-boxed run finding no crashes means: within the time budget spent,
none of these targets crashed, hung past libFuzzer's timeout, or leaked
memory outside `atheris`'s allocator limits, on the inputs the fuzzer's
mutation strategy happened to reach. It does not mean these boundaries are
exhaustively proven safe -- coverage-guided fuzzing is a search, not an
exhaustiveness proof, and code paths outside the fuzzer's reached coverage
are simply untested by this harness. Extending `-max_total_time` and
widening seed corpora both increase reached coverage; neither eliminates
the gap.
