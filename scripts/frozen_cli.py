"""PyInstaller entry point dispatching both published command names."""

from __future__ import annotations

import sys
from pathlib import Path

from comh.cli import main as comh_main
from docx_harness.cli import main as docx_main


def main() -> int:
    executable = Path(sys.argv[0]).stem.casefold()
    return docx_main() if executable == "docx-harness" else comh_main()


if __name__ == "__main__":
    raise SystemExit(main())
