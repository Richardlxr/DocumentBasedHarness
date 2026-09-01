from __future__ import annotations

from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


def set_east_asia_font(style, font_name: str) -> None:
    style.font.name = font_name
    r_pr = style._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:eastAsia"), font_name)


def set_fixed_table_layout(table) -> None:
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    current = tbl_pr.find(qn("w:tblLayout"))
    if current is not None:
        tbl_pr.remove(current)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)


def set_cell_width(cell, twips: int) -> None:
    set_table_cell_width(cell._tc, twips)


def set_table_cell_width(tc, twips: int) -> None:
    tc_pr = tc.get_or_add_tcPr()
    tc_w = tc_pr.get_or_add_tcW()
    tc_w.set(qn("w:w"), str(twips))
    tc_w.set(qn("w:type"), "dxa")
    no_wrap = tc_pr.find(qn("w:noWrap"))
    if no_wrap is not None:
        tc_pr.remove(no_wrap)


def set_table_column_widths(table, widths_twips: tuple[int, ...]) -> None:
    """Apply grid widths and merge-aware physical cell widths."""
    if not widths_twips:
        return

    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.insert(0, tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths_twips)))
    tbl_w.set(qn("w:type"), "dxa")

    grid_columns = table._tbl.tblGrid.findall(qn("w:gridCol"))
    for column_index, width in enumerate(widths_twips):
        if column_index < len(grid_columns):
            grid_columns[column_index].set(qn("w:w"), str(width))

    for tr in table._tbl.tr_lst:
        column_index = 0
        for tc in tr.tc_lst:
            tc_pr = tc.get_or_add_tcPr()
            grid_span = tc_pr.find(qn("w:gridSpan"))
            span = int(grid_span.get(qn("w:val"))) if grid_span is not None else 1
            width = sum(widths_twips[column_index : column_index + span])
            set_table_cell_width(tc, width)
            column_index += span


def set_equal_table_column_widths(table, total_width_twips: int) -> None:
    """Fill the available width with deterministic equal-width wrapping columns."""
    column_count = len(table.columns)
    if column_count == 0:
        return
    total_width_twips = max(total_width_twips, column_count)
    base_width, remainder = divmod(total_width_twips, column_count)
    widths = tuple(base_width + (1 if index < remainder else 0) for index in range(column_count))
    set_table_column_widths(table, widths)


def clear_cell(cell) -> None:
    """Remove merged-cell residue while preserving required cell properties."""
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    for child in list(tc):
        if child is not tc_pr:
            tc.remove(child)
    tc.append(OxmlElement("w:p"))


def set_cell_margins(
    cell,
    *,
    top: int = 40,
    start: int = 60,
    bottom: int = 40,
    end: int = 60,
) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    current = tc_pr.find(qn("w:shd"))
    if current is not None:
        tc_pr.remove(current)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    tc_pr.append(shading)


def set_table_borders(
    table,
    *,
    color: str = "000000",
    outer_size: int = 12,
    inner_size: int = 4,
) -> None:
    """Apply a 1.5 pt outer border and 0.5 pt inner grid by default."""
    tbl_pr = table._tbl.tblPr
    current = tbl_pr.find(qn("w:tblBorders"))
    if current is not None:
        tbl_pr.remove(current)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "start", "bottom", "end", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        size = inner_size if edge.startswith("inside") else outer_size
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:color"), color)
        borders.append(element)
    tbl_pr.append(borders)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is None:
        header = OxmlElement("w:tblHeader")
        header.set(qn("w:val"), "true")
        tr_pr.append(header)


def set_table_row_cant_split(row) -> None:
    """Keep a normal table row on one page when Word can do so."""
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        cant_split = OxmlElement("w:cantSplit")
        cant_split.set(qn("w:val"), "true")
        tr_pr.append(cant_split)


def set_table_row_auto_height(row) -> None:
    """Remove direct row-height constraints so content determines the minimum height."""
    tr_pr = row._tr.get_or_add_trPr()
    for height in tr_pr.findall(qn("w:trHeight")):
        tr_pr.remove(height)


def set_table_row_min_height(row, height_twips: int) -> None:
    """Set a calculated minimum height while still allowing Word to expand the row."""
    set_table_row_auto_height(row)
    tr_pr = row._tr.get_or_add_trPr()
    height = OxmlElement("w:trHeight")
    height.set(qn("w:val"), str(max(1, height_twips)))
    height.set(qn("w:hRule"), "atLeast")
    tr_pr.append(height)


def create_numbering_instance(document, style_name: str) -> int:
    """Create an independent numbering sequence from a paragraph style."""
    style = document.styles[style_name]
    base_num_id = None
    while style is not None:
        p_pr = style._element.pPr
        num_pr = p_pr.numPr if p_pr is not None else None
        if num_pr is not None and num_pr.numId is not None:
            base_num_id = int(num_pr.numId.val)
            break
        style = style.base_style
    if base_num_id is None:
        raise ValueError(f"paragraph style has no numbering definition: {style_name}")

    numbering = document.part.numbering_part.element
    abstract_num_id = None
    num_ids = []
    for num in numbering.findall(qn("w:num")):
        num_id = int(num.get(qn("w:numId")))
        num_ids.append(num_id)
        if num_id == base_num_id:
            abstract = num.find(qn("w:abstractNumId"))
            if abstract is not None:
                abstract_num_id = abstract.get(qn("w:val"))
    if abstract_num_id is None:
        raise ValueError(f"numbering definition does not exist for style: {style_name}")

    new_num_id = max(num_ids, default=0) + 1
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(new_num_id))
    abstract = OxmlElement("w:abstractNumId")
    abstract.set(qn("w:val"), abstract_num_id)
    num.append(abstract)
    level_override = OxmlElement("w:lvlOverride")
    level_override.set(qn("w:ilvl"), "0")
    start_override = OxmlElement("w:startOverride")
    start_override.set(qn("w:val"), "1")
    level_override.append(start_override)
    num.append(level_override)
    numbering.append(num)
    return new_num_id


def set_paragraph_numbering(paragraph, num_id: int) -> None:
    """Bind a paragraph to an explicit numbering sequence at level zero."""
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = p_pr.get_or_add_numPr()
    level = num_pr.get_or_add_ilvl()
    level.set(qn("w:val"), "0")
    number = num_pr.get_or_add_numId()
    number.set(qn("w:val"), str(num_id))


def add_hyperlink(paragraph, text: str, url: str, *, bold: bool, italic: bool) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE

    relationship_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    run_style = OxmlElement("w:rStyle")
    run_style.set(qn("w:val"), "Hyperlink")
    properties.append(run_style)
    if bold:
        properties.append(OxmlElement("w:b"))
    if italic:
        properties.append(OxmlElement("w:i"))
    run.append(properties)
    content = OxmlElement("w:t")
    content.text = text
    run.append(content)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_paragraph_bottom_border(paragraph, *, color: str = "A6B1C2", size: int = 6) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        p_pr.append(borders)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)


def ensure_style(styles, name: str, style_type: WD_STYLE_TYPE, base: str | None = None):
    if name in styles:
        return styles[name]
    style = styles.add_style(name, style_type)
    if base and base in styles:
        style.base_style = styles[base]
    return style


def configure_run_style(
    style,
    *,
    font: str,
    size: float,
    bold: bool = False,
    color: str | None = None,
) -> None:
    set_east_asia_font(style, font)
    style.font.size = Pt(size)
    style.font.bold = bold
    if color:
        from docx.shared import RGBColor

        style.font.color.rgb = RGBColor.from_string(color)
