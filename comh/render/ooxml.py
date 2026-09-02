"""OOXML helpers for python-pptx.

Small, isolated, tested helpers for drawingML XML operations not exposed
directly by python-pptx (e.g. solid fill alpha channel).
"""

from __future__ import annotations

from pptx.dml.color import RGBColor
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn


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
