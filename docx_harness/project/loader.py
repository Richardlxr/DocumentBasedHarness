from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path
from threading import RLock
from types import ModuleType

from ..errors import DocumentError
from .config import ProjectConfig

_MODULE_LOAD_LOCK = RLock()


def _project_python_files(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    excluded = {".git", ".venv", ".workspace", "__pycache__", "build"}
    for current, directories, filenames in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in excluded)
        current_path = Path(current)
        paths.extend(current_path / name for name in sorted(filenames) if name.endswith(".py"))
    return tuple(paths)


def _project_python_fingerprint(root: Path) -> tuple[str, tuple[Path, ...]]:
    digest = hashlib.sha256()
    paths = _project_python_files(root)
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12], paths


def _discard_project_bytecode(paths: tuple[Path, ...]) -> None:
    for path in paths:
        try:
            Path(importlib.util.cache_from_source(str(path))).unlink(missing_ok=True)
        except (NotImplementedError, ValueError):
            continue


def load_project_module(config: ProjectConfig) -> ModuleType:
    """Load Project Python in a path- and content-addressed isolated namespace."""

    root_identity = hashlib.sha256(str(config.root).encode("utf-8")).hexdigest()[:12]
    source_identity, source_paths = _project_python_fingerprint(config.root)
    package_name = (
        f"_docx_harness_project_{config.name.replace('-', '_')}_{root_identity}_{source_identity}"
    )
    module_name = f"{package_name}.extensions"

    with _MODULE_LOAD_LOCK:
        existing = sys.modules.get(module_name)
        if isinstance(existing, ModuleType):
            return existing

        _discard_project_bytecode(source_paths)
        importlib.invalidate_caches()

        package = ModuleType(package_name)
        package.__package__ = package_name
        package.__path__ = [str(config.root)]
        package.__file__ = str(config.root)
        sys.modules[package_name] = package

        spec = importlib.util.spec_from_file_location(module_name, config.extensions)
        if spec is None or spec.loader is None:
            sys.modules.pop(package_name, None)
            raise DocumentError(f"cannot load project extension module: {config.extensions}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            for name in tuple(sys.modules):
                if name == package_name or name.startswith(f"{package_name}."):
                    sys.modules.pop(name, None)
            if isinstance(error, DocumentError):
                raise
            raise DocumentError(
                f"cannot load project extension module {config.extensions}: {error}"
            ) from error
        return module
