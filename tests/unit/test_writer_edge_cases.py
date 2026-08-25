"""Edge case coverage for codec/writer.py."""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from libipynb import dump, dumps, loads
from libipynb.errors import NotebookWriteError


def _minimal_doc() -> object:
    return loads(
        '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}',
        mode="preservation",
    )


class TestProfileVersion:
    def test_declared_profile(self) -> None:
        doc = _minimal_doc()
        text = dumps(doc, profile="declared")
        assert '"nbformat": 4' in text

    def test_nbformat_prefix_stripped(self) -> None:
        doc = _minimal_doc()
        text = dumps(doc, profile="nbformat-4.5")
        assert '"nbformat": 4' in text

    def test_invalid_profile_raises(self) -> None:
        doc = _minimal_doc()
        with pytest.raises(ValueError, match="profile must be"):
            dumps(doc, profile="3.0")

    def test_declared_with_bad_version_raises(self) -> None:
        raw = {"nbformat": True, "nbformat_minor": 5, "metadata": {}, "cells": []}
        with pytest.raises(NotebookWriteError, match="declared profile"):
            dumps(raw, profile="declared")


class TestDeclaredProfileVersionValidation:
    """LIBIPYNB-Q58 (mutation-testing follow-up): `_profile_version`'s
    declared-profile check is a 6-condition `or`-chain over `major`/`minor`
    (each: bool-check, type-check, and value-check). The only pre-existing
    test (`test_declared_with_bad_version_raises`, `major=True`) exercises
    just the first condition -- every OTHER condition could be silently
    broken (e.g. `or` weakened to `and` between two adjacent conditions)
    without any test noticing, since `major=True` alone already makes the
    whole chain True regardless of the rest. Each test below sets exactly
    one condition True while holding every earlier condition in the chain
    False -- MC/DC-style isolation for a short-circuiting `or`, chosen
    from `mutmut show`'s actual survived-mutant diffs rather than guessed.

    `major=4.0` (a float, not `major="4"`) is deliberate for the
    not-an-int case: mutmut also pairs `not isinstance(major, int)` with
    the NEXT condition (`major != 4`) via `and` -- a string majorlike "4"
    would leave that pairing undetected, since `"4" != 4` is *also* True
    and would raise anyway either way. `4.0 == 4` is True (Python), so
    `major != 4` is False for a float -- isolating the not-an-int
    condition from the not-equal-to-4 condition specifically.
    """

    def test_major_not_an_int_is_rejected(self) -> None:
        raw = {"nbformat": 4.0, "nbformat_minor": 5, "metadata": {}, "cells": []}
        with pytest.raises(NotebookWriteError, match="declared profile"):
            dumps(raw, profile="declared")

    def test_major_is_an_int_but_not_4_is_rejected(self) -> None:
        raw = {"nbformat": 5, "nbformat_minor": 5, "metadata": {}, "cells": []}
        with pytest.raises(NotebookWriteError, match="declared profile"):
            dumps(raw, profile="declared")

    def test_minor_being_a_bool_is_rejected_even_though_major_is_valid(self) -> None:
        raw = {"nbformat": 4, "nbformat_minor": True, "metadata": {}, "cells": []}
        with pytest.raises(NotebookWriteError, match="declared profile"):
            dumps(raw, profile="declared")

    def test_minor_not_an_int_is_rejected(self) -> None:
        raw = {"nbformat": 4, "nbformat_minor": "5", "metadata": {}, "cells": []}
        with pytest.raises(NotebookWriteError, match="declared profile"):
            dumps(raw, profile="declared")

    def test_negative_minor_is_rejected(self) -> None:
        raw = {"nbformat": 4, "nbformat_minor": -1, "metadata": {}, "cells": []}
        with pytest.raises(NotebookWriteError) as excinfo:
            dumps(raw, profile="declared")
        # Exact message, not just a substring match: a mutmut-confirmed
        # survivor mutated this literal (wrapped it in "XX...XX" marker
        # text) without any existing test noticing, since every other
        # test here only checked the exception TYPE or a loose substring.
        assert str(excinfo.value) == "declared profile requires a non-negative nbformat 4.x version"


