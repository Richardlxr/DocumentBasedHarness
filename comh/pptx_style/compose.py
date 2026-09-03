"""Native style composition. No source content, density, layout slots or animations are imported."""

from __future__ import annotations

import math
from copy import deepcopy

from lxml import etree as ET

from .package import (
    NS,
    REL,
    AssetCopier,
    Package,
    StyleError,
    blob,
    descendants,
    q,
    relpath,
    select_shapes,
    shape_id,
    shapes,
    target,
)
from .profile import Surface
from .text import assess_text, preserve_single_line


def _rels():
    return ET.Element(q("rel:Relationships"), nsmap={None: NS["rel"]})


def _add_rel(rels, identity, kind, path):
    ET.SubElement(rels, q("rel:Relationship"), Id=identity, Type=REL + kind, Target=path)


def _surface_tree(source, scope, part, surface, copier, output_part):
    original = source.tree(part)
    root = ET.Element(original.tag, dict(original.attrib), nsmap=original.nsmap)
    # Visual inheritance only. In particular, sample-page transitions/timing do not cross over.
    rels = _rels()
    cs = original.find("p:cSld", NS)
    clean = ET.SubElement(root, q("p:cSld"))
    bg = cs.find("p:bg", NS)
    if bg is not None:
        clean.append(copier.element(bg, part, output_part, rels))
    tree = ET.SubElement(clean, q("p:spTree"))
    old_tree = cs.find("p:spTree", NS)
    for node in old_tree:
        if node.tag in {q("p:nvGrpSpPr"), q("p:grpSpPr")}:
            tree.append(deepcopy(node))
    for node in select_shapes(shapes(original), surface.selected(scope)):
        tree.append(copier.element(node, part, output_part, rels))
    for node in descendants(shapes(root)):
        if shape_id(node) in dict(surface.single_line).get(scope, ()):
            assessment = assess_text(source, surface.slide, scope, node)
            if assessment is None:
                raise StyleError(f"{scope}/{shape_id(node)}: single_line requires text")
            preserve_single_line(node, assessment, location=f"{scope}/{shape_id(node)}")
    for tag in ("clrMap", "clrMapOvr", "txStyles"):
        node = original.find("p:" + tag, NS)
        if node is not None:
            root.append(deepcopy(node))
    for rel in source.relationships(part):
        if rel.get("Type") == REL + "themeOverride":
            if rel.get("TargetMode") == "External":
                raise StyleError(f"external theme override: {part}")
            copied = copier.copy(target(part, rel.get("Target")))
            _add_rel(
                rels,
                "rIdStyleThemeOverride",
                "themeOverride",
                "../theme/" + copied.rsplit("/", 1)[-1],
            )
    # A selected connector must not retain endpoints bound to omitted source content.
    kept_ids = {n.get("id") for n in tree.findall(".//p:cNvPr", NS)}
    for connector in tree.findall(".//a:stCxn", NS) + tree.findall(".//a:endCxn", NS):
        if connector.get("id") not in kept_ids:
            raise StyleError(
                f"{scope}: selected connector refers to omitted shape {connector.get('id')}"
            )
    return root, rels


def _scale_content(tree, scale: float, dy: int, font_sizes: dict[int, int]) -> None:
    """Uniform geometry transform into the actual canvas; compensate typography before layout."""
    if scale == 1 and dy == 0:
        return
    for shape in shapes(tree):
        for node in shape.iter():
            local = node.tag.rsplit("}", 1)[-1]
            if local in {"off", "ext", "chOff", "chExt"}:
                for attr in ("x", "y", "cx", "cy"):
                    if node.get(attr) is not None:
                        node.set(attr, str(round(int(node.get(attr)) * scale)))
            for attr in ("marL", "marR", "indent", "lIns", "rIns", "tIns", "bIns"):
                if node.get(attr) is not None:
                    node.set(attr, str(round(int(node.get(attr)) * scale)))
            if local in {"rPr", "defRPr", "endParaRPr"} and node.get("sz"):
                old = int(node.get("sz"))
                node.set("sz", str(font_sizes.get(old, round(old * scale))))
            if local == "spcPts" and node.get("val"):
                node.set("val", str(round(int(node.get("val")) * scale)))
            if local == "ln" and node.get("w"):
                node.set("w", str(round(int(node.get("w")) * scale)))
        transform = shape.find("p:spPr/a:xfrm/a:off", NS)
        if transform is None:
            transform = shape.find("p:xfrm/a:off", NS)
        if transform is None:
            transform = shape.find("p:grpSpPr/a:xfrm/a:off", NS)
        if transform is not None:
            transform.set("y", str(int(transform.get("y")) + dy))


