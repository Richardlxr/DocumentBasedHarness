from __future__ import annotations

from pathlib import Path

from .diagrams.artifacts import DiagramExportProfile
from .diagrams.model import DiagramConverterRegistry, default_diagram_registry
from .extension import ExtensionRegistry, default_registry
from .lifecycle import RenderHooks
from .parser import parse_document
from .renderers.docx import DocxRenderer
from .table_format import TableFormatProfile


def compile_text(
    text: str,
    output: str | Path,
    *,
    source: str = "<string>",
    template: str | Path | None = None,
    registry: ExtensionRegistry | None = None,
    table_profile: TableFormatProfile | None = None,
    diagram_profile: DiagramExportProfile | None = None,
    diagram_registry: DiagramConverterRegistry | None = None,
    hooks: RenderHooks | None = None,
    project_root: str | Path | None = None,
) -> Path:
    active_registry = registry or default_registry()
    active_diagram_registry = diagram_registry or default_diagram_registry()
    document_ir = parse_document(
        text,
        source=source,
        registry=active_registry,
        diagram_registry=active_diagram_registry,
    )
    source_dir = Path(source).resolve().parent if source != "<string>" else Path.cwd()
    renderer = DocxRenderer(
        registry=active_registry,
        template=template,
        source_dir=source_dir,
        table_profile=table_profile,
        diagram_profile=diagram_profile,
        diagram_registry=active_diagram_registry,
        hooks=hooks,
        source=source,
        project_root=project_root,
    )
    return renderer.render(document_ir, output)


def compile_file(
    source: str | Path,
    output: str | Path,
    *,
    template: str | Path | None = None,
    registry: ExtensionRegistry | None = None,
    table_profile: TableFormatProfile | None = None,
    diagram_profile: DiagramExportProfile | None = None,
    diagram_registry: DiagramConverterRegistry | None = None,
    hooks: RenderHooks | None = None,
    project_root: str | Path | None = None,
) -> Path:
    source_path = Path(source)
    return compile_text(
        source_path.read_text(encoding="utf-8"),
        output,
        source=str(source_path),
        template=template,
        registry=registry,
        table_profile=table_profile,
        diagram_profile=diagram_profile,
        diagram_registry=diagram_registry,
        hooks=hooks,
        project_root=project_root,
    )
