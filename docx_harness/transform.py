from __future__ import annotations

from docutils import nodes

from .diagrams.model import DiagramConverterRegistry
from .errors import DocumentError, SourceLocation
from .extension import ExtensionRegistry
from .ir import (
    BlockQuote,
    CodeBlock,
    DiagramBlock,
    DocumentIR,
    Heading,
    HorizontalRule,
    Inline,
    InlineImage,
    InlineMath,
    LineBreak,
    ListBlock,
    MathBlock,
    Paragraph,
    TableBlock,
    TableCell,
    TableRow,
    TextSpan,
)
from .math_conversion import validate_tex


class DocumentTransformer:
    def __init__(
        self,
        *,
        source: str,
        registry: ExtensionRegistry,
        diagram_registry: DiagramConverterRegistry,
    ) -> None:
        self.source = source
        self.registry = registry
        self.diagram_registry = diagram_registry

    def transform(self, document: nodes.document) -> DocumentIR:
        # Docutils promotes a leading Markdown H1 to a document-level title,
        # while following H2/H3 headings become nested sections. Preserve that
        # absolute level shift instead of treating the first section as H1 too.
        has_document_title = any(isinstance(child, nodes.title) for child in document.children)
        has_document_subtitle = any(
            isinstance(child, nodes.subtitle) for child in document.children
        )
        blocks: list[object] = []
        for child in document.children:
            if isinstance(child, nodes.title):
                heading_level = 1
            elif isinstance(child, nodes.subtitle):
                heading_level = 2
            else:
                heading_level = 1 + int(has_document_title) + int(has_document_subtitle)
            blocks.extend(self.transform_block(child, heading_level))
        return DocumentIR(tuple(blocks), self.source)

    def transform_children(self, node: nodes.Node, heading_level: int) -> list[object]:
        blocks: list[object] = []
        for child in node.children:
            blocks.extend(self.transform_block(child, heading_level))
        return blocks

    def transform_block(self, node: nodes.Node, heading_level: int) -> list[object]:
        extension_block = self.registry.transform_node(node, self, heading_level)
        if extension_block is not None:
            return [extension_block]

        if isinstance(node, nodes.section):
            blocks: list[object] = []
            title = next((child for child in node.children if isinstance(child, nodes.title)), None)
            if title is not None:
                blocks.append(
                    Heading(
                        level=min(heading_level, 6),
                        inlines=self.transform_inlines(title),
                        location=self.location(title),
                    )
                )
            for child in node.children:
                if child is not title:
                    blocks.extend(self.transform_block(child, heading_level + 1))
            return blocks

        # MyST/Docutils promotes a single top-level heading to a document
        # title. Headings nested inside directives are represented as rubrics.
        if isinstance(node, (nodes.title, nodes.subtitle, nodes.rubric)):
            return [
                Heading(
                    level=min(heading_level, 6),
                    inlines=self.transform_inlines(node),
                    location=self.location(node),
                )
            ]

        if isinstance(node, nodes.paragraph):
            return [Paragraph(self.transform_inlines(node), self.location(node))]

        if isinstance(node, nodes.math_block):
            location = self.location(node)
            if node.get("ids") or node.get("names") or node.get("number") is not None:
                raise DocumentError(
                    "equation labels and numbering are not supported yet",
                    location,
                )
            validate_tex(node.astext(), display=True, location=location)
            return [MathBlock(node.astext(), location)]

        if isinstance(node, nodes.literal_block):
            language = node.get("language")
            classes = node.get("classes", [])
            if not language and classes:
                language = next(
                    (class_name for class_name in classes if class_name != "code"), classes[0]
                )
            if language and (
                self.diagram_registry.supports(language) or language.lower() == "drawio-file"
            ):
                return [DiagramBlock(language.lower(), node.astext(), self.location(node))]
            return [CodeBlock(node.astext(), language, self.location(node))]

        if isinstance(node, nodes.block_quote):
            return [
                BlockQuote(
                    tuple(self.transform_children(node, heading_level)),
                    self.location(node),
                )
            ]

        if isinstance(node, (nodes.bullet_list, nodes.enumerated_list)):
            items = []
            for item in node.children:
                if not isinstance(item, nodes.list_item):
                    self.unsupported(item)
                items.append(tuple(self.transform_children(item, heading_level)))
            return [
                ListBlock(
                    items=tuple(items),
                    ordered=isinstance(node, nodes.enumerated_list),
                    location=self.location(node),
                )
            ]

        if isinstance(node, nodes.table):
            return [self.transform_table(node, heading_level)]

        if isinstance(node, nodes.transition):
            return [HorizontalRule(self.location(node))]

        if isinstance(node, (nodes.comment, nodes.target, nodes.substitution_definition)):
            return []

        self.unsupported(node)

    def transform_table(self, node: nodes.table, heading_level: int) -> TableBlock:
        header: TableRow | None = None
        rows: list[TableRow] = []
        occupied: set[tuple[int, int]] = set()
        for row_index, row in enumerate(node.findall(nodes.row)):
            cells: list[TableCell] = []
            column = 0
            for entry in row.children:
                if not isinstance(entry, nodes.entry):
                    continue
                while (row_index, column) in occupied:
                    column += 1
                column_span = int(entry.get("morecols", 0)) + 1
                row_span = int(entry.get("morerows", 0)) + 1
                for occupied_row in range(row_index, row_index + row_span):
                    for occupied_column in range(column, column + column_span):
                        position = (occupied_row, occupied_column)
                        if position in occupied:
                            raise DocumentError(
                                "Markdown table contains overlapping spans",
                                self.location(entry),
                            )
                        occupied.add(position)
                cells.append(
                    TableCell(
                        tuple(self.transform_children(entry, heading_level)),
                        column=column,
                        column_span=column_span,
                        row_span=row_span,
                    )
                )
                column += column_span
            transformed = TableRow(tuple(cells))
            if isinstance(row.parent, nodes.thead) and header is None:
                header = transformed
            else:
                rows.append(transformed)
        return TableBlock(header=header, rows=tuple(rows), location=self.location(node))

    def transform_inlines(
        self,
        node: nodes.Node,
        *,
        bold: bool = False,
        italic: bool = False,
        code: bool = False,
        href: str | None = None,
    ) -> tuple[Inline, ...]:
        output: list[Inline] = []
        for child in node.children:
            if isinstance(child, nodes.Text):
                output.append(TextSpan(str(child), bold, italic, code, href))
            elif isinstance(child, nodes.strong):
                output.extend(
                    self.transform_inlines(child, bold=True, italic=italic, code=code, href=href)
                )
            elif isinstance(child, nodes.emphasis):
                output.extend(
                    self.transform_inlines(child, bold=bold, italic=True, code=code, href=href)
                )
            elif isinstance(child, nodes.literal):
                output.extend(
                    self.transform_inlines(child, bold=bold, italic=italic, code=True, href=href)
                )
            elif isinstance(child, nodes.reference):
                href = child.get("refuri")
                if href is None and child.get("refid"):
                    href = f"#{child.get('refid')}"
                output.extend(
                    self.transform_inlines(
                        child,
                        bold=bold,
                        italic=italic,
                        code=code,
                        href=href,
                    )
                )
            elif isinstance(child, nodes.image):
                output.append(InlineImage(child.get("uri", ""), child.get("alt", "")))
            elif isinstance(child, nodes.math):
                location = self.location(child)
                validate_tex(child.astext(), display=False, location=location)
                output.append(InlineMath(child.astext(), location))
            elif isinstance(child, nodes.inline):
                output.extend(
                    self.transform_inlines(child, bold=bold, italic=italic, code=code, href=href)
                )
            elif child.__class__.__name__ == "line_break":
                output.append(LineBreak())
            else:
                self.unsupported(child)
        return tuple(output)

    def location(self, node: nodes.Node) -> SourceLocation:
        return SourceLocation(self.source, getattr(node, "line", None))

    def unsupported(self, node: nodes.Node) -> None:
        raise DocumentError(
            f"unsupported Markdown/MyST node: {node.__class__.__name__}",
            self.location(node),
        )