class TestProfileVersionEquivalentMutants:
    """LIBIPYNB-Q58: 4 of `_profile_version`'s 9 mutmut-survived mutants
    are genuinely EQUIVALENT -- no test, however constructed, can
    distinguish them from the original code, so they are documented here
    rather than force-killed with a meaningless assertion (the session's
    own standing rule: a survived mutant is either fixed with a real
    regression test or explicitly justified as unkillable).

    1. Pairing `isinstance(major, bool)` with `not isinstance(major, int)`
       via `and` (instead of `or`): `isinstance(x, bool)` is True only for
       `x is True` or `x is False`, and both of those are `!= 4` (the
       NEXT condition in the chain) -- so whenever the first condition
       would matter, the third condition (`major != 4`) is *already* True
       independently, making the whole chain True regardless of how the
       first two conditions are combined. Confirmed by direct proof, not
       assumption: for every bool value of `major`, `major != 4` holds.

    2. The final `selected.split(".", 1)` call (limit=1) is only ever
       reached after `selected not in {"4.0", ..., "4.5"}` has already
       raised for anything else -- every member of that set has EXACTLY
       one "." character, so `split(".", 1)` == `split(".", 2)` ==
       `split(".")` == `rsplit(".", 1)` for every reachable input. Three
       separate mutmut mutants target this same unreachable-divergence
       call (dropping the limit, using `rsplit`, using limit=2).
    """


class TestVersionMismatch:
    def test_explicit_upgrade_required(self) -> None:
        doc = _minimal_doc()  # nbformat=4, nbformat_minor=5
        with pytest.raises(NotebookWriteError) as excinfo:
            dumps(doc, profile="4.4")
        # LIBIPYNB-Q58: strengthened from a loose substring match after
        # mutmut found the .code and .context attributes entirely
        # untested (message-only assertions can't see either).
        assert "requires explicit upgrade" in str(excinfo.value)
        assert excinfo.value.code == "IPYNB_EXPLICIT_UPGRADE_REQUIRED"
        assert excinfo.value.context == {
            "declared_version": (4, 5),
            "target_version": (4, 4),
        }


class TestDumpsEquivalentMutants:
    """LIBIPYNB-Q58: 2 of `dumps`'s 3 mutmut-survived mutants
    (`ensure_ascii=False` -> `ensure_ascii=None`, `allow_nan=False` ->
    `allow_nan=None`) are genuinely EQUIVALENT, confirmed empirically
    against CPython's actual `json` module, not assumed: both parameters
    are used via a plain `if ensure_ascii:` / `if allow_nan:` truthiness
    check internally (`json/encoder.py`), never an `is False` identity
    check or a type check -- `None` and `False` are both falsy, so
    `json.dumps(..., ensure_ascii=None)` and `json.dumps(...,
    allow_nan=None)` produce byte-identical output and identical
    ValueError-on-NaN behavior to `ensure_ascii=False`/`allow_nan=False`,
    for every possible input. No test, however constructed, can
    distinguish them."""


class TestDumpErrors:
    def test_non_serializable_content_raises(self) -> None:
        raw = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"bad": object()},
            "cells": [],
        }
        with pytest.raises(NotebookWriteError, match="cannot serialize"):
            dumps(raw, profile="declared")

    def test_partial_stream_write(self) -> None:
        class LimitedWriter:
            def write(self, text: str) -> int:
                return 1

        doc = _minimal_doc()
        with pytest.raises(NotebookWriteError) as excinfo:
            dump(doc, LimitedWriter(), profile="declared")  # type: ignore[arg-type]
        # LIBIPYNB-Q58: exact match, not a substring -- a mutmut-confirmed
        # survivor wrapped this literal in "XX...XX" marker text, which a
        # loose `match="partial write"` substring check still contains.
        assert str(excinfo.value) == "notebook destination accepted a partial write"

    def test_stream_write_os_error(self) -> None:
        class FailWriter:
            def write(self, text: str) -> int:
                raise OSError("disk full")

        doc = _minimal_doc()
        with pytest.raises(NotebookWriteError, match="cannot write"):
            dump(doc, FailWriter(), profile="declared")  # type: ignore[arg-type]

    def test_file_write_to_nonexistent_dir(self, tmp_path: Path) -> None:
        doc = _minimal_doc()
        bad_path = tmp_path / "no_such_dir" / "out.ipynb"
        with pytest.raises(NotebookWriteError, match="cannot write"):
            dump(doc, bad_path, profile="declared")


