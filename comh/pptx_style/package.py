"""Small OPC adapter. Copy native style assets and their relationships, never slide content."""

from __future__ import annotations

import io
import posixpath
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from lxml import etree as ET

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
REL = NS["r"] + "/"


class StyleError(RuntimeError):
    """An actionable style-source or compile error."""


def xml(data: bytes):
    try:
        tree = ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True))
    except ET.XMLSyntaxError as error:
        raise StyleError(f"invalid PPTX XML: {error}") from error
    if tree.getroottree().docinfo.doctype:
        raise StyleError("PPTX XML must not contain a DTD")
    return tree


def blob(tree) -> bytes:
    return ET.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)


def q(name: str) -> str:
    prefix, local = name.split(":")
    return f"{{{NS[prefix]}}}{local}"


def relpath(part: str) -> str:
    return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")


def target(part: str, ref: str) -> str:
    path = posixpath.normpath(posixpath.join(posixpath.dirname(part), ref))
    if ref.startswith("/"):
        path = ref[1:]
    if path.startswith("../") or "\\" in path or ":" in path:
        raise StyleError(f"invalid package relationship: {part} → {ref}")
    return path


class Package:
    def __init__(self, source: Path | bytes):
        try:
            with ZipFile(io.BytesIO(source) if isinstance(source, bytes) else source) as archive:
                entries = archive.infolist()
                names = [i.filename for i in entries]
                if len(names) != len(set(names)):
                    raise StyleError("PPTX has duplicate ZIP entries")
                if len(entries) > 20000 or sum(i.file_size for i in entries) > 512 * 1024**2:
                    raise StyleError("PPTX exceeds the 512 MiB / 20000-part inspection limit")
                if any(n.startswith("/") or ".." in n.split("/") or "\\" in n for n in names):
                    raise StyleError("PPTX contains unsafe part names")
                self.parts = {i.filename: archive.read(i) for i in entries if not i.is_dir()}
        except (BadZipFile, OSError) as error:
            raise StyleError(f"cannot read PPTX: {error}") from error
        for required in ("[Content_Types].xml", "ppt/presentation.xml"):
            if required not in self.parts:
                raise StyleError(f"PPTX is missing {required}")
        self.types = xml(self.parts["[Content_Types].xml"])

    def tree(self, name: str):
        if name not in self.parts:
            raise StyleError(f"missing PPTX part: {name}")
        return xml(self.parts[name])

    def relationships(self, part: str):
        path = relpath(part)
        return list(xml(self.parts[path])) if path in self.parts else []

    def related(self, part: str, kind: str) -> str:
        matches = [r for r in self.relationships(part) if r.get("Type") == REL + kind]
        if len(matches) != 1 or matches[0].get("TargetMode") == "External":
            raise StyleError(f"{part} needs one local {kind} relationship")
        return target(part, matches[0].get("Target"))

    def slides(self) -> list[str]:
        rels = {r.get("Id"): r for r in self.relationships("ppt/presentation.xml")}
        result = []
        for node in self.tree("ppt/presentation.xml").findall("p:sldIdLst/p:sldId", NS):
            rel = rels.get(node.get(q("r:id")))
            if rel is None or rel.get("Type") != REL + "slide":
                raise StyleError("invalid slide ordering relationship")
            result.append(target("ppt/presentation.xml", rel.get("Target")))
        return result

    def scopes(self, slide: int) -> dict[str, str]:
        slides = self.slides()
        if not 1 <= slide <= len(slides):
            raise StyleError(f"source slide {slide} does not exist (1..{len(slides)})")
        s = slides[slide - 1]
        layout = self.related(s, "slideLayout")
        return {"slide": s, "layout": layout, "master": self.related(layout, "slideMaster")}

    def content_type(self, part: str) -> str:
        for node in self.types:
            if node.get("PartName") == "/" + part:
                return node.get("ContentType")
        for node in self.types:
            if node.get("Extension") == part.rsplit(".", 1)[-1]:
                return node.get("ContentType")
        raise StyleError(f"part has no content type: {part}")

    def set_type(self, part: str, content_type: str) -> None:
        for node in self.types:
            if node.get("PartName") == "/" + part:
                node.set("ContentType", content_type)
                return
        ET.SubElement(self.types, q("ct:Override"), PartName="/" + part, ContentType=content_type)

    def save(self, path: Path) -> None:
        self.parts["[Content_Types].xml"] = blob(self.types)
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            for name, data in sorted(self.parts.items()):
                archive.writestr(name, data)


