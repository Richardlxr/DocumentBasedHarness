"""Content hashing for lineage tracking.

Every artifact records the hash of its own file and of its upstream files at the
moment it was produced. Staleness is always recomputed live from current file
hashes; nothing is regenerated automatically.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 16


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hash_dir(path: Path) -> str:
    """Hash a directory by sorted (relative path, file hash) pairs.

    Used for ``sources/`` so that any added, removed, or changed source file
    invalidates downstream evidence.
    """
    entries: list[str] = []
    if path.exists():
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            rel = child.relative_to(path).as_posix()
            entries.append(f"{rel}:{hash_file(child)}")
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return "sha256-dir:" + digest


def short(hash_value: str | None) -> str:
    if not hash_value:
        return "-"
    return hash_value.split(":", 1)[-1][:8]
