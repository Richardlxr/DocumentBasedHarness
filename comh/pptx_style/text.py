"""Conservative native-text compatibility diagnostics; not a presentation player."""

from __future__ import annotations

import math

from ..render.metrics import font_resolution, text_width
from .package import NS, StyleError, q, shape_id
from .typography import effective_text_style


def assess_text(package, slide: int, scope: str, node) -> dict | None:
    body = node.find("p:txBody", NS)
    if body is None or not body.findall(".//a:t", NS):
        return None
    properties = body.find("a:bodyPr", NS)
    attrs = properties.attrib if properties is not None else {}
    style = effective_text_style(package, slide, scope, shape_id(node))
    paragraphs = ["".join(p.xpath(".//a:t/text()", namespaces=NS)) for p in body.findall("a:p", NS)]
    family = style.get("cjk" if any(ord(c) > 255 for p in paragraphs for c in p) else "latin")
    family = family or "Microsoft YaHei"
    bold, italic = bool(style["bold"]), bool(style["italic"])
    resolution = font_resolution(family, bold=bold, italic=italic)
    size = style.get("size_pt")
    extent = node.find("p:spPr/a:xfrm/a:ext", NS)
    insets = {
        k: int(attrs.get(k, default)) / 12700
        for k, default in (("lIns", 91440), ("rIns", 91440), ("tIns", 45720), ("bIns", 45720))
    }
    box = {k: int(extent.get(k)) / 12700 for k in ("cx", "cy")} if extent is not None else None
    available = max(0, box["cx"] - insets["lIns"] - insets["rIns"]) if box else None
    estimated = (
        max(
            (text_width(p, math.ceil(size), family, bold=bold, italic=italic) for p in paragraphs),
            default=0,
        )
        if size
        else None
    )
    fit = (
        next(
            (
                n.tag.rsplit("}", 1)[-1]
                for n in properties
                if n.tag in {q("a:noAutofit"), q("a:normAutofit"), q("a:spAutoFit")}
            ),
            "noAutofit",
        )
        if properties is not None
        else "noAutofit"
    )
    codes = []
    if resolution["substitution"]:
        codes.append("measurement_font_substitution")
    if estimated is not None and available is not None and estimated > available:
        codes.append("width_pressure")
    if fit != "noAutofit":
        codes.append("viewer_autofit")
    if extent is None or size is None:
        codes.append("unmeasured_geometry_or_size")
    if len(body.findall("a:p", NS)) != 1 or body.findall(".//a:br", NS):
        codes.append("multiline_content")
    transform = node.find("p:spPr/a:xfrm", NS)
    if (
        len(body.findall("a:p/a:r", NS)) != 1
        or attrs.get("vert", "horz") != "horz"
        or int(attrs.get("numCol", "1")) != 1
        or (transform is not None and int(transform.get("rot", "0")))
    ):
        codes.append("complex_text")
    return {
        "text": "\n".join(paragraphs),
        "wrap": attrs.get("wrap", "square"),
        "auto_fit": fit,
        "box_pt": box,
        "insets_pt": insets,
        "available_width_pt": available,
        "estimated_width_pt": estimated,
        "font": resolution,
        "font_size_pt": size,
        "risks": codes,
        "measurement_scope": (
            "First-run measurement with margin; mixed formatting, "
            "shaping and player fonts unverified."
        ),
    }


def preserve_single_line(node, assessment: dict, *, location: str) -> None:
    """Only explicitly selected, simple horizontal brand labels; never shrink typography."""
    if (
        any(
            code in assessment["risks"]
            for code in ("multiline_content", "complex_text", "unmeasured_geometry_or_size")
        )
        or "\n" in assessment["text"]
        or "\r" in assessment["text"]
    ):
        raise StyleError(
            f"{location}: single_line requires one text paragraph and a simple measured run"
        )
    body = node.find("p:txBody", NS)
    properties = body.find("a:bodyPr", NS)
    if properties is None:
        raise StyleError(f"{location}: single_line needs explicit body properties")
    # No-wrap and shape-auto-fit alone are not honored consistently by all importers.
    # Materialize sufficient width as well; retain the original origin and font size.
    extent = node.find("p:spPr/a:xfrm/a:ext", NS)
    needed = assessment["estimated_width_pt"] + sum(
        assessment["insets_pt"][k] for k in ("lIns", "rIns")
    )
    alignment = next(
        (
            p.get("algn")
            for path in ("a:p/a:pPr", "a:lstStyle/a:lvl1pPr")
            if (p := body.find(path, NS)) is not None and p.get("algn")
        ),
        "l",
    )
    if alignment != "l" and needed * 12700 > int(extent.get("cx")):
        raise StyleError(f"{location}: single_line expansion needs a left-aligned brand label")
    extent.set("cx", str(max(int(extent.get("cx")), math.ceil(needed * 12700))))
    properties.set("wrap", "none")
    for child in list(properties):
        if child.tag in {q("a:noAutofit"), q("a:normAutofit"), q("a:spAutoFit")}:
            properties.remove(child)
    from lxml import etree as ET

    properties.append(ET.Element(q("a:noAutofit")))
