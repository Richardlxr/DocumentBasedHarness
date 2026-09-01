from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ..errors import DocumentError, SourceLocation
from .drawio_cli import DRAWIO_VERSION
from .layout import DiagramLayoutEngine, LayoutEdgeInput, LayoutNodeInput, Point, Rect
from .model import DiagramSource, DrawioDocument
from .style import CN_OFFICIAL_DIAGRAM_STYLE, DiagramStyleProfile

_HEADER = re.compile(r"^(?:flowchart|graph)\s+(TB|TD|BT|LR|RL)\s*$", re.IGNORECASE)
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*")
_EDGE_MARKERS = ("<-->", "-.->", "==>", "-->", "---")
_UNSUPPORTED = (
    "subgraph",
    "end",
    "classdef",
    "class ",
    "style ",
    "linkstyle",
    "click ",
    "direction ",
)


@dataclass(slots=True)
class _Node:
    key: str
    label: str
    shape: str = "rectangle"
    order: int = 0


@dataclass(frozen=True, slots=True)
class _Edge:
    source: str
    target: str
    label: str
    marker: str


def _error(message: str, source: DiagramSource, relative_line: int | None = None) -> DocumentError:
    location = source.location
    if location is not None and location.line is not None and relative_line is not None:
        location = SourceLocation(location.source, location.line + relative_line)
    return DocumentError(message, location)


