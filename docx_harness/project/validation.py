from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from docx import Document

from ..errors import DocumentError
from ..parser import parse_document
from .config import ProjectConfig, load_project
from .runtime import ProjectRuntime, load_project_runtime

STYLE_MANIFEST_SCHEMA = "docx-harness/style-manifest/v1"


@dataclass(frozen=True, slots=True)
class ProjectValidationReport:
    root: Path
    checks: tuple[str, ...]

    def __str__(self) -> str:
        details = "\n".join(f"ok\t{check}" for check in self.checks)
        return f"validated managed Project: {self.root}\n{details}"


def _validate_git_root(config: ProjectConfig) -> None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=config.root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise DocumentError(f"cannot inspect managed project Git repository: {error}") from error
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise DocumentError(
            f"managed project is not an independent Git repository: {config.root}: {details}"
        )
    git_root = Path(completed.stdout.strip()).resolve()
    if git_root != config.root:
        raise DocumentError(
            f"managed project Git root must equal the project root: {git_root} != {config.root}"
        )


def _validate_template(config: ProjectConfig) -> None:
    try:
        Document(config.template)
    except Exception as error:
        raise DocumentError(f"cannot open project template {config.template}: {error}") from error


def _validate_style_manifest(config: ProjectConfig) -> bool:
    if config.style_manifest is None:
        return False
    try:
        manifest = json.loads(config.style_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DocumentError(
            f"cannot read project style manifest {config.style_manifest}: {error}"
        ) from error
    if not isinstance(manifest, dict) or manifest.get("schema") != STYLE_MANIFEST_SCHEMA:
        raise DocumentError(
            f"unsupported project style manifest schema: "
            f"{manifest.get('schema') if isinstance(manifest, dict) else '<non-object>'}"
        )
    return True


def _validate_source(runtime: ProjectRuntime) -> None:
    source = runtime.config.source
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise DocumentError(f"cannot read project source {source}: {error}") from error
    parse_document(
        text,
        source=str(source),
        registry=runtime.registry,
        diagram_registry=runtime.diagram_registry,
    )


def validate_project(project: str | Path) -> ProjectValidationReport:
    config = load_project(project)
    checks = ["configuration and managed paths"]
    _validate_git_root(config)
    checks.append("independent Git root")
    _validate_template(config)
    checks.append("DOCX template")
    if _validate_style_manifest(config):
        checks.append("optional style manifest")
    runtime = load_project_runtime(config)
    checks.append("Project extension runtime")
    _validate_source(runtime)
    checks.append("default Markdown/MyST source")
    return ProjectValidationReport(config.root, tuple(checks))