class TestDumpSuccess:
    def test_stream_write(self) -> None:
        buf = io.StringIO()
        doc = _minimal_doc()
        dump(doc, buf, profile="declared")
        assert '"nbformat": 4' in buf.getvalue()

    def test_file_write(self, tmp_path: Path) -> None:
        doc = _minimal_doc()
        dest = tmp_path / "out.ipynb"
        dump(doc, dest, profile="declared")
        assert dest.exists()
        content = dest.read_text(encoding="utf-8")
        assert '"nbformat": 4' in content

    def test_default_indent_matches_dumps_own_default_of_one_space(self, tmp_path: Path) -> None:
        """LIBIPYNB-Q58: `dump()`'s own `indent: int | None = 1` default
        was untested -- every existing test either passed `indent=`
        explicitly or only checked for content, never the actual
        whitespace width, so a mutmut-confirmed survivor silently changed
        the default to 2 without anything noticing."""
        doc = _minimal_doc()
        dest = tmp_path / "out.ipynb"
        dump(doc, dest, profile="declared")  # no indent= -- exercises the default
        content = dest.read_text(encoding="utf-8")
        assert '\n "cells"' in content
        assert '\n  "cells"' not in content


class TestAsMapping:
    """LIBIPYNB-Q58: `_as_mapping`'s final `raise TypeError(...)` branch
    had its exception TYPE covered elsewhere but never its message --
    mutmut confirmed all 4 of its survived mutants are string-literal
    changes on that one message (`None`, empty, lowercased, uppercased)."""

    def test_a_raw_mapping_is_accepted_without_a_notebookdocument_wrapper(self) -> None:
        raw = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}
        text = dumps(raw, profile="declared")
        assert '"nbformat": 4' in text

    def test_a_value_that_is_neither_a_notebookdocument_nor_a_mapping_is_rejected(self) -> None:
        with pytest.raises(NotebookWriteError) as excinfo:
            dumps(42, profile="declared")  # type: ignore[arg-type]
        assert (
            str(excinfo.value)
            == "cannot serialize notebook: document must be an NotebookDocument or mapping"
        )


class TestNormalizedEarlyReturnAndValidation:
    """LIBIPYNB-Q58: `_normalized`'s own early-return check
    (`profile == "declared" or (isinstance(profile, str) and
    profile.removeprefix("nbformat-") == "declared")`) and its
    schema-validation-failure path were both, in different ways,
    untested before this: the existing `test_nbformat_prefix_stripped`
    uses `profile="nbformat-4.5"`, which never touches either the second
    clause of the early-return check OR the validation-failure branch --
    the resolved version there ("4.5") happens to also be schema-valid,
    so success looks identical whichever path is taken.
    """

    def test_nbformat_prefixed_declared_profile_also_skips_validation(self) -> None:
        """`profile="nbformat-declared"` is the only value where the
        early-return's FIRST clause (`profile == "declared"` literally)
        is False but the SECOND clause
        (`profile.removeprefix("nbformat-") == "declared"`) is True --
        isolating it from mutmut's confirmed `or`-to-`and` mutant here.
        The notebook is deliberately schema-INVALID (missing
        `metadata.kernelspec.display_name`) so reaching `validate()` at
        all would raise: this proves the early return actually happened,
        not merely that `dumps()` happened to succeed either way."""
        raw = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3"}},
            "cells": [],
        }
        text = dumps(raw, profile="nbformat-declared")
        assert '"kernelspec"' in text

    def test_schema_invalid_notebook_raises_with_full_diagnostic_context(self) -> None:
        """The `if not report.is_valid: raise NotebookWriteError(...)`
        branch (message, `.code`, and `.context` built from the first
        validation error) had zero coverage before this -- every other
        test's document was either schema-valid or failed earlier
        (version mismatch), never reaching this specific branch."""
        raw = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3"}},  # missing display_name
            "cells": [],
        }
        with pytest.raises(NotebookWriteError) as excinfo:
            dumps(raw)  # default profile -> "4.5", schema-validating
        assert (
            str(excinfo.value)
            == "notebook is not valid for nbformat 4.5: 'display_name' is a required property"
        )
        assert excinfo.value.code == "IPYNB_SCHEMA_REQUIRED"
        assert excinfo.value.context == {
            "path": ("metadata", "kernelspec", "display_name"),
            "error_count": 1,
        }


