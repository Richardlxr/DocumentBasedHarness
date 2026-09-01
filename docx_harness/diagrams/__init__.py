"""Native draw.io diagram conversion and export."""

from .artifacts import DiagramArtifact, DiagramArtifactBuilder, DiagramExportProfile
from .drawio_cli import DRAWIO_VERSION, DrawioCli, install_drawio
from .layout import (
    DiagramLayoutEngine,
    DiagramLayoutPolicy,
    LayoutEdgeInput,
    LayoutNodeInput,
    LayoutResult,
    PlacedNode,
    Point,
    Port,
    Rect,
    RoutedEdge,
)
from .mermaid import create_mermaid_flowchart_converter
from .metrics import FontMetrics
from .model import (
    DiagramConverterRegistry,
    DiagramSource,
    DrawioDocument,
    default_diagram_registry,
)
from .style import (
    CN_OFFICIAL_DIAGRAM_FONTS,
    CN_OFFICIAL_DIAGRAM_STYLE,
    SWISS_TECHNICAL_DIAGRAM_STYLE,
    DiagramStyleProfile,
    cn_official_diagram_style,
)

__all__ = [
    "DRAWIO_VERSION",
    "CN_OFFICIAL_DIAGRAM_FONTS",
    "CN_OFFICIAL_DIAGRAM_STYLE",
    "SWISS_TECHNICAL_DIAGRAM_STYLE",
    "DiagramArtifact",
    "DiagramArtifactBuilder",
    "DiagramConverterRegistry",
    "DiagramExportProfile",
    "DiagramLayoutEngine",
    "DiagramLayoutPolicy",
    "DiagramSource",
    "DrawioCli",
    "DrawioDocument",
    "DiagramStyleProfile",
    "FontMetrics",
    "LayoutEdgeInput",
    "LayoutNodeInput",
    "LayoutResult",
    "PlacedNode",
    "Point",
    "Port",
    "Rect",
    "RoutedEdge",
    "create_mermaid_flowchart_converter",
    "cn_official_diagram_style",
    "default_diagram_registry",
    "install_drawio",
]
