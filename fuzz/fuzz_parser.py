"""Fuzz libipynb.loads() -- the raw-bytes JSON parser boundary.

This is the actual untrusted-input entry point: nothing has validated this
data before it reaches loads(). See fuzz/README.md for scope and platform
notes (atheris is Linux-only).
"""

from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from libipynb import NotebookError, loads

# Every recovery mode reachable from untrusted input -- a caller might
# choose any of these, and each has its own code path through the parser.
_MODES = ("strict", "preservation", "recovery")


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    mode = _MODES[fdp.ConsumeIntInRange(0, len(_MODES) - 1)]
    remaining = fdp.ConsumeBytes(fdp.remaining_bytes())
    try:
        loads(remaining, mode=mode)
    except NotebookError:
        pass  # Rejecting malformed/oversized/adversarial input is correct.
    except UnicodeDecodeError:
        pass  # Invalid UTF-8 is expected adversarial input, not a bug.


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
