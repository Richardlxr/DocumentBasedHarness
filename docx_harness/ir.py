from __future__ import annotations

from dataclasses import dataclass

from .errors import SourceLocation


@dataclass(frozen=True, slots=True)
class TextSpan:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    href: str | None = None


@dataclass(frozen=True, slots=True)
class InlineImage:
    uri: str
    alt: str = ""


@dataclass(frozen=True, slots=True)
class LineBreak:
    pass


@dataclass(frozen=True, slots=True)
class InlineMath:
    tex: str
    location: SourceLocation | None = None


Inline = TextSpan | InlineImage | LineBreak | InlineMath


@dataclass(frozen=True, slots=True)
class Paragraph:
    inlines: tuple[Inline, ...]
    location: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    inlines: tuple[Inline, ...]
    location: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class CodeBlock:
    text: str
    language: str | None = None
    location: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class DiagramBlock:
    source_kind: str
    content: str
    location: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class MathBlock:
    tex: str
    location: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class BlockQuote:
    blocks: tuple[Block, ...]
    location: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class ListBlock:
    items: tuple[tuple[Block, ...], ...]
    ordered: bool = False
    location: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class TableCell:
    blocks: tuple[Block, ...]
    column: int = 0
    column_span: int = 1
    row_span: int = 1


@dataclass(frozen=True, slots=True)
class TableRow:
    cells: tuple[TableCell, ...]


@dataclass(frozen=True, slots=True)
class TableBlock:
    header: TableRow | None
    rows: tuple[TableRow, ...]
    location: SourceLocation | None = None


@dataclass(frozen=True, slots=True)
class HorizontalRule:
    location: SourceLocation | None = None


Block = (
    Paragraph
    | Heading
    | CodeBlock
    | DiagramBlock
    | MathBlock
    | BlockQuote
    | ListBlock
    | TableBlock
    | HorizontalRule
)


@dataclass(frozen=True, slots=True)
class DocumentIR:
    blocks: tuple[object, ...]
    source: str
