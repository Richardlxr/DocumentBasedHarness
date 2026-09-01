from __future__ import annotations

from dataclasses import dataclass

from docutils import nodes
from docutils.parsers.rst import Directive
from docx.enum.text import WD_BREAK
from docx.table import _Cell

from ..errors import DocumentError, SourceLocation
from ..extension import DirectiveExtension


class DocumentBodyStartNode(nodes.General, nodes.Element):
    pass


class DocumentBodyStartDirective(Directive):
    has_content = False

    def run(self):
        node = DocumentBodyStartNode()
        node.line = self.lineno
        return [node]


@dataclass(frozen=True, slots=True)
class DocumentBodyStartBlock:
    location: SourceLocation


def transform_document_body_start(node, transformer, heading_level):
    del heading_level
    return DocumentBodyStartBlock(location=transformer.location(node))


def render_document_body_start(block, renderer, container) -> None:
    del renderer
    if isinstance(container, _Cell):
        raise DocumentError("document body cannot start inside a table cell", block.location)
    paragraph = container.add_paragraph()
    paragraph.add_run().add_break(WD_BREAK.PAGE)


DOCUMENT_BODY_START_EXTENSION = DirectiveExtension(
    name="document-body-start",
    directive=DocumentBodyStartDirective,
    node_type=DocumentBodyStartNode,
    ir_type=DocumentBodyStartBlock,
    transform=transform_document_body_start,
    render=render_document_body_start,
)
