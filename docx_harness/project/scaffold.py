from __future__ import annotations

import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

from ..errors import DocumentError
from ..presets import get_template_preset
from ..style_import import extract_template, write_style_manifest
from ..template import create_template
from .config import PROJECT_NAME

_RESOURCE_FILES = {
    "project.toml": "project.toml.txt",
    "extensions.py": "extensions.py.txt",
    ".gitignore": "gitignore.txt",
    "AGENTS.md": "AGENTS.md.txt",
    "README.md": "README.md.txt",
    "VERSIONING.md": "VERSIONING.md.txt",
    "WORKSPACE_REFERENCES.md": "WORKSPACE_REFERENCES.md.txt",
    "pytest.ini": "pytest.ini.txt",
    "references/source-revisions.toml": "source-revisions.toml.txt",
    ".workspace/CONTEXT.md": "CONTEXT.md.txt",
    ".workspace/references.toml": "workspace-references.toml.txt",
}


def init_workspace(repository: str | Path = ".") -> Path:
    projects = Path(repository).resolve() / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / ".gitkeep").touch(exist_ok=True)
    return projects


def _resource_text(name: str) -> str:
    return files("docx_harness.project").joinpath("resources", name).read_text(encoding="utf-8")


def _write_managed_scaffold(root: Path, name: str, preset: str) -> None:
    substitutions = {
        "__PROJECT_NAME__": name,
        "__PROJECT_TITLE__": name.replace("-", " ").title(),
        "__TEMPLATE_PRESET__": preset,
    }
    for relative, resource_name in _RESOURCE_FILES.items():
        content = _resource_text(resource_name)
        for marker, value in substitutions.items():
            content = content.replace(marker, value)
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _initialize_git(root: Path) -> None:
    try:
        completed = subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise DocumentError(f"cannot initialize managed project Git repository: {error}") from error
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise DocumentError(f"cannot initialize managed project Git repository: {details}")


def init_project(
    name: str,
    *,
    workspace: str | Path = "projects",
    preset: str = "standard",
    from_docx: str | Path | None = None,
) -> Path:
    if not PROJECT_NAME.fullmatch(name):
        raise DocumentError("project name must be a 3-64 character lowercase hyphenated identifier")
    if from_docx is None:
        try:
            get_template_preset(preset)
        except ValueError as error:
            raise DocumentError(str(error)) from error

    root = Path(workspace).resolve() / name
    if root.exists() and any(root.iterdir()):
        raise DocumentError(f"project directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    try:
        for directory in (
            "documents",
            "templates",
            "components",
            "references",
            "build",
            "tests",
            ".workspace",
        ):
            (root / directory).mkdir(parents=True, exist_ok=True)

        template_preset = "imported" if from_docx is not None else preset
        _write_managed_scaffold(root, name, template_preset)
        example_name = (
            "example-cn-official.md.txt" if preset == "cn-official" else "example-standard.md.txt"
        )
        example = _resource_text(example_name).replace(
            "__PROJECT_TITLE__", name.replace("-", " ").title()
        )
        (root / "documents" / "example.md").write_text(example, encoding="utf-8")
        (root / "tests" / ".gitkeep").touch()

        template = root / "templates" / "base.docx"
        manifest = root / "style-manifest.json"
        if from_docx is None:
            create_template(template, preset=preset)
            write_style_manifest(template, manifest)
        else:
            style_source = Path(from_docx).resolve()
            if not style_source.exists():
                raise DocumentError(f"DOCX style source does not exist: {style_source}")
            retained_source = root / "references" / "style-source.docx"
            shutil.copy2(style_source, retained_source)
            extract_template(
                retained_source,
                template,
                manifest=manifest,
                components=root / "components",
            )
        _initialize_git(root)
    except Exception:
        shutil.rmtree(root)
        raise
    return root
