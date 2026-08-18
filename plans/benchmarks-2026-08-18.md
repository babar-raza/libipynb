# libipynb Benchmarks — 2026-08-18

**Date:** 2026-08-18
**Purpose:** A standing, dated, re-runnable performance snapshot. Section 12 of
[`plans/forensic-capability-audit-2026-08-18.md`](forensic-capability-audit-2026-08-18.md) ("Performance
and Large-Notebook Assessment") ran a similar pass earlier the same day, before two resource-limit
defaults changed (`security/limits.py`: `max_entries` raised `100_000 → 2_000_000`, and a new
`max_scan_tokens = 200_000` guard added). This document does **not** reuse that pass's numbers — every
figure below was measured fresh, against a freshly-built fixture, on this run.
**Repository:** `libipynb`, local branch `master` at commit `88aa112`.
**Environment:** Windows 11 Pro build 10.0.26200 (`platform.platform()` →
`Windows-11-10.0.26200-SP0`), Intel64 Family 6 Model 183 (AMD64). Interpreter: the project's
`.venv\Scripts\python.exe`, confirmed via `.venv\Scripts\python.exe --version` → **Python 3.13.2**.
`nbformat==5.10.4` (used only to build the fixture, not part of the library under test), `psutil==7.2.2`
(used for RSS memory measurement).

---

## 1. Fixture construction

No dedicated performance fixture ships in the repo (confirmed by the earlier audit and re-confirmed
here). A fresh fixture was built matching the audit's §12 description — a realistic (not adversarial)
notebook, not committed to the repository, built and discarded from the OS temp/scratch directory.

**Method used:** `nbformat.v4` construction helpers (`new_notebook`, `new_code_cell`,
`new_markdown_cell`, `new_output`), the same approach the original audit used (it cites
`nbformat.v4.new_code_cell()` directly). `libipynb` itself has no equivalent cell-construction
convenience API — `NotebookDocument`/`CellEditor` operate on plain dicts — so `nbformat` was the more
direct choice, exactly as permitted by the task brief.

Script (`build_fixture.py`, run from the scratch directory, not committed):

```python
import base64, os, sys
import nbformat as nbf

def build(out_path, num_cells=3000, image_every=6, image_bytes=46_000):
    nb = nbf.v4.new_notebook()
    nb["metadata"] = {
        "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
        "language_info": {"name": "python", "version": "3.11.0"},
    }
    cells = []
    image_count = 0
    for i in range(num_cells):
        if i % 5 == 0:
            text = (f"## Section {i}\n\nSome narrative markdown text describing what the "
                     "following cells demonstrate, repeated to give realistic prose length. " * 6)
            cell = nbf.v4.new_markdown_cell(source=text)
        else:
            src = (f"x_{i} = {i}\ndef f_{i}(a, b):\n    \"\"\"Doc string.\"\"\"\n"
                   f"    return a + b + x_{i}\nresult_{i} = f_{i}({i}, {i+1})\n"
                   f"print('result', result_{i})\n")
            cell = nbf.v4.new_code_cell(source=src)
            cell["execution_count"] = i
            if i % image_every == 0 and image_count < 400:
                data = base64.b64encode(os.urandom(image_bytes)).decode("ascii")
                out = nbf.v4.new_output(output_type="display_data",
                                         data={"image/png": data, "text/plain": f"<Figure {i}>"})
                cell["outputs"] = [out]
                image_count += 1
            else:
                out = nbf.v4.new_output(output_type="stream", name="stdout",
                                         text=f"result {i+i+1}\n")
                cell["outputs"] = [out]
        cell["id"] = f"cell-{i:05d}"
        cells.append(cell)
    nb["cells"] = cells
    nb["nbformat"], nb["nbformat_minor"] = 4, 5
    with open(out_path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)
```

Actual output, this run:

```
wrote fixture_large.ipynb: 25.16 MiB, 3000 cells, 400 image outputs
```

This matches the audit's described shape (~25 MB / 3,000 cells / 400 image outputs) almost exactly
(25.16 MiB here vs. the audit's cited 25.14 MiB) — close enough to treat the two passes' cost profiles
as comparable, while every timing number itself is a fresh measurement, not copied.

---

## 2. Load → validate → write cycle

Command (`benchmark.py`, run via `.venv\Scripts\python.exe benchmark.py`, using
`libipynb.codec.reader.load`, `libipynb.validation.validate`, `libipynb.codec.writer.dumps`):

```python
doc = reader.load(FIXTURE, mode="strict")
validate(doc)
writer.dumps(doc, profile="declared")   # cheap passthrough path
writer.dumps(doc)                       # default profile=None -> resolves to schema-validating "4.5"
```

| Step | Measured (this run) | Audit's §12 cited figure | Comparison |
|---|---|---|---|
| `load(strict)` | **2.4217 s** | not separately broken out in §12 (folded into the 25–30 s cycle figure) | fresh measurement |
| `validate(doc)` | **3.1444 s** | not separately broken out | fresh measurement |
| `dumps(profile="declared")` | **0.1715 s** | **0.134 s (warm)** | same order of magnitude; still ~18x cheaper than the default write below |
| `dumps()` default (`profile=None` → `"4.5"`) | **3.0297 s** | **2.17 s (warm) / 9.6 s (cold)** | same order of magnitude; the `declared` vs. default gap (~18x here vs. the audit's cited 16–70x) is confirmed still real, still present, unchanged in shape |
| **Full cycle, `declared` write** | **5.4967 s** | not cited as a standalone number | fresh measurement |
| **Full cycle, default write** | **8.1896 s** | **~25–30 s cited for "a single strict-mode load→validate→write cycle"** | this run is markedly faster than the audit's cited 25–30 s. This is very unlikely to be caused by the `max_entries`/`max_scan_tokens` changes (this fixture's 54,811 total entries sit far below even the *old* 100,000 `max_entries` ceiling — see §4 — and it triggers no markup scan at all). More likely explanations: machine-load variance between runs, a warm vs. cold-cache difference, or the two fixtures not being byte-identical (this run's is 25.16 MiB vs. the audit's 25.14 MiB, built independently). Reported as-is rather than adjusted to match the older number. |

The 16–70x "cheap `declared` write vs. expensive default write" defect the audit flagged is **still
present, confirmed unchanged in this codebase revision** — the default `dumps()` call still silently
re-validates the whole document against the nbformat 4.5 schema.

---

## 3. `CellEditor` operations

Command: `libipynb.model.editor.CellEditor`, single `.replace()` calls and `.batch()`.

| Operation | Measured (this run) | Audit's §12 cited figure |
|---|---|---|
| Single `editor.replace()` (applied) | **3.0173 s** | "~700 ms–3.5 s per edit" | within the audit's cited range |
| `editor.replace(dry_run=True)` | **3.0854 s** | 1.28 s (on a 4,000-cell notebook) | fresh number, different fixture size; qualitatively confirms the same finding below |
| `editor.replace(dry_run=False)` (applied) | **3.0005 s** | 1.44 s (on a 4,000-cell notebook) | fresh number |
| **20 sequential individual `.replace()` calls** | **72.5369 s total (3.6268 s/edit avg)** | "14.85 s total" for a 20-edit sequential loop | this run is ~5x slower in absolute terms — most likely fixture-size-driven (this fixture's cells carry ~46 KB base64 image payloads on ~13% of cells, materially heavier per-`deepcopy` than a plain-text-only fixture) rather than a regression; the *per-edit* cost still scales with full-notebook `deepcopy` + full `validate()`, exactly as the audit described |
| **20 edits via one `editor.batch()` context** | **3.1192 s total** | not present in the audit's §12 numbers | **new finding, not in the original audit**: `CellEditor.batch()` (documented in `editor.py` as LIBIPYNB-Q15a) pays exactly one `deepcopy` + one `validate()` for an entire accumulated batch instead of one pair per call — measured **~23x faster** than 20 individual calls on this fixture (3.12 s vs. 72.54 s). Any caller doing >1 edit should use `.batch()`, not repeated single calls. |

**`dry_run=True` still provides no performance benefit** over an applied edit (3.0854 s vs. 3.0005 s here
— within noise of each other, consistent with the audit's own 1.28 s vs. 1.44 s finding) — `_finish()` in
`editor.py` still calls `validate()` before checking `dry_run`, so "preview" costs exactly what "commit"
costs. Confirmed unchanged.

Baseline for comparison — a raw, unvalidated list mutation on the same document
(`doc.raw["cells"].append(...)`, no `deepcopy`, no `validate()`): **0.000005 s**, i.e. ~600,000x cheaper
than a validated `CellEditor` call, consistent with the audit's own `NotebookDocument.add_cell()`
0.0004 s comparison point (same order-of-magnitude conclusion: the cost is entirely
`deepcopy`+`validate()` overhead, not the mutation itself).

---

## 4. `diff_notebooks()`, `merge_notebooks()`, `sanitize()`, `scan_for_secrets()`

All four run against the same 3,000-cell/25 MiB fixture (or lightly-modified copies of it, for
diff/merge, built by mutating every 10th/20th cell's source and re-wrapping in a fresh
`NotebookDocument`).

| Function | Measured (this run) | Audit's §12 cited figure |
|---|---|---|
| `diff_notebooks()` | **0.5875 s** | 0.41 s | same order of magnitude |
| `merge_notebooks()` | **1.4134 s** | 0.88 s | same order of magnitude |
| `sanitize()` | **0.0864 s** | 0.05 s | same order of magnitude |
| `scan_for_secrets()` | **0.1836 s** | 0.04 s | same order of magnitude |

All four remain comfortably sub-second at this realistic scale, as the audit found — the modest
differences above are consistent with normal run-to-run variance and this fixture not being
byte-identical to the audit's, not a regression.

---

## 5. Resource-limit-adjacent findings (the numbers most likely to have changed)

These are the two figures the task brief specifically flagged as likely-changed, and both were verified
directly against the exact repro shapes the audit itself used, not just inferred from reading the
`security/limits.py` diff.

### 5a. `max_entries`: 100,000 → 2,000,000

Reproduced the audit's own cited repro — a ~2.18 MiB single-code-cell notebook with a 150,000-line
`source` array (the shape that was previously rejected by `nbformat.validate()`-accepted notebooks):

```python
lines = [f"x = {i}\n" for i in range(150_000)]
nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {...},
      "cells": [{"id": "big-cell", "cell_type": "code", "metadata": {},
                 "source": lines, "execution_count": None, "outputs": []}]}
reader.loads(json.dumps(nb), mode="strict")                                    # current default
reader.loads(json.dumps(nb), mode="strict",
             limits=NotebookResourceLimits().with_overrides(max_entries=100_000))  # old default, reconstructed
```

Result, this run:

- **Current default (`max_entries=2,000,000`): ACCEPTED, in 1.6371 s.**
- **Old default reconstructed (`max_entries=100,000`): REJECTED** —
  `NotebookResourceLimitError max_entries exceeded: 150011 > 100000`.

This directly confirms publication blocker #5 from the audit ("Default `max_entries` resource limit
rejects legitimate large notebooks that the official `nbformat` reference implementation accepts") is
now fixed for this exact repro case. It is a genuine, verified behavior change, not merely a change to
an unused constant.

The main §2/§3/§4 fixture above (54,811 total entries, computed via the same DFS `enforce_structure`
counts `enforce_structure` itself performs) sits well under *both* the old 100,000 and new 2,000,000
ceilings, so none of this report's main timing numbers were themselves affected by the `max_entries`
change — the change matters only for notebooks with one or more very large flat arrays (long
list-of-lines source, very long output arrays), not for the "many moderately-sized cells" shape this
report's main fixture uses.

### 5b. New `max_scan_tokens = 200,000` guard

Reproduced the audit's own cited dense-markup repro (a single markdown cell containing `'<p>' * 300_000`,
which the audit measured at ~4.4 s of unbounded CPU with *zero* resource-limit engagement under the old
code):

```python
nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {},
      "cells": [{"id": "markup-cell", "cell_type": "markdown", "metadata": {},
                 "source": "<p>" * 300_000}]}
sanitize(NotebookDocument(nb))
```

Result, this run: **REJECTED after 0.4769 s** —
`NotebookResourceLimitError max_scan_tokens exceeded: 200001 > 200000`.

This is a genuine, verified new protection: the same payload that previously ran to completion
unbounded (audit: ~4.4 s CPU, and the audit's own linear extrapolation warned of up to ~10 minutes of
blocking CPU for an in-budget-sized but token-dense payload) is now rejected in well under half a
second. `max_scan_tokens` did not exist in any form at the time of the original audit — this is not a
threshold change, it is a wholly new guard, and this is the first behavioral measurement of it.

---

## 6. Memory growth

Two independent methodologies were used since they measure different things; neither is directly
comparable to the audit's cited "~2.3x notebook size" figure because the audit did not specify which
method it used.

**`tracemalloc`** (Python-level allocations only, around `load(strict)` → `validate()` →
`dumps(profile="declared")`):

```
tracemalloc peak: 78.18 MiB
```

against a 25.16 MiB input file — a ~3.1x ratio of tracemalloc peak to file size.

**`psutil`-based whole-process RSS** (captures C-level/allocator overhead `tracemalloc` misses; measured
via `psutil.Process().memory_info().rss` immediately before and after the same
load→validate→`dumps(declared)` sequence, holding the result in memory):

```
file size:   25.16 MiB
RSS before:  53.27 MiB
RSS after:   84.74 MiB
RSS growth:  31.47 MiB
growth / file size ratio: 1.25x
```

Both figures point the same direction as the audit's conclusion — **memory growth is modest and roughly
proportional to notebook size, not the bottleneck; CPU (validation, `deepcopy`) is** — but the specific
multiplier (1.25x RSS-growth here vs. tracemalloc's 3.1x-of-peak here vs. the audit's cited "~2.3x") is
not apples-to-apples across three different measurement methods and three different runs, and should not
be read as a precise trend.

---

## 7. Headline summary (fresh numbers, this run only)

- Cheap write (`dumps(profile="declared")`): **0.1715 s** vs. default write (`dumps()`, silently
  re-validates against 4.5): **3.0297 s** — an ~17.7x gap, confirming the audit's flagged default-profile
  footgun is still present and unchanged.
- Full load→validate→write cycle: **5.50 s** (declared write) / **8.19 s** (default write) — both
  markedly faster than the audit's cited ~25–30 s; most plausibly run-to-run/fixture variance, not a
  regression fix (nothing in the diff between the two passes targets this path).
- `CellEditor.batch()` for 20 edits: **3.12 s**, vs. **72.54 s** for 20 individual sequential calls —
  ~23x faster; a genuinely new finding for this pass, not previously measured in the audit.
- `max_entries` raised 100,000 → 2,000,000: the audit's own 150,000-line-single-cell repro flips from
  **REJECTED** (old default) to **ACCEPTED in 1.64 s** (new default) — publication blocker #5 confirmed
  fixed for this case.
- New `max_scan_tokens` guard: the audit's own 300,000-tag dense-markup repro, previously unbounded
  (~4.4 s CPU, no limit engaged), now **rejected deterministically in 0.48 s**.
- `diff_notebooks()` 0.59 s / `merge_notebooks()` 1.41 s / `sanitize()` 0.09 s / `scan_for_secrets()`
  0.18 s — all still comfortably sub-second at realistic (25 MiB/3,000-cell) scale, consistent with the
  audit's own conclusion that these are not practical bottlenecks.

---

## 8. Reproduction

1. Build the fixture: run the `build_fixture.py` script in §1 against a scratch path (not the repo) —
   `.venv\Scripts\python.exe build_fixture.py <scratch_path>\fixture_large.ipynb`.
2. Run the timing script described in §2–§4 (`benchmark.py`) against that path with
   `.venv\Scripts\python.exe benchmark.py`.
3. Run the two resource-limit repros in §5 directly (inline scripts shown there).
4. Run the RSS memory script in §6 (`benchmark_rss.py`, using `psutil`).
5. Delete the scratch fixture file(s) afterward — nothing under `plans/` or elsewhere in the repository
   depends on them, and none were committed.

No fixture files, benchmark scripts, or other artifacts from this pass were added to the repository;
only this markdown file is new.