def shape_id(shape) -> int:
    nodes = shape.findall(".//p:cNvPr", NS)
    if not nodes:
        raise StyleError("shape has no identity")
    return int(nodes[0].get("id"))


def shapes(tree) -> list:
    sp = tree.find("p:cSld/p:spTree", NS)
    return [] if sp is None else [s for s in sp if s.tag not in {q("p:nvGrpSpPr"), q("p:grpSpPr")}]


def descendants(nodes):
    for node in nodes:
        yield node
        if node.tag == q("p:grpSp"):
            yield from descendants(
                [n for n in node if n.tag not in {q("p:nvGrpSpPr"), q("p:grpSpPr")}]
            )


def select_shapes(nodes, selected: tuple[int, ...]) -> list:
    """Selecting a nested icon retains its group's coordinate transform, not its siblings."""
    result = []
    for node in nodes:
        if shape_id(node) in selected:
            result.append(deepcopy(node))
        elif node.tag == q("p:grpSp"):
            children = [n for n in node if n.tag not in {q("p:nvGrpSpPr"), q("p:grpSpPr")}]
            kept = select_shapes(children, selected)
            if kept:
                group = deepcopy(node)
                for child in list(group):
                    if child.tag not in {q("p:nvGrpSpPr"), q("p:grpSpPr")}:
                        group.remove(child)
                group.extend(kept)
                result.append(group)
    return result


class AssetCopier:
    """Copy only resource graphs referenced by selected style elements.

    Slides, notes, hyperlinks and executable objects are never imported as assets.
    Native images, theme parts and their local dependencies remain byte-for-byte.
    """

    def __init__(self, source: Package, dest: Package):
        self.source, self.dest = source, dest
        self.copied: dict[str, str] = {}

    def copy(self, part: str) -> str:
        if part in self.copied:
            return self.copied[part]
        allowed = ("ppt/media/", "ppt/theme/", "ppt/fonts/")
        if not part.startswith(allowed):
            raise StyleError(f"unsupported style asset dependency: {part}")
        path = posixpath.join(posixpath.dirname(part), "comh-style-" + posixpath.basename(part))
        if path in self.dest.parts:
            raise StyleError(f"style asset name collision: {path}")
        self.copied[part] = path
        self.dest.parts[path] = self.source.parts[part]
        self.dest.set_type(path, self.source.content_type(part))
        rels = self.source.relationships(part)
        if rels:
            root = ET.Element(q("rel:Relationships"), nsmap={None: NS["rel"]})
            for rel in rels:
                if rel.get("TargetMode") == "External":
                    raise StyleError(f"external style resource is unsupported: {part}")
                node = deepcopy(rel)
                copied = self.copy(target(part, rel.get("Target")))
                node.set("Target", posixpath.relpath(copied, posixpath.dirname(path)))
                root.append(node)
            self.dest.parts[relpath(path)] = blob(root)
        return path

    def element(self, node, owner: str, dest_owner: str, rels) -> object:
        copied = deepcopy(node)
        original = {r.get("Id"): r for r in self.source.relationships(owner)}
        for element in copied.iter():
            for attr, value in list(element.attrib.items()):
                if not attr.startswith("{" + NS["r"] + "}"):
                    continue
                rel = original.get(value)
                if rel is None or rel.get("TargetMode") == "External":
                    raise StyleError(f"unresolved/external relationship in style element: {owner}")
                if rel.get("Type") not in {
                    REL + "image",
                    REL + "theme",
                    REL + "themeOverride",
                    "http://schemas.microsoft.com/office/2007/relationships/hdphoto",
                }:
                    raise StyleError(f"unsupported style element relationship: {rel.get('Type')}")
                resource = self.copy(target(owner, rel.get("Target")))
                rid = f"rIdStyle{len(rels) + 1}"
                while any(r.get("Id") == rid for r in rels):
                    rid += "x"
                ET.SubElement(
                    rels,
                    q("rel:Relationship"),
                    Id=rid,
                    Type=rel.get("Type"),
                    Target=posixpath.relpath(resource, posixpath.dirname(dest_owner)),
                )
                element.set(attr, rid)
        return copied
