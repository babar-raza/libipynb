# Coverage-guided fuzzing (LIBIPYNB-V3, extended under LIBIPYNB-Q40)

Six `atheris`-based fuzz targets for the boundaries that process untrusted
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
- `fuzz_nan_infinity.py` -- `libipynb.loads()` specifically driving coverage
  into the `NaN`/`Infinity`/`-Infinity` strict-mode rejection path
  (LIBIPYNB-Q18/P0-C), by constructing plausible notebook JSON text with a
  fuzzer-chosen non-finite constant embedded at a fuzzer-chosen leaf
  position -- `fuzz_parser.py`'s pure random-byte mutation is extremely
  unlikely to stumble onto these exact literal tokens in a syntactically
  valid numeric position within a bounded time budget on its own.
- `fuzz_output_truncation.py` -- `adapters.execute._apply_output_budget`
  (LIBIPYNB-Q16/P0-A) and `adapters.jupyter_execute.
  _truncate_outputs_if_needed` (LIBIPYNB-Q17/P0-B) called directly, fuzzing
  variable-length result/output lists and budgets. Complements
  `tests/property/test_property_output_truncation.py`'s Hypothesis
  coverage of the identical two functions with a different search
  strategy (coverage-guided mutation vs. example-based property checking)
  over the same historically-buggy boundary.

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
python fuzz/fuzz_nan_infinity.py -max_total_time=60
python fuzz/fuzz_output_truncation.py -max_total_time=60
```

WSL note (this project's own local verification of these two newest
targets): `atheris` requires Python >=3.11, and WSL distributions commonly
ship an older system Python (e.g. Ubuntu 22.04's default is 3.10) -- install
a newer interpreter yourself first (e.g. `curl -LsSf https://astral.sh/uv/install.sh
| sh` then `uv python install 3.12`, no root needed). Also build/install
from a directory on the native Linux filesystem (e.g. `~/`), not
`/mnt/c/...` -- editable installs fail there with `Cannot update time
stamp of directory 'src/libipynb.egg-info'`, a known drvfs (9p/NTFS mount)
limitation, not a bug in this project.

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
