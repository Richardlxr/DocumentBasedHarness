from __future__ import annotations

import io

from docutils import nodes
from docutils.core import publish_doctree
from myst_parser.parsers.docutils_ import Parser

from .diagrams.model import DiagramConverterRegistry, default_diagram_registry
from .errors import DocumentError, SourceLocation
from .extension import ExtensionRegistry, default_registry
from .ir import DocumentIR
from .transform import DocumentTransformer


def parse_document(
    text: str,
    *,
    source: str = "<string>",
    registry: ExtensionRegistry | None = None,
    diagram_registry: DiagramConverterRegistry | None = None,
) -> DocumentIR:
    active_registry = registry or default_registry()
    active_diagram_registry = diagram_registry or default_diagram_registry()
    warning_stream = io.StringIO()

    with active_registry.activated_directives():
        doctree = publish_doctree(
            source=text,
            source_path=source,
            parser=Parser(),
            settings_overrides={
                "myst_enable_extensions": ["colon_fence", "dollarmath"],
                "myst_all_links_external": True,
                "report_level": 2,
                "halt_level": 5,
                "warning_stream": warning_stream,
                "file_insertion_enabled": False,
                "raw_enabled": False,
            },
        )

    messages = list(doctree.findall(nodes.system_message))
    if messages:
        message = messages[0]
        line = message.get("line") or getattr(message, "line", None)
        details = "\n".join(line for line in message.astext().splitlines() if line.strip())
        raise DocumentError(details, SourceLocation(source, line))

    return DocumentTransformer(
        source=source,
        registry=active_registry,
        diagram_registry=active_diagram_registry,
    ).transform(doctree)
