from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.part import Part
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.oxml.shape import CT_Inline
from docx.shared import Twips

from ..diagrams.artifacts import DiagramArtifact, DiagramExportProfile

VSDX_CONTENT_TYPE = "application/vnd.ms-visio.drawing"
PNG_CONTENT_TYPE = "image/png"


def _add_part(document_part, path: Path, *, partname: str, content_type: str, reltype: str) -> str:
    package = document_part.package
    name = package.next_partname(partname)
    part = Part(name, content_type, path.read_bytes(), package)
    return document_part.relate_to(part, reltype)


def _png_size(
    path: Path,
    available_width_twips: int,
    available_height_twips: int,
    profile: DiagramExportProfile,
) -> tuple[int, int, float, float]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"invalid PNG diagram preview: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid PNG diagram dimensions: {path}")
    pixels_per_inch = profile.logical_dpi * profile.png_scale
    natural_width_twips = width * 1440 / pixels_per_inch
    natural_height_twips = height * 1440 / pixels_per_inch
    max_width_twips = available_width_twips * profile.max_width_fraction
    max_height_twips = available_height_twips * profile.max_height_fraction
    scale = min(
        max_width_twips / natural_width_twips,
        max_height_twips / natural_height_twips,
    )
    if not profile.allow_upscale:
        scale = min(scale, 1.0)
    display_width_twips = max(1, round(natural_width_twips * scale))
    display_height_twips = max(1, round(natural_height_twips * scale))
    cx = int(Twips(display_width_twips))
    cy = int(Twips(display_height_twips))
    return cx, cy, cx / 12700, cy / 12700


def add_vsdx_object(
    paragraph,
    artifact: DiagramArtifact,
    *,
    available_width_twips: int,
    available_height_twips: int,
    profile: DiagramExportProfile,
) -> None:
    """Add a Visio OLE object backed by VSDX with a PNG preview."""

    document_part = paragraph.part
    vsdx = artifact.require("vsdx")
    ole_rid = _add_part(
        document_part,
        vsdx,
        partname="/word/embeddings/diagram%d.vsdx",
        content_type=VSDX_CONTENT_TYPE,
        reltype=RT.OLE_OBJECT,
    )
    preview_rid = _add_part(
        document_part,
        artifact.require("png"),
        partname="/word/media/diagram%d.png",
        content_type=PNG_CONTENT_TYPE,
        reltype=RT.IMAGE,
    )
    _, _, width_points, height_points = _png_size(
        artifact.require("png"),
        available_width_twips,
        available_height_twips,
        profile,
    )
    digest = hashlib.sha256(vsdx.read_bytes()).hexdigest()[:8].upper()
    shape_id = f"_x0000_i{1024 + document_part.next_id}"
    object_id = f"_{digest}"
    namespaces = (
        f'{nsdecls("w", "r")} xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office"'
    )
    xml = (
        f"<w:object {namespaces} "
        f'w:dxaOrig="{round(width_points * 20)}" w:dyaOrig="{round(height_points * 20)}">'
        f'<v:shape id="{shape_id}" type="#_x0000_t75" '
        f'style="width:{width_points:.2f}pt;height:{height_points:.2f}pt" o:ole="">'
        f'<v:imagedata r:id="{preview_rid}" o:title="{artifact.drawio.stem}"/>'
        "</v:shape>"
        f'<o:OLEObject Type="Embed" ProgID="Visio.Drawing.15" ShapeID="{shape_id}" '
        f'DrawAspect="Content" ObjectID="{object_id}" r:id="{ole_rid}"/>'
        "</w:object>"
    )
    paragraph.add_run()._r.append(parse_xml(xml))
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER


def add_png_picture(
    paragraph,
    artifact: DiagramArtifact,
    *,
    available_width_twips: int,
    available_height_twips: int,
    profile: DiagramExportProfile,
) -> None:
    """Add the high-resolution PNG diagram as a normal DrawingML picture."""

    png = artifact.require("png")
    png_rid = _add_part(
        paragraph.part,
        png,
        partname="/word/media/diagram%d.png",
        content_type=PNG_CONTENT_TYPE,
        reltype=RT.IMAGE,
    )
    cx, cy, _, _ = _png_size(
        png,
        available_width_twips,
        available_height_twips,
        profile,
    )
    inline = CT_Inline.new_pic_inline(
        paragraph.part.next_id,
        png_rid,
        png.name,
        cx,
        cy,
    )
    paragraph.add_run()._r.add_drawing(inline)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
