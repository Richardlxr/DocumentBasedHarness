"""Read-only inventory in presentation order. Geometry is evidence, not a layout prescription."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .package import NS, Package, q, shape_id, shapes


def _shape_record(node) -> dict:
    identity = node.find(".//p:cNvPr", NS)
    text = "\n".join(node.xpath(".//a:t/text()", namespaces=NS))
    runs = node.findall(".//a:rPr", NS) + node.findall(".//a:defRPr", NS)
    fonts = sorted(
        {
            n.get("typeface")
            for n in node.findall(".//a:latin", NS) + node.findall(".//a:ea", NS)
            if n.get("typeface")
        }
    )
    xfrm = node.find(".//a:xfrm", NS)
    ph = node.find(".//p:ph", NS)
    return {
        "id": shape_id(node),
        "name": identity.get("name", ""),
        "kind": node.tag.rsplit("}", 1)[-1],
        "text": text,
        "placeholder": dict(ph.attrib) if ph is not None else None,
        "fonts": fonts,
        "sizes_pt": sorted({int(r.get("sz")) / 100 for r in runs if r.get("sz")}),
        "geometry": (
            {c.tag.rsplit("}", 1)[-1]: dict(c.attrib) for c in xfrm} if xfrm is not None else None
        ),
        "has_chart_or_ole": bool(node.findall(".//a:graphic", NS)),
        "has_actions": bool(node.findall(".//a:hlinkClick", NS)),
        "children": (
            [_shape_record(n) for n in node if n.tag not in {q("p:nvGrpSpPr"), q("p:grpSpPr")}]
            if node.tag == q("p:grpSp")
            else []
        ),
    }


def inventory_slide(package: Package, number: int) -> dict:
    from .text import assess_text
    from .typography import effective_text_style

    scopes = package.scopes(number)
    layers = {}
    for scope, part in scopes.items():
        tree = package.tree(part)
        c_sld = tree.find("p:cSld", NS)
        layers[scope] = {
            "part": part,
            "name": c_sld.get("name", "") if c_sld is not None else "",
            "background": tree.find("p:cSld/p:bg", NS) is not None,
            "shapes": [_shape_record(s) for s in shapes(tree)],
        }
        from .package import descendants

        nodes = {shape_id(n): n for n in descendants(shapes(tree))}

        def add_typography(records, scope=scope, nodes=nodes):
            for record in records:
                if record["text"] or record["placeholder"] is not None:
                    record["text_style"] = effective_text_style(
                        package, number, scope, record["id"]
                    )
                    record["text_layout"] = assess_text(package, number, scope, nodes[record["id"]])
                add_typography(record["children"])

        add_typography(layers[scope]["shapes"])
    return {"slide": number, "layers": layers}


def inspect_pptx(source: Path, *, slide: int | None = None) -> dict:
    package = Package(source)
    size = package.tree("ppt/presentation.xml").find("p:sldSz", NS)
    count = len(package.slides())
    numbers = [slide] if slide is not None else range(1, count + 1)
    return {
        "schema": "comh/pptx-style-inventory/v1",
        "source": source.name,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "slide_count": count,
        "canvas_emu": {k: int(size.get(k)) for k in ("cx", "cy")},
        "slides": [inventory_slide(package, i) for i in numbers],
        "boundary": "Appearance only. Source page density and content structure are not imported.",
    }


def theme_tokens(package: Package) -> dict:
    """Extract a proposed palette/font seed. No guesses about slide content or shape roles."""
    master = package.scopes(1)["master"]
    theme = package.tree(package.related(master, "theme"))
    colors = {}
    for entry in theme.findall("a:themeElements/a:clrScheme/*", NS):
        color = next(iter(entry), None)
        if color is not None:
            colors[entry.tag.rsplit("}", 1)[-1]] = color.get("lastClr", color.get("val"))
    fonts = {}
    for key, script in (("latin", "latin"), ("cjk", "ea")):
        values = []
        for group in ("majorFont", "minorFont"):
            node = theme.find(f"a:themeElements/a:fontScheme/a:{group}", NS)
            font = node.find(f"a:{script}", NS) if node is not None else None
            face = font.get("typeface") if font is not None else None
            if not face and key == "cjk" and node is not None:
                match = next(
                    (f for f in node if f.tag == q("a:font") and f.get("script") == "Hans"), None
                )
                face = match.get("typeface") if match is not None else None
            values.append(face or ("Microsoft YaHei" if key == "cjk" else "Calibri"))
        fonts[key] = values
    bg, fg = colors.get("lt1", "FFFFFF"), colors.get("dk1", "000000")
    return {
        "colors": {
            "background": bg,
            "text": fg,
            "muted": fg,
            "accent": colors.get("accent1", fg),
            "accent_soft": colors.get("accent2", fg),
            "card_fill": bg,
            "card_line": colors.get("accent1", fg),
        },
        "fonts": fonts,
        "sizes": {},
    }
