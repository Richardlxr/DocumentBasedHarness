"""OOXML helpers for python-pptx.

Small, isolated, tested helpers for drawingML XML operations not exposed
directly by python-pptx (e.g. solid fill alpha channel).
"""

from __future__ import annotations

from lxml import etree
from pptx.dml.color import RGBColor
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn


def set_connector_arrow(shape, *, at_start: bool = False) -> None:
    """Arrow at the endpoint of an editable native connector."""
    line = shape.line._get_or_add_ln()
    tag = "a:headEnd" if at_start else "a:tailEnd"
    tail = line.find(qn(tag))
    if tail is None:
        tail = etree.SubElement(line, qn(tag))
    tail.set("type", "triangle")


def set_east_asian_font(run, family: str) -> None:
    """Pin CJK face as well as Latin face; template theme inheritance must not override it."""
    properties = run._r.get_or_add_rPr()
    node = properties.find(qn("a:ea"))
    if node is None:
        node = etree.Element(qn("a:ea"))
        # CT_TextCharacterProperties: latin, ea, cs, sym, hyperlink, extension.
        after = properties.find(qn("a:latin"))
        if after is not None:
            properties.insert(list(properties).index(after) + 1, node)
        else:
            properties.append(node)
    node.set("typeface", family)


def set_shape_translucent_fill(shape, color: RGBColor, alpha: float) -> None:
    """Set solid fill color with an alpha transparency in [0.0, 1.0].

    In python-pptx, shape.fill.solid() sets RGB but has no public API for alpha.
    This injects <a:alpha val="..."/> (0..100000) inside <a:srgbClr>.
    """
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    spPr = shape._element.spPr
    solidFill = spPr.find(qn("a:solidFill"))
    if solidFill is not None:
        srgbClr = solidFill.find(qn("a:srgbClr"))
        if srgbClr is not None:
            # Remove any existing alpha child to prevent duplicates
            for child in list(srgbClr):
                if child.tag == qn("a:alpha"):
                    srgbClr.remove(child)
            alpha_val = max(0, min(100000, int(round(alpha * 100000))))
            alpha_elem = parse_xml(
                '<a:alpha xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                f'val="{alpha_val}"/>'
            )
            srgbClr.append(alpha_elem)


_CELL_BORDERS = ("lnL", "lnR", "lnT", "lnB")


def set_cell_borders(cell, **sides) -> None:
    """Explicit table-cell borders, overriding the table style's grid.

    ``sides`` maps left/right/top/bottom to ``(RGBColor, width_pt)`` or None
    (no line). Sides left out are also drawn as no line, so a cell never
    inherits the default style's white inner grid. Borders precede the cell
    fill in CT_TableCellProperties, so they are inserted first.
    """
    tc_pr = cell._tc.get_or_add_tcPr()
    for child in list(tc_pr):
        if child.tag in {qn(f"a:{tag}") for tag in _CELL_BORDERS}:
            tc_pr.remove(child)
    ns = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    sides_in_order = ("left", "right", "top", "bottom")
    for index, (tag, side) in enumerate(zip(_CELL_BORDERS, sides_in_order, strict=True)):
        spec = sides.get(side)
        if spec is None:
            xml = f'<a:{tag} {ns} w="0"><a:noFill/></a:{tag}>'
        else:
            color, width = spec
            xml = (
                f'<a:{tag} {ns} w="{int(width * 12700)}" cap="flat" cmpd="sng">'
                f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:{tag}>'
            )
        tc_pr.insert(index, parse_xml(xml))
