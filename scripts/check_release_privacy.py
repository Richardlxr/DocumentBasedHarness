#!/usr/bin/env python3
"""Reject private run data and machine-specific paths before publishing."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PUBLIC_RUN = "runs/sample-cache-latency/"
PATH_PATTERNS = {
    "macOS user directory": re.compile(r"/" r"Users/(?!<USER>/|USERNAME/)[^/\s]+/"),
    "Windows user directory": re.compile(
        r"[A-Za-z]:\\Users\\(?!<USER>\\|USERNAME\\)[^\\\s]+\\",
        re.IGNORECASE,
    ),
}


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [root / value.decode("utf-8") for value in result.stdout.split(b"\0") if value]


def inspect(root: Path) -> list[str]:
    errors: list[str] = []
    for path in tracked_files(root):
        relative = path.relative_to(root).as_posix()
        if relative.startswith("runs/") and not relative.startswith(PUBLIC_RUN):
            errors.append(f"private run path is tracked: {relative}")
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in PATH_PATTERNS.items():
            if pattern.search(content):
                errors.append(f"{label} found in tracked text: {relative}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = inspect(root)
    if errors:
        print("release privacy check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("release privacy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