def _remap_content_ids(tree, starting: int) -> dict[int, int]:
    mapping = {}
    for shape in shapes(tree):
        for node in shape.findall(".//p:cNvPr", NS):
            old = int(node.get("id"))
            mapping[old] = starting
            node.set("id", str(starting))
            starting += 1
    for node in tree.iter():
        if node.tag in {q("a:stCxn"), q("a:endCxn")} and node.get("id"):
            node.set("id", str(mapping[int(node.get("id"))]))
        if node.tag == q("p:spTgt") and node.get("spid"):
            node.set("spid", str(mapping[int(node.get("spid"))]))
    return mapping


def _box(node):
    transform = node.find(".//a:xfrm", NS)
    if transform is None:
        transform = node.find("p:xfrm", NS)
    if transform is None:
        return None
    offset, extent = transform.find("a:off", NS), transform.find("a:ext", NS)
    if offset is None or extent is None:
        return None
    x, y = int(offset.get("x")), int(offset.get("y"))
    w, h = int(extent.get("cx")), int(extent.get("cy"))
    angle = math.radians(int(transform.get("rot", "0")) / 60000)
    rw = abs(w * math.cos(angle)) + abs(h * math.sin(angle))
    rh = abs(w * math.sin(angle)) + abs(h * math.cos(angle))
    return x + (w - rw) / 2, y + (h - rh) / 2, x + (w + rw) / 2, y + (h + rh) / 2


def _check_protected(source, surface, generated, page_id, layers):
    content = [
        (shape_id(s), _box(s))
        for s in shapes(generated)
        if s.find(".//p:cNvPr", NS).get("name") != "decor"
    ]
    for scope, layer in layers.items():
        ids = set(dict(surface.protect).get(scope, ())) | set(
            dict(surface.single_line).get(scope, ())
        )
        for shape in shapes(layer):
            if shape_id(shape) not in ids:
                continue
            box = _box(shape)
            if box is None:
                raise StyleError(f"{page_id}: cannot measure protected {scope}/{shape_id(shape)}")
            for identity, other in content:
                if other is None:
                    continue
                w = min(box[2], other[2]) - max(box[0], other[0])
                h = min(box[3], other[3]) - max(box[1], other[1])
                if w > 0 and h > 0:
                    raise StyleError(
                        f"{page_id}: content shape {identity} overlaps protected "
                        f"style element {scope}/{shape_id(shape)}"
                    )


def _check_expanded_labels(source, surface, layers, page_id):
    size = source.tree("ppt/presentation.xml").find("p:sldSz", NS)
    scopes = source.scopes(surface.slide)
    for scope, ids in surface.single_line:
        originals = {shape_id(n): n for n in shapes(source.tree(scopes[scope]))}
        for node in shapes(layers[scope]):
            if shape_id(node) not in ids:
                continue
            new, old = _box(node), _box(originals[shape_id(node)])
            if (
                new[0] < 0
                or new[1] < 0
                or new[2] > int(size.get("cx"))
                or new[3] > int(size.get("cy"))
            ):
                raise StyleError(f"{page_id}: single_line {scope}/{shape_id(node)} leaves canvas")
            for other_scope, layer in layers.items():
                for other in shapes(layer):
                    if other is node:
                        continue
                    box = _box(other)

                    def overlap(a, b):
                        return (
                            b is not None
                            and min(a[2], b[2]) > max(a[0], b[0])
                            and min(a[3], b[3]) > max(a[1], b[1])
                        )

                    if overlap(new, box) and not overlap(old, box):
                        raise StyleError(
                            f"{page_id}: expanded single_line {scope}/{shape_id(node)} "
                            f"overlaps style element {other_scope}/{shape_id(other)}"
                        )


