"""LIBIPYNB-Q4: enables ``python -m libipynb.cli`` -- a common Python CLI
invocation convention (e.g. when the installed console script isn't on
PATH, or when explicitly selecting a venv interpreter). Both other
supported invocation styles (the ``libipynb`` console script and
``from libipynb.cli import main``) already worked fine; this only adds the
third one."""

from __future__ import annotations

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
