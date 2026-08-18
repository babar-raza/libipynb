# Independence and Packaging Audit — 2026-08-18

This is a standing, re-runnable audit of libipynb's packaging independence: that a
clean build produces artifacts containing no internal/organizational leakage, that
those artifacts install and work standalone (no reliance on the source checkout or
dev-only tooling), and that the import boundary between the core library and
oracle/exec-extra tooling holds. It supersedes the one-time prose writeup in
`plans/forensic-capability-audit-2026-08-18.md` §16 — the methodology there is
unchanged, but every number below is freshly executed, not copied forward.

**Trigger for this specific run:** `pyproject.toml`'s `[project.urls]` block
(`Repository = "https://gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb"`, a
private internal GitLab instance) was removed as a fix for the finding recorded in
§16/§17 item 4 of the forensic audit — that URL was leaking verbatim into the built
wheel's `dist-info/METADATA`. This run both re-establishes the standing checks and
serves as first-build confirmation that the fix actually took effect.

## Environment

- Date: 2026-08-18
- Repo: `libipynb`, branch `master`, commit `88aa112bb1d907c0c0272fa64fe0663c5b75a0f7`
  (local `master` ahead of `origin/master`; working tree has the usual in-flight
  modifications from prior sessions — see `git status` output below)
- Python (`.venv\Scripts\python.exe --version`): `Python 3.13.2`
- OS: Windows 11 Pro, 10.0.26200 (Alienware M18), via Git Bash / PowerShell
- Build frontend: `python -m build` (PEP 517, `setuptools` backend, isolated venv)

## 0. Provenance context

```
$ git status
On branch master
Your branch is up to date with 'origin/master'.
Changes not staged for commit: (26 modified files under src/libipynb, tests/, plus
  .gitlab-ci.yml, CHANGELOG.md, CONTRIBUTING.md, README.md, SECURITY.md, pyproject.toml)
Untracked files: .supervisor/, ARCHITECTURE.md, plans/forensic-capability-audit-2026-08-18.md,
  plans/libipynb-feature-analysis-and-execution.md, plans/production-hardening-plan.md,
  src/libipynb/_internal/paths.py, src/libipynb/cli/__main__.py,
  tests/oracle/test_diff_parity.py, tests/unit/test_internal_paths.py,
  tests/unit/test_obligation_surrogate_handling.py
```

```
$ git log -3 --oneline
88aa112 fix(execution): make execute_async cancellation deterministic, not just leak-free
4fdb295 feat(execution): add real Jupyter-kernel-protocol execution engine (LIBIPYNB-P4a-1/P4b/P4c)
f2fd4ec feat(full-parity): close LIBIPYNB-P1/P2/P3a/P3b/P3c/P6/P7/P8/P9, fixing a broken import in HEAD
```

Diff of the actual fix under audit (`pyproject.toml`):

```diff
@@ -34,7 +34,6 @@ test = [
     "pytest-timeout>=2.3",
     "hypothesis>=6.100",
     "nbformat>=5.10",
-    "pyyaml>=6.0",
 ]
@@ -42,7 +41,7 @@ fuzz = ["atheris>=2.3; sys_platform == 'linux'"]
-exec = ["jupyter_client>=8.6", "nbclient>=0.10"]
+exec = ["jupyter_client>=8.6", "nbclient>=0.10", "nbformat>=5.10"]
@@ -61,9 +60,6 @@ export = ["jupytext>=1.16", "nbconvert>=7.16"]
 [project.scripts]
 libipynb = "libipynb.cli:main"

-[project.urls]
-Repository = "https://gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb"
-
 [tool.setuptools.packages.find]
```

The `[project.urls]` block was deleted outright (not merely rewritten to a public
URL) — so this run also confirms the fix behaves the way a full removal predicts:
no `Home-page`/`Project-URL` field of any kind should appear in built metadata,
not just an absence of the string "recruitize".

---

## 1. Clean build

**Command:**
```
rm -rf dist build src/libipynb.egg-info
.venv\Scripts\python.exe -m build --wheel --sdist
```

**Result:** `Successfully built libipynb-0.1.0-py3-none-any.whl and libipynb-0.1.0.tar.gz`

Artifacts produced (`ls -la dist/`):
```
libipynb-0.1.0.tar.gz              136557 bytes
libipynb-0.1.0-py3-none-any.whl    156116 bytes
```

