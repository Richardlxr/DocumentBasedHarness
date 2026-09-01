import pytest
from docutils import nodes
from docutils.parsers.rst import Directive

from docx_harness.diagrams.model import default_diagram_registry
from docx_harness.directives.document_body import DocumentBodyStartBlock
from docx_harness.directives.document_cover import DocumentCoverBlock
from docx_harness.directives.test_case import TestCaseBlock as CaseBlock
from docx_harness.errors import DocumentError
from docx_harness.extension import DirectiveExtension, ExtensionRegistry, default_registry
from docx_harness.ir import Heading, InlineMath, MathBlock, Paragraph, TableBlock
from docx_harness.parser import parse_document
from docx_harness.transform import DocumentTransformer

SOURCE = """\
# Report

An ordinary **paragraph**.

| A | B |
| - | - |
| 1 | 2 |

:::{test-case} Successful login
:id: TC-AUTH-001
:priority: P0

The user enters valid credentials.

### Expected result

The user reaches the home page.
:::
"""


def test_parses_standard_markdown_and_semantic_directive() -> None:
    document = parse_document(SOURCE, source="report.md")

    assert isinstance(document.blocks[0], Heading)
    assert isinstance(document.blocks[1], Paragraph)
    assert isinstance(document.blocks[2], TableBlock)
    test_case = next(block for block in document.blocks if isinstance(block, CaseBlock))
    assert test_case.meta.id == "TC-AUTH-001"
    assert test_case.meta.priority == "P0"
    assert isinstance(test_case.blocks[0], Paragraph)
    assert any(isinstance(block, Heading) for block in test_case.blocks)
    assert test_case.sections[-1].title[0].text == "Expected result"


def test_reports_invalid_directive_options_with_source() -> None:
    source = """\
:::{test-case} Invalid
:id: lowercase
:priority: critical
:::
"""

    with pytest.raises(DocumentError) as caught:
        parse_document(source, source="invalid.md")

    assert "invalid.md" in str(caught.value)
    assert "test-case" in str(caught.value).lower() or "validation" in str(caught.value).lower()


def test_preserves_heading_levels_after_promoted_document_title() -> None:
    document = parse_document(
        "# Document title\n\n## First level\n\n### Second level\n",
        source="headings.md",
    )

    headings = [block for block in document.blocks if isinstance(block, Heading)]
    assert [heading.level for heading in headings] == [1, 2, 3]


def test_parses_document_body_start_with_source_location() -> None:
    document = parse_document(
        "# Cover\n\n2026年8月\n\n:::{document-body-start}\n:::\n\n## Content\n",
        source="paged.md",
    )

    body_start = next(
        block for block in document.blocks if isinstance(block, DocumentBodyStartBlock)
    )
    assert body_start.location.source == "paged.md"
    assert body_start.location.line == 5


def test_parses_document_cover_date_with_source_location() -> None:
    document = parse_document(
        "# Cover\n\n:::{document-cover}\n:date: 2026年8月\n:::\n\n## Content\n",
        source="covered.md",
    )

    cover = next(block for block in document.blocks if isinstance(block, DocumentCoverBlock))
    assert cover.date == "2026年8月"
    assert cover.location.source == "covered.md"
    assert cover.location.line == 3


def test_rejects_document_cover_without_date() -> None:
    with pytest.raises(DocumentError, match="date"):
        parse_document(
            "# Cover\n\n:::{document-cover}\n:::\n",
            source="cover-without-date.md",
        )


def test_parses_and_validates_inline_and_display_tex_math() -> None:
    document = parse_document(
        "样本为 $x_i$。\n\n$$\n\\bar{x}=\\frac{1}{n}\\sum_{i=1}^{n}x_i\n$$\n",
        source="formula.md",
    )

    paragraph = document.blocks[0]
    assert isinstance(paragraph, Paragraph)
    inline = next(item for item in paragraph.inlines if isinstance(item, InlineMath))
    assert inline.tex == "x_i"
    assert inline.location.line == 1

    display = document.blocks[1]
    assert isinstance(display, MathBlock)
    assert display.tex.strip() == r"\bar{x}=\frac{1}{n}\sum_{i=1}^{n}x_i"
    assert display.location.line == 3


def test_rejects_unsupported_tex_with_source_location() -> None:
    with pytest.raises(DocumentError) as caught:
        parse_document("首行。\n\n$$\\unknown{x}$$\n", source="invalid-formula.md")

    assert "invalid-formula.md:3" in str(caught.value)
    assert r"\unknown" in str(caught.value)


def test_rejects_equation_labels_instead_of_silently_dropping_them() -> None:
    with pytest.raises(DocumentError, match="labels and numbering"):
        parse_document("$$x^2$$ (eq-square)\n", source="labelled-formula.md")


def test_partitions_test_case_fields_without_hard_coding_their_labels() -> None:
    document = parse_document(
        """\
:::{test-case} Partitioned
:id: TC-PART-001

Introductory evidence.

**Purpose:** Verify arbitrary semantic fields.

**Execution notes:**

1. First note.
2. Second note.
:::
""",
        source="partitioned.md",
    )
    test_case = next(block for block in document.blocks if isinstance(block, CaseBlock))

    assert len(test_case.preamble) == 1
    assert [section.title[0].text for section in test_case.sections] == [
        "Purpose",
        "Execution notes",
    ]
    assert isinstance(test_case.sections[0].blocks[0], Paragraph)
    assert test_case.sections[0].blocks[0].inlines[0].text == "Verify arbitrary semantic fields."


class _TemporaryNode(nodes.General, nodes.Element):
    pass


class _TemporaryDirective(Directive):
    has_content = False

    def run(self):
        return [_TemporaryNode()]


def test_custom_directive_registration_does_not_leak_between_compiles() -> None:
    registry = ExtensionRegistry()
    registry.add(
        DirectiveExtension(
            name="temporary-project-directive",
            directive=_TemporaryDirective,
            node_type=_TemporaryNode,
            ir_type=str,
            transform=lambda node, transformer, level: "temporary",
            render=lambda block, renderer, container: None,
        )
    )
    source = ":::{temporary-project-directive}\n:::"

    assert parse_document(source, registry=registry).blocks == ("temporary",)
    with pytest.raises(DocumentError, match="Unknown directive type"):
        parse_document(source)


def test_preserves_docutils_table_spans_in_ir() -> None:
    table = nodes.table()
    group = nodes.tgroup(cols=2)
    table += group
    head = nodes.thead()
    group += head
    heading_row = nodes.row()
    head += heading_row
    heading = nodes.entry(morecols=1)
    heading += nodes.paragraph(text="Heading")
    heading_row += heading
    body = nodes.tbody()
    group += body
    body_row = nodes.row()
    body += body_row
    for value in ("A", "B"):
        entry = nodes.entry()
        entry += nodes.paragraph(text=value)
        body_row += entry

    transformer = DocumentTransformer(
        source="spans.md",
        registry=default_registry(),
        diagram_registry=default_diagram_registry(),
    )
    block = transformer.transform_table(table, 1)

    assert block.header.cells[0].column == 0
    assert block.header.cells[0].column_span == 2
    assert [cell.column for cell in block.rows[0].cells] == [0, 1]
