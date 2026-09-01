from __future__ import annotations

from pathlib import Path

from ..compiler import compile_file
from ..diagrams.artifacts import DiagramExportProfile
from ..diagrams.model import DiagramConverterRegistry
from ..errors import DocumentError
from ..table_format import TableFormatProfile
from .config import ProjectConfig
from .runtime import load_project_runtime


def managed_source(config: ProjectConfig, source: str | Path | None) -> Path:
    candidate = config.source if source is None else Path(source)
    if not candidate.is_absolute():
        direct = (config.root / candidate).resolve()
        candidate = direct if direct.exists() else (config.documents / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not candidate.is_relative_to(config.documents):
        raise DocumentError(
            f"managed project source must be inside {config.documents}: {candidate}"
        )
    if not candidate.is_file():
        raise DocumentError(f"project source document does not exist: {candidate}")
    return candidate


def managed_output(config: ProjectConfig, source: Path, output: str | Path | None) -> Path:
    if output is None:
        destination = (
            config.output if source == config.source else config.build / f"{source.stem}.docx"
        )
    else:
        destination = Path(output)
        if not destination.is_absolute():
            destination = config.root / destination
        destination = destination.resolve()
    if not destination.is_relative_to(config.build):
        raise DocumentError(f"managed project output must be inside {config.build}: {destination}")
    return destination


def render_project(
    project: str | Path,
    source: str | Path | None = None,
    *,
    output: str | Path | None = None,
    table_profile: TableFormatProfile | None = None,
    diagram_profile: DiagramExportProfile | None = None,
    diagram_registry: DiagramConverterRegistry | None = None,
) -> Path:
    runtime = load_project_runtime(project)
    source_path = managed_source(runtime.config, source)
    destination = managed_output(runtime.config, source_path, output)
    return compile_file(
        source_path,
        destination,
        template=runtime.config.template,
        registry=runtime.registry,
        table_profile=table_profile or runtime.table_profile,
        diagram_profile=diagram_profile,
        diagram_registry=diagram_registry or runtime.diagram_registry,
        hooks=runtime.hooks,
        project_root=runtime.config.root,
    )