def compose(
    source: Package,
    dest: Package,
    surfaces: list[Surface],
    page_ids: list[str],
    font_maps: list[dict[int, int]],
    scale: float,
    dy: int,
) -> dict:
    copier = AssetCopier(source, dest)
    pres = dest.tree("ppt/presentation.xml")
    src_size = source.tree("ppt/presentation.xml").find("p:sldSz", NS)
    pres.find("p:sldSz", NS).attrib.clear()
    pres.find("p:sldSz", NS).attrib.update(src_size.attrib)
    master_list = pres.find("p:sldMasterIdLst", NS)
    master_list.clear()
    pres_rels = ET.Element(q("rel:Relationships"), nsmap={None: NS["rel"]})
    for rel in dest.relationships("ppt/presentation.xml"):
        if rel.get("Type") != REL + "slideMaster":
            pres_rels.append(deepcopy(rel))
    slide_parts = dest.slides()
    mappings = {}
    for index, (part, surface, page_id) in enumerate(
        zip(slide_parts, surfaces, page_ids, strict=True)
    ):
        scopes = source.scopes(surface.slide)
        master_part = f"ppt/slideMasters/comhStyleMaster{index + 1}.xml"
        layout_part = f"ppt/slideLayouts/comhStyleLayout{index + 1}.xml"
        master, mr = _surface_tree(source, "master", scopes["master"], surface, copier, master_part)
        layout, lr = _surface_tree(source, "layout", scopes["layout"], surface, copier, layout_part)
        slide, sr = _surface_tree(source, "slide", scopes["slide"], surface, copier, part)
        theme = copier.copy(source.related(scopes["master"], "theme"))
        _add_rel(mr, "rIdMasterTheme", "theme", "../theme/" + theme.rsplit("/", 1)[-1])
        _add_rel(
            mr,
            "rIdMasterLayout",
            "slideLayout",
            "../slideLayouts/" + layout_part.rsplit("/", 1)[-1],
        )
        listing = ET.Element(q("p:sldLayoutIdLst"))
        ET.SubElement(
            listing, q("p:sldLayoutId"), id="2147483649", attrib={q("r:id"): "rIdMasterLayout"}
        )
        tx_styles = master.find("p:txStyles", NS)
        master.insert(
            list(master).index(tx_styles) if tx_styles is not None else len(master), listing
        )
        _add_rel(
            lr,
            "rIdLayoutMaster",
            "slideMaster",
            "../slideMasters/" + master_part.rsplit("/", 1)[-1],
        )
        for original in dest.relationships(part):
            node = deepcopy(original)
            if node.get("Type") == REL + "slideLayout":
                node.set("Target", "../slideLayouts/" + layout_part.rsplit("/", 1)[-1])
            if any(r.get("Id") == node.get("Id") for r in sr):
                raise StyleError("generated and imported relationship IDs collided")
            sr.append(node)
        generated = dest.tree(part)
        _scale_content(generated, scale, dy, font_maps[index])
        # Built-in accent bars belong to the default appearance, not the imported style.
        content_tree = generated.find("p:cSld/p:spTree", NS)
        for shape in shapes(generated):
            if shape.find(".//p:cNvPr", NS).get("name") == "decor":
                content_tree.remove(shape)
        layers = {"master": master, "layout": layout, "slide": slide}
        _check_expanded_labels(source, surface, layers, page_id)
        _check_protected(source, surface, generated, page_id, layers)
        highest = max((int(n.get("id")) for n in slide.findall(".//p:cNvPr", NS)), default=1)
        mapping = _remap_content_ids(generated, highest + 1)
        mappings[page_id] = mapping
        for shape in shapes(generated):
            slide.find("p:cSld/p:spTree", NS).append(deepcopy(shape))
        for tag in ("transition", "timing"):
            node = generated.find("p:" + tag, NS)
            if node is not None:
                slide.append(deepcopy(node))
        for output_part, tree, rels, source_part in (
            (part, slide, sr, scopes["slide"]),
            (layout_part, layout, lr, scopes["layout"]),
            (master_part, master, mr, scopes["master"]),
        ):
            dest.parts[output_part] = blob(tree)
            dest.parts[relpath(output_part)] = blob(rels)
            dest.set_type(output_part, source.content_type(source_part))
        rid = f"rIdComhStyleMaster{index + 1}"
        _add_rel(pres_rels, rid, "slideMaster", "slideMasters/" + master_part.rsplit("/", 1)[-1])
        ET.SubElement(
            master_list, q("p:sldMasterId"), id=str(2147483648 + index), attrib={q("r:id"): rid}
        )
    dest.parts["ppt/presentation.xml"] = blob(pres)
    dest.parts[relpath("ppt/presentation.xml")] = blob(pres_rels)
    return {"shape_ids": mappings, "copied_assets": copier.copied}