class TestNormalizedEquivalentMutants:
    """LIBIPYNB-Q58: 4 of `_normalized`'s 30 mutmut-survived mutants are
    genuinely EQUIVALENT.

    1. Mutating the early-return check's FIRST literal
       (`profile == "declared"` -> `profile == "XXdeclaredXX"` /
       `"DECLARED"`): the only value for which the ORIGINAL first clause
       is True is the string `"declared"` itself, and for that exact
       value the SECOND clause
       (`profile.removeprefix("nbformat-") == "declared"`) is *also*
       always True (`"declared"` doesn't start with `"nbformat-"`, so
       `removeprefix` is a no-op, and it trivially equals itself) -- the
       `or`'s overall truth value is identical whichever literal the
       first clause is compared against, since the second clause already
       covers every case where the first would have mattered.

    2. The `validate(source, profile=f"nbformat-{major}.{minor}")` call's
       `profile=` argument (dropped to `None`, or omitted entirely --
       both fall back to `validate()`'s own default, `"declared"`): this
       line is only reached after the PRECEDING check in the same
       function (`if (declared_major, declared_minor) != (major,
       minor): raise ...`) has already confirmed the document's own
       declared version equals the resolved target version -- so
       `profile="declared"` (validate against the document's own
       version) and `profile=f"nbformat-{major}.{minor}"` (validate
       against that exact version explicitly) are PROVABLY validating
       against the identical schema for every input that reaches this
       line. Confirmed empirically, not just argued: `validate(doc,
       profile="declared")` and `validate(doc, profile="nbformat-4.5")`
       produce byte-identical `ValidationReport` errors (same code,
       message, and location) for the schema-invalid fixture used
       above.
    """


class TestDumpTempFileConstruction:
    """LIBIPYNB-Q58: `dump()`'s `tempfile.mkstemp(dir=real_path.parent,
    suffix=".tmp")` and `os.fdopen(fd, "w", encoding="utf-8",
    newline="\\n")` calls are both load-bearing for correctness reasons
    documented in `dump()`'s own docstring (same-filesystem atomicity;
    deterministic, locale-independent output) but the temp file is
    renamed away (or deleted) before any assertion could inspect it
    directly -- mutmut confirmed 11 survived mutants across both calls'
    keyword arguments. Spying on the real calls (still delegating to the
    real implementation) is the only way to observe the exact arguments
    used, independent of whatever the current OS locale happens to be."""

    def test_mkstemp_uses_the_destinations_own_directory_and_the_tmp_suffix(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls: list[dict[str, Any]] = []
        real_mkstemp = tempfile.mkstemp

        def spy_mkstemp(*args: Any, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return real_mkstemp(*args, **kwargs)

        monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
        doc = _minimal_doc()
        dest = tmp_path / "out.ipynb"

        dump(doc, dest, profile="declared")

        assert len(calls) == 1
        assert calls[0]["dir"] == dest.parent
        assert calls[0]["suffix"] == ".tmp"

    def test_fdopen_uses_explicit_utf8_encoding_and_unix_newlines(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls: list[dict[str, Any]] = []
        real_fdopen = os.fdopen

        def spy_fdopen(fd: int, *args: Any, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return real_fdopen(fd, *args, **kwargs)

        monkeypatch.setattr(os, "fdopen", spy_fdopen)
        doc = _minimal_doc()
        dest = tmp_path / "out.ipynb"

        dump(doc, dest, profile="declared")

        assert len(calls) == 1
        assert calls[0]["encoding"] == "utf-8"
        assert calls[0]["newline"] == "\n"


class TestDumpTempFileCleanup:
    def test_a_cleanup_unlink_failure_does_not_mask_the_original_write_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """LIBIPYNB-Q58: `except BaseException: with
        contextlib.suppress(OSError): os.unlink(tmp)` is dump()'s
        best-effort cleanup after a write failure -- it must swallow a
        SECOND failure (the temp file already being gone) so the
        ORIGINAL failure is what actually propagates. Simulated here by
        making the write itself both fail AND remove the temp file out
        from under the cleanup step, so `os.unlink(tmp)` genuinely raises
        `FileNotFoundError` (a real `OSError`) inside the `suppress`
        block -- not just a hypothetical."""
        real_mkstemp = tempfile.mkstemp
        captured_path: list[str] = []

        def spy_mkstemp(*args: Any, **kwargs: Any) -> Any:
            fd, path = real_mkstemp(*args, **kwargs)
            captured_path.append(path)
            return fd, path

        def failing_fdopen(fd: int, *args: Any, **kwargs: Any) -> Any:
            # os.fdopen(fd, ...) is where the raw fd from mkstemp() would
            # normally become a file object -- close it directly (no
            # write ever happens) and delete the temp file out from
            # under the pending cleanup step, then fail exactly as a
            # real write error would.
            os.close(fd)
            os.unlink(captured_path[-1])
            raise OSError("simulated write failure")

        monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
        monkeypatch.setattr(os, "fdopen", failing_fdopen)
        doc = _minimal_doc()
        dest = tmp_path / "out.ipynb"

        with pytest.raises(NotebookWriteError, match="cannot write notebook"):
            dump(doc, dest, profile="declared")