def _strip_label(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return html.unescape(value.replace("<br/>", "\n").replace("<br>", "\n"))


def _parse_node(term: str, source: DiagramSource, line: int) -> tuple[str, str | None, str]:
    term = term.strip()
    match = _ID.match(term)
    if match is None:
        raise _error(f"unsupported Mermaid node expression: {term}", source, line)
    key = match.group(0)
    suffix = term[match.end() :].strip()
    if not suffix:
        return key, None, "rectangle"

    shapes = (
        ("((", "))", "ellipse"),
        ("([", "])", "stadium"),
        ("[[", "]]", "process"),
        ("[(", ")]", "cylinder"),
        ("{", "}", "rhombus"),
        ("(", ")", "rounded"),
        ("[", "]", "rectangle"),
    )
    for opening, closing, shape in shapes:
        if suffix.startswith(opening) and suffix.endswith(closing):
            return key, _strip_label(suffix[len(opening) : -len(closing)]), shape
    raise _error(f"unsupported Mermaid node shape: {term}", source, line)


def _split_edge_chain(statement: str) -> tuple[list[str], list[tuple[str, str]]]:
    terms: list[str] = []
    edges: list[tuple[str, str]] = []
    start = 0
    depth = 0
    quote: str | None = None
    index = 0
    while index < len(statement):
        char = statement[index]
        if quote:
            if char == quote and (index == 0 or statement[index - 1] != "\\"):
                quote = None
            index += 1
            continue
        if char in {'"', "'"}:
            quote = char
            index += 1
            continue
        if char in "[({":
            depth += 1
            index += 1
            continue
        if char in "]) }".replace(" ", ""):
            depth = max(0, depth - 1)
            index += 1
            continue
        marker = next(
            (candidate for candidate in _EDGE_MARKERS if statement.startswith(candidate, index)),
            None,
        )
        if depth == 0 and marker is not None:
            terms.append(statement[start:index].strip())
            index += len(marker)
            label = ""
            if index < len(statement) and statement[index] == "|":
                end = statement.find("|", index + 1)
                if end < 0:
                    return [], []
                label = statement[index + 1 : end].strip()
                index = end + 1
            edges.append((marker, label))
            start = index
            continue
        index += 1
    terms.append(statement[start:].strip())
    return terms, edges


def _statements(content: str) -> list[tuple[int, str]]:
    statements: list[tuple[int, str]] = []
    for line_number, raw in enumerate(content.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        for part in stripped.split(";"):
            if part.strip():
                statements.append((line_number, part.strip()))
    return statements


def _parse(source: DiagramSource) -> tuple[str, dict[str, _Node], list[_Edge]]:
    statements = _statements(source.content)
    if not statements:
        raise _error("empty Mermaid diagram", source)
    header_line, header = statements.pop(0)
    match = _HEADER.fullmatch(header)
    if match is None:
        kind = header.split(maxsplit=1)[0] if header else ""
        raise _error(
            f"unsupported Mermaid diagram type '{kind}'; registered converter currently "
            "accepts flowchart/graph",
            source,
            header_line,
        )
    direction = "TB" if match.group(1).upper() == "TD" else match.group(1).upper()
    nodes: dict[str, _Node] = {}
    edges: list[_Edge] = []

    def remember(key: str, label: str | None, shape: str) -> None:
        existing = nodes.get(key)
        if existing is None:
            nodes[key] = _Node(key, label or key, shape, len(nodes))
        elif label is not None:
            existing.label = label
            existing.shape = shape

    for line_number, statement in statements:
        lowered = statement.lower()
        if lowered == "end" or any(lowered.startswith(prefix) for prefix in _UNSUPPORTED):
            raise _error(
                f"unsupported Mermaid flowchart statement: {statement}", source, line_number
            )
        terms, connectors = _split_edge_chain(statement)
        if not connectors:
            if len(terms) != 1 or not terms[0]:
                raise _error(f"invalid Mermaid statement: {statement}", source, line_number)
            key, label, shape = _parse_node(terms[0], source, line_number)
            remember(key, label, shape)
            continue
        if len(terms) != len(connectors) + 1 or any(not term for term in terms):
            raise _error(f"invalid Mermaid edge chain: {statement}", source, line_number)
        parsed = [_parse_node(term, source, line_number) for term in terms]
        for key, label, shape in parsed:
            remember(key, label, shape)
        for index, (marker, label) in enumerate(connectors):
            edges.append(_Edge(parsed[index][0], parsed[index + 1][0], label, marker))
    if not nodes:
        raise _error("Mermaid flowchart has no nodes", source)
    return direction, nodes, edges


def _node_style(shape: str, profile: DiagramStyleProfile) -> str:
    if shape == "rounded":
        fill = profile.primary_fill
        text_color = profile.inverted_text_color
        stroke_color = profile.primary_fill
        stroke_width = profile.focus_stroke_width
        geometry = "rounded=1;arcSize=8;fontStyle=1;"
    elif shape in {"stadium", "ellipse"}:
        fill = profile.external_fill
        text_color = profile.text_color
        stroke_color = profile.external_stroke_color
        stroke_width = profile.node_stroke_width
        geometry = "rounded=1;arcSize=8;dashed=1;dashPattern=4 3;"
    elif shape == "process":
        fill = profile.focus_fill
        text_color = profile.text_color
        stroke_color = profile.focus_stroke_color
        stroke_width = profile.focus_stroke_width
        geometry = "rounded=1;arcSize=6;fontStyle=1;"
    elif shape == "rhombus":
        fill = profile.decision_fill
        text_color = profile.text_color
        stroke_color = profile.focus_stroke_color
        stroke_width = profile.focus_stroke_width
        geometry = "rhombus;"
    elif shape == "cylinder":
        fill = profile.focus_fill
        text_color = profile.text_color
        stroke_color = profile.focus_stroke_color
        stroke_width = profile.focus_stroke_width
        geometry = "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=15;"
    else:
        fill = profile.card_fill
        text_color = profile.text_color
        stroke_color = profile.stroke_color
        stroke_width = profile.node_stroke_width
        geometry = "rounded=1;arcSize=6;"
    base = (
        f"html=0;fontFamily={profile.font_family};fontSize={profile.node_font_size};"
        f"fillColor={fill};strokeColor={stroke_color};"
        f"fontColor={text_color};strokeWidth={stroke_width:g};"
        "align=center;verticalAlign=middle;spacing=10;shadow=0;glass=0;"
    )
    return geometry + base


def _edge_style(marker: str, profile: DiagramStyleProfile) -> str:
    dashed = "dashed=1;" if marker == "-.->" else ""
    width = profile.emphasized_edge_width if marker == "==>" else profile.edge_stroke_width
    end_arrow = "endArrow=none;" if marker == "---" else "endArrow=block;endFill=1;"
    start_arrow = "startArrow=block;startFill=1;" if marker == "<-->" else ""
    base = (
        "edgeStyle=none;rounded=0;orthogonal=1;orthogonalLoop=1;jettySize=0;"
        f"html=0;fontFamily={profile.font_family};"
        f"fontSize={profile.edge_font_size};fontColor={profile.text_color};"
        f"strokeColor={profile.edge_color};strokeWidth={width:g};"
        f"labelBackgroundColor={profile.label_fill};endSize=6;startSize=6;"
    )
    return f"{base}{dashed}{end_arrow}{start_arrow}"


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _normalized_port(point: Point, rect: Rect) -> tuple[float, float]:
    return (
        min(1.0, max(0.0, (point.x - rect.left) / rect.width)),
        min(1.0, max(0.0, (point.y - rect.top) / rect.height)),
    )


def convert_mermaid_flowchart(
    source: DiagramSource,
    *,
    style: DiagramStyleProfile = CN_OFFICIAL_DIAGRAM_STYLE,
) -> DrawioDocument:
    """Convert the supported Mermaid flowchart subset into independent native mxCells."""

    direction, nodes, edges = _parse(source)
    layout = DiagramLayoutEngine(
        font_family=style.font_family,
        node_font_size=style.node_font_size,
        edge_font_size=style.edge_font_size,
    ).layout(
        direction,
        [LayoutNodeInput(node.key, node.label, node.shape, node.order) for node in nodes.values()],
        [
            LayoutEdgeInput(f"edge-{index}", edge.source, edge.target, edge.label, index)
            for index, edge in enumerate(edges, 1)
        ],
    )

    digest = hashlib.sha256(source.content.encode("utf-8")).hexdigest()[:12]
    mxfile = ET.Element("mxfile", {"host": "docx-harness", "version": DRAWIO_VERSION})
    diagram = ET.SubElement(mxfile, "diagram", {"id": digest, "name": "Page-1"})
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "dx": "1200",
            "dy": "800",
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": "1169",
            "pageHeight": "827",
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    cell_ids: dict[str, str] = {}
    for index, node in enumerate(sorted(nodes.values(), key=lambda item: item.order), 2):
        cell_id = f"node-{index}-{node.key}"
        cell_ids[node.key] = cell_id
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": cell_id,
                "value": layout.nodes[node.key].label,
                "style": _node_style(node.shape, style),
                "vertex": "1",
                "parent": "1",
            },
        )
        placed = layout.nodes[node.key]
        rect = placed.rect
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": _number(rect.x),
                "y": _number(rect.y),
                "width": _number(rect.width),
                "height": _number(rect.height),
                "as": "geometry",
            },
        )
    for index, edge in enumerate(edges, 1):
        routed = layout.edges[f"edge-{index}"]
        source_rect = layout.nodes[edge.source].rect
        target_rect = layout.nodes[edge.target].rect
        exit_x, exit_y = _normalized_port(routed.source_port.point, source_rect)
        entry_x, entry_y = _normalized_port(routed.target_port.point, target_rect)
        edge_style = (
            _edge_style(edge.marker, style)
            + f"exitX={_number(exit_x)};exitY={_number(exit_y)};exitDx=0;exitDy=0;"
            + f"entryX={_number(entry_x)};entryY={_number(entry_y)};entryDx=0;entryDy=0;"
        )
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": f"edge-{index}",
                "value": edge.label,
                "style": edge_style,
                "edge": "1",
                "parent": "1",
                "source": cell_ids[edge.source],
                "target": cell_ids[edge.target],
            },
        )
        geometry = ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": _number(routed.label_fraction),
                "y": "0",
                "relative": "1",
                "as": "geometry",
            },
        )
        if routed.label_box is not None and routed.label_offset != Point(0, 0):
            ET.SubElement(
                geometry,
                "mxPoint",
                {
                    "x": _number(routed.label_offset.x),
                    "y": _number(routed.label_offset.y),
                    "as": "offset",
                },
            )
        waypoints = routed.points[1:-1]
        if waypoints:
            point_array = ET.SubElement(geometry, "Array", {"as": "points"})
            for point in waypoints:
                ET.SubElement(
                    point_array,
                    "mxPoint",
                    {"x": _number(point.x), "y": _number(point.y)},
                )
    ET.indent(mxfile, space="  ")
    return DrawioDocument(ET.tostring(mxfile, encoding="unicode"))


def create_mermaid_flowchart_converter(style: DiagramStyleProfile):
    """Bind a reusable style profile to the registered converter protocol."""

    def convert(source: DiagramSource) -> DrawioDocument:
        return convert_mermaid_flowchart(source, style=style)

    return convert