Both the wheel and sdist builds completed via isolated build environments
(`venv+pip`, `setuptools>=80.9.0`) with no errors or warnings from `build`,
`egg_info`, `bdist_wheel`, or `sdist`.

**Verdict: PASS.**

---

## 2. Wheel metadata — internal URL check

**Command:**
```
unzip -p dist/libipynb-*.whl "*/METADATA" | grep -i recruitize
echo "EXIT_CODE=$?"
```

**Output:**
```
EXIT_CODE=1
```

Zero matches (grep exit code 1 = no lines matched), as expected. The full
`METADATA` file was also dumped and inspected by hand: there is no
`Home-page`/`Project-URL`/`Repository` field at all — the `[project.urls]` table
was removed outright, not merely re-pointed, so no residual URL field of any kind
survives into the built artifact. Metadata now starts directly from
`Description-Content-Type` into the extras/`Requires-Dist` block with no URL
fields present anywhere.

**Verdict: PASS** — internal GitLab URL is fully absent from the built wheel's
metadata; this is a genuine fix, confirmed against a real, fresh artifact, not
just the source `pyproject.toml`.

---

## 3. Wheel and sdist file-list leakage check

**Command:**
```
unzip -l dist/libipynb-*.whl
unzip -l dist/libipynb-*.whl | grep -iE "tests/|plans/|gitlab-ci|\.supervisor"
tar tzf dist/libipynb-*.tar.gz | grep -iE "tests/|plans/|gitlab-ci|\.supervisor"
```

**Wheel contents:** 56 files total — exclusively `libipynb/**/*.py`,
`libipynb/py.typed`, the 6 `libipynb/validation/schemas/*.json` files, and
`libipynb-0.1.0.dist-info/{LICENSE,NOTICE,METADATA,WHEEL,entry_points.txt,
top_level.txt,RECORD}`. No `tests/`, `plans/`, `.gitlab-ci.yml`, or
`.supervisor/` entries.

**Grep results:** both the wheel-file-list grep and the sdist (`tar.gz`) file-list
grep returned exit code 1 (no matches) for all four forbidden patterns.

**Verdict: PASS** — neither the wheel nor the sdist leaks test fixtures, planning
documents, CI config, or the `.supervisor/` directory.

---

## 4. Clean install smoke test

**Setup:**
```
python -m venv /tmp/libipynb-indep-check   # throwaway venv, outside the repo
/tmp/libipynb-indep-check/Scripts/python.exe -m pip install --quiet \
    dist/libipynb-0.1.0-py3-none-any.whl
```
Install completed with no errors (pip only emitted its routine "new pip version
available" notice).

All four verification commands were run from `/tmp` (outside the repo directory
entirely), using only the throwaway venv's interpreter/scripts:

**a. Core import:**
```
$ python -c "from libipynb import NotebookDocument, load, validate, NotebookError; print('wheel import OK')"
wheel import OK
```

**b. Resolved from site-packages, not the source tree:**
```
$ python -c "import libipynb, pathlib; p = pathlib.Path(libipynb.__file__).resolve(); assert 'site-packages' in str(p); print('resolved from', p)"
resolved from C:\Users\prora\AppData\Local\Temp\libipynb-indep-check\Lib\site-packages\libipynb\__init__.py
```

**c. Installed console script (`[project.scripts]` entry point):**
```
$ libipynb --help
usage: libipynb [-h] COMMAND ...

Production Jupyter Notebook toolkit.

positional arguments:
  COMMAND
    probe      Detect whether a file is a Jupyter Notebook and report its profile.
    inspect    Load a notebook and print basic structure information.
    validate   Validate a notebook against the nbformat schema.
    sanitize   Scan a notebook for active content and security hazards.
    upgrade    Upgrade a notebook to nbformat 4.5 and print the conversion ledger.
    normalize  Clean up a notebook: strip outputs, execution counts, and selected metadata...
    convert    Convert a notebook between nbformat versions (4.0 through 4.5).
    diff       Diff two notebooks by cell identity and report structural changes.
    merge      Three-way merge two notebooks against a common ancestor by cell identity.
    execute    Execute a notebook's code cells through a real local Jupyter kernel...
    analytics  Report structural analytics for a notebook...
    trust      Sign, verify, or revoke content-addressed notebook trust using a persistent HMAC store.

options:
  -h, --help   show this help message and exit
```

**d. `__main__.py` module entry point:**
```
$ python -m libipynb.cli --help
```
Produced byte-identical output to (c) above — the `__main__.py` entry point
(`src/libipynb/cli/__main__.py`, currently untracked in git per the status above)
correctly delegates to the same CLI.

**Verdict: PASS** — the wheel installs standalone in a fresh venv with no access
to the repo's source tree, and all four checks (import, site-packages resolution,
console script, module entry point) behave correctly.

