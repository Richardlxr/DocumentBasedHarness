"""Inspect effective first-paragraph typography without importing its content or layout."""

from .package import NS, Package, StyleError, descendants, q, shape_id, shapes


def _placeholder(node):
    return node.find(".//p:ph", NS)


def effective_text_style(package: Package, slide: int, scope: str, identity: int) -> dict:
    scopes = package.scopes(slide)
    trees = {key: package.tree(part) for key, part in scopes.items()}
    node = next((s for s in descendants(shapes(trees[scope])) if shape_id(s) == identity), None)
    if node is None:
        raise StyleError(f"slide {slide}/{scope}: text style shape {identity} does not exist")
    chain = [node]
    ph = _placeholder(node)
    role = ph.get("type", "body") if ph is not None else "other"
    if scope == "slide" and ph is not None:
        for candidate in shapes(trees["layout"]):
            other = _placeholder(candidate)
            if other is not None and other.get("idx", "0") == ph.get("idx", "0"):
                chain.append(candidate)
                role = other.get("type", role)
                break
    if scope != "master" and ph is not None:
        for candidate in shapes(trees["master"]):
            other = _placeholder(candidate)
            if other is not None and other.get("type", "body") == role:
                chain.append(candidate)
                break
    properties = []
    for element in chain:
        body = element.find("p:txBody", NS)
        if body is None:
            continue
        for path in (
            "a:p/a:r/a:rPr",
            "a:p/a:pPr/a:defRPr",
            "a:p/a:endParaRPr",
            "a:lstStyle/a:lvl1pPr/a:defRPr",
        ):
            found = body.find(path, NS)
            if found is not None:
                properties.append(found)
    category = (
        "titleStyle"
        if role in {"title", "ctrTitle"}
        else "bodyStyle"
        if role == "body"
        else "otherStyle"
    )
    for tree, path in (
        (trees["master"], f"p:txStyles/p:{category}/a:lvl1pPr/a:defRPr"),
        (package.tree("ppt/presentation.xml"), "p:defaultTextStyle/a:lvl1pPr/a:defRPr"),
    ):
        found = tree.find(path, NS)
        if found is not None:
            properties.append(found)
    theme = package.tree(package.related(scopes["master"], "theme"))

    def face(script):
        raw = next(
            (
                p.find(f"a:{script}", NS).get("typeface")
                for p in properties
                if p.find(f"a:{script}", NS) is not None
            ),
            None,
        )
        if not raw or raw.startswith("+"):
            group = (
                "majorFont"
                if (raw and raw.startswith("+mj")) or role in {"title", "ctrTitle"}
                else "minorFont"
            )
            font = theme.find(f"a:themeElements/a:fontScheme/a:{group}", NS)
            entry = font.find(f"a:{script}", NS) if font is not None else None
            resolved = entry.get("typeface") if entry is not None else None
            if not resolved and script == "ea" and font is not None:
                hans = next(
                    (f for f in font if f.tag == q("a:font") and f.get("script") == "Hans"), None
                )
                resolved = hans.get("typeface") if hans is not None else None
            return resolved
        return raw

    size = next((int(p.get("sz")) / 100 for p in properties if p.get("sz")), None)
    bold = next((p.get("b") in {"1", "true"} for p in properties if p.get("b") is not None), None)
    italic = next((p.get("i") in {"1", "true"} for p in properties if p.get("i") is not None), None)
    color = None
    warnings = []
    for prop in properties:
        if any(
            prop.find("a:" + kind, NS) is not None
            for kind in ("gradFill", "pattFill", "blipFill", "noFill")
        ):
            warnings.append("non-solid text fill requires an explicit reviewed color token")
            break
        fill = prop.find("a:solidFill", NS)
        if fill is None or not len(fill):
            continue
        entry = fill[0]
        if len(entry):
            warnings.append("text color transforms require an explicit reviewed color token")
            break
        if entry.tag == q("a:srgbClr"):
            color = entry.get("val")
        elif entry.tag == q("a:schemeClr"):
            key = entry.get("val")
            mapping = trees["master"].find("p:clrMap", NS)
            if mapping is not None:
                key = mapping.get(key, key)
            resolved = theme.find(f"a:themeElements/a:clrScheme/a:{key}", NS)
            if resolved is not None and len(resolved):
                color = resolved[0].get("lastClr", resolved[0].get("val"))
        if color:
            break
    return {
        "latin": face("latin"),
        "cjk": face("ea"),
        "size_pt": size,
        "bold": bold,
        "italic": italic,
        "color": color,
        "warnings": warnings,
        "scope": "first paragraph/run; mixed formatting still needs inspection",
    }