---

## 5. Import-boundary enforcement

**Command:**
```
.venv\Scripts\python.exe -m pytest tests/unit/test_import_boundary.py -v
```

**Result:**
```
tests/unit/test_import_boundary.py::test_the_checker_actually_detects_a_forbidden_import PASSED
tests/unit/test_import_boundary.py::test_the_checker_does_not_flag_unrelated_imports PASSED
tests/unit/test_import_boundary.py::test_the_checker_flags_from_import_form_too PASSED
tests/unit/test_import_boundary.py::test_jupyter_client_and_nbclient_are_still_flagged_outside_the_allowed_file PASSED
tests/unit/test_import_boundary.py::test_jupyter_client_and_nbclient_are_allowed_only_in_the_kernel_backend_file PASSED
tests/unit/test_import_boundary.py::test_the_kernel_backend_exception_does_not_widen_to_other_forbidden_tools PASSED
tests/unit/test_import_boundary.py::test_no_source_file_imports_an_oracle_or_exec_extra_tool PASSED

7 passed in 0.46s
```

**Verdict: PASS** — 7/7 tests pass. The static AST-based checker confirms no file
under `src/libipynb` imports an oracle/exec-extra tool (`nbdime`, `nbconvert`,
`papermill`, `nbstripout`, `jupyter_client`, `nbclient`) outside the one explicitly
sanctioned kernel-backend file.

---

## 6. Example scripts (mirrors CI's `package-examples` job)

**Command 1:**
```
$ .venv\Scripts\python.exe examples/load_and_inspect.py
Notebook format: nbformat 4.5
Total cells:     9
Code cells:      4
Markdown cells:  5
  Cell 0: [markdown] # nbconvert latex test
  ...
Kernel: Python 3 (ipykernel)
EXIT_CODE=0
```

**Command 2:**
```
$ .venv\Scripts\python.exe examples/validate_notebook.py
Valid notebooks: (16 fixtures, all VALID)
Invalid notebooks: (4 fixtures, all correctly INVALID with expected diagnostic codes:
  IPYNB_SCHEMA_REQUIRED, IPYNB_CELLS, IPYNB_PARSE, IPYNB_SCHEMA_TYPE, IPYNB_VERSION,
  IPYNB_SCHEMA_MINIMUM, IPYNB_SCHEMA_ADDITIONALPROPERTIES)
EXIT_CODE=0
```

Both scripts ran to completion with no traceback and exit code 0.

**Verdict: PASS.**

---

## 7. Cleanup

```
rm -rf /tmp/libipynb-indep-check
rm -rf dist build src/libipynb.egg-info
```

Confirmed via `ls` (all four paths report "No such file or directory") and via
`git status --short`, which after cleanup shows the exact same set of modified/
untracked repository files as before this audit began — no stray `dist/`,
`build/`, or `*.egg-info` directories were left in the working tree.

---

## Summary

| # | Check | Verdict |
|---|-------|---------|
| 2 | Clean build (`build --wheel --sdist`) | **PASS** — `libipynb-0.1.0-py3-none-any.whl` + `libipynb-0.1.0.tar.gz` built successfully |
| 3 | Wheel `METADATA` contains no internal URL (`grep -i recruitize`) | **PASS** — exit code 1, zero matches; `[project.urls]` field absent entirely |
| 4 | Wheel/sdist file list excludes `tests/`, `plans/`, `.gitlab-ci.yml`, `.supervisor/` | **PASS** — 56-file wheel contains only the package + dist-info; sdist likewise clean |
| 5 | Clean install smoke test (fresh venv, import / site-packages resolution / console script / module entry point) | **PASS** — all 4 sub-checks succeeded from outside the repo directory |
| 6 | `tests/unit/test_import_boundary.py` | **PASS** — 7/7 tests passed |
| 7 | Example scripts (`load_and_inspect.py`, `validate_notebook.py`) | **PASS** — both exited 0, no tracebacks |

**Overall: the internal-GitLab-URL packaging-metadata leak (forensic audit §16/§17
item 4) is confirmed fixed in a fresh, from-scratch build.** All six independence/
packaging checks pass on this run with no exceptions or caveats.
