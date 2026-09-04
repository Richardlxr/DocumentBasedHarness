from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import pytest

from docx_harness.compiler import compile_text
from docx_harness.diagrams import (
    CN_OFFICIAL_DIAGRAM_STYLE,
    DiagramArtifact,
    DiagramConverterRegistry,
    DiagramExportProfile,
    DiagramLayoutEngine,
    DiagramLayoutPolicy,
    DiagramSource,
    DrawioCli,
    DrawioDocument,
    FontMetrics,
    LayoutEdgeInput,
    LayoutNodeInput,
    cn_official_diagram_style,
    create_mermaid_flowchart_converter,
    default_diagram_registry,
)
from docx_harness.diagrams import drawio_cli as drawio_cli_module
from docx_harness.diagrams.drawio_cli import DRAWIO_VERSION
from docx_harness.errors import DocumentError, SourceLocation
from docx_harness.ir import DiagramBlock
from docx_harness.parser import parse_document
from docx_harness.renderers.diagram_ooxml import _png_size


def test_parser_promotes_mermaid_fence_to_diagram_ir() -> None:
    document = parse_document("```mermaid\nflowchart LR\nA --> B\n```\n", source="plan.md")

    assert isinstance(document.blocks[0], DiagramBlock)
    assert document.blocks[0].source_kind == "mermaid"


def test_parser_discovers_project_registered_diagram_language() -> None:
    registry = DiagramConverterRegistry()
    registry.add("my-dsl", lambda source: DrawioDocument("<mxGraphModel><root/></mxGraphModel>"))
    document = parse_document(
        "```my-dsl\nnode A\n```\n", source="plan.md", diagram_registry=registry
    )

    assert isinstance(document.blocks[0], DiagramBlock)
    assert document.blocks[0].source_kind == "my-dsl"


def test_mermaid_flowchart_becomes_native_mxgraph_cells() -> None:
    source = DiagramSource(
        "mermaid",
        "flowchart LR\nclient[测试端] -->|流量| dut{被测网络}\ndut --> server((对端))\n",
    )
    document = default_diagram_registry().convert(source)
    cells = document.graph_model.findall(".//mxCell")
    vertices = [cell for cell in cells if cell.get("vertex") == "1"]
    edges = [cell for cell in cells if cell.get("edge") == "1"]

    assert len(vertices) == 3
    assert len(edges) == 2
    assert all(edge.get("source") and edge.get("target") for edge in edges)
    assert all(edge.find("./mxGeometry") is not None for edge in edges)
    assert all("exitX=" in edge.get("style", "") for edge in edges)
    assert all("entryX=" in edge.get("style", "") for edge in edges)
    assert all("edgeStyle=none" in edge.get("style", "") for edge in edges)
    assert all("whiteSpace=wrap" not in vertex.get("style", "") for vertex in vertices)
    assert all("html=0" in vertex.get("style", "") for vertex in vertices)
    assert all("fontFamily=SimHei" in vertex.get("style", "") for vertex in vertices)
    assert "fillColor=#F8FAFB" in vertices[0].get("style", "")
    assert "fillColor=#EFEBDD" in vertices[1].get("style", "")
    assert "dashed=1" in vertices[2].get("style", "")
    assert all("fontFamily=SimHei" in edge.get("style", "") for edge in edges)
    assert "mermaidData" not in document.xml
    assert "shape=image" not in document.xml


def test_mermaid_precomputes_long_label_wrapping() -> None:
    source = DiagramSource(
        "mermaid",
        "flowchart LR\nnode[这是一个需要由转换器确定性换行的很长中文节点标题] --> target[目标]\n",
    )

    document = default_diagram_registry().convert(source)
    vertex = next(
        cell
        for cell in document.graph_model.findall(".//mxCell")
        if cell.get("id", "").endswith("-node")
    )

    assert "\n" in vertex.get("value", "")
    assert "whiteSpace=wrap" not in vertex.get("style", "")


def _layout(
    nodes: list[tuple[str, str]],
    edges: list[tuple[str, str, str]],
    *,
    direction: str = "TB",
    policy: DiagramLayoutPolicy | None = None,
):
    engine = DiagramLayoutEngine(
        font_family="SimHei",
        node_font_size=13,
        edge_font_size=11,
        policy=policy,
    )
    return engine.layout(
        direction,
        [
            LayoutNodeInput(key, label, "rectangle", order)
            for order, (key, label) in enumerate(nodes)
        ],
        [
            LayoutEdgeInput(f"edge-{order}", source, target, label, order)
            for order, (source, target, label) in enumerate(edges, 1)
        ],
    )


def test_font_metrics_measure_real_glyphs_and_wrap_deterministically() -> None:
    metrics = FontMetrics("SimHei")

    if metrics.measure("WW", 13)[0] == metrics.measure("ii", 13)[0]:
        pytest.skip(
            "resolved SimHei-compatible font uses full-width Latin glyphs "
            "(equal advances); glyph-proportion assertion needs a proportional build"
        )
    assert metrics.measure("WW", 13)[0] > metrics.measure("ii", 13)[0]
    first = metrics.wrap("确定性字体度量可以控制中文与 Latin wrapping", 13, 85)
    second = metrics.wrap("确定性字体度量可以控制中文与 Latin wrapping", 13, 85)

    assert first == second
    assert "\n" in first
    assert all(metrics.measure(line, 13)[0] <= 85 for line in first.splitlines())


def test_layout_allocates_distinct_fan_out_and_fan_in_ports() -> None:
    result = _layout(
        [("start", "开始"), ("left", "左侧"), ("right", "右侧"), ("end", "汇合")],
        [
            ("start", "left", "分支 A"),
            ("start", "right", "分支 B"),
            ("left", "end", "结果 A"),
            ("right", "end", "结果 B"),
        ],
    )

    outgoing = [result.edges["edge-1"].source_port, result.edges["edge-2"].source_port]
    incoming = [result.edges["edge-3"].target_port, result.edges["edge-4"].target_port]

    assert len({port.point for port in outgoing}) == 2
    assert len({port.stub for port in outgoing}) == 2
    assert len({port.point for port in incoming}) == 2
    assert len({port.stub for port in incoming}) == 2


def test_adjacent_rank_edges_share_a_common_bend_channel() -> None:
    result = _layout(
        [("source", "源节点"), ("left", "左分支"), ("right", "右分支")],
        [("source", "left", "分支 A"), ("source", "right", "分支 B")],
    )

    horizontal_lanes = []
    for edge in result.edges.values():
        horizontal_lanes.append(
            {
                start.y
                for start, end in edge.segments
                if start.y == pytest.approx(end.y) and start.x != pytest.approx(end.x)
            }
        )

    assert horizontal_lanes[0] & horizontal_lanes[1]


def test_aligned_nodes_use_a_straight_edge_without_bends() -> None:
    result = _layout(
        [("source", "源节点"), ("target", "目标节点")],
        [("source", "target", "")],
    )

    assert len(result.edges["edge-1"].points) == 2


def test_long_edge_label_reserves_a_sufficient_horizontal_segment() -> None:
    result = _layout(
        [("source", "测试端"), ("target", "被测端")],
        [("source", "target", "需要完整显示且不得压住箭头的长链路注解")],
        direction="LR",
    )
    edge = result.edges["edge-1"]
    horizontal_lengths = [
        abs(end.x - start.x) for start, end in edge.segments if start.y == pytest.approx(end.y)
    ]

    assert edge.label_box is not None
    assert max(horizontal_lengths) >= edge.label_box.width + 28


def test_layout_avoids_nodes_labels_lines_and_removes_collinear_bends() -> None:
    result = _layout(
        [
            ("control", "控制与观测面"),
            ("tools", "外部观测工具"),
            ("left", "旁路节点 A"),
            ("right", "旁路节点 B"),
            ("dut", "物理 DUT"),
        ],
        [
            ("control", "left", "运行与观测"),
            ("control", "right", "运行与观测"),
            ("left", "dut", "物理接口 / 隧道"),
            ("right", "dut", "物理接口 / 隧道"),
            ("tools", "dut", "旁路观测"),
        ],
    )

    for edge in result.edges.values():
        for first, middle, last in zip(edge.points, edge.points[1:], edge.points[2:], strict=False):
            assert not (first.x == middle.x == last.x)
            assert not (first.y == middle.y == last.y)


def test_layout_routes_a_long_edge_around_an_unrelated_node() -> None:
    result = _layout(
        [("source", "源"), ("middle", "中间障碍"), ("target", "目标")],
        [
            ("source", "middle", "第一跳"),
            ("middle", "target", "第二跳"),
            ("source", "target", "旁路"),
        ],
        direction="LR",
    )

    assert len(result.edges["edge-3"].points) >= 4
    adjacent_lanes = {
        start.x
        for start, end in result.edges["edge-2"].segments
        if start.x == pytest.approx(end.x) and start.y != pytest.approx(end.y)
    }
    long_edge_lanes = {
        start.x
        for start, end in result.edges["edge-3"].segments
        if start.x == pytest.approx(end.x) and start.y != pytest.approx(end.y)
    }
    assert min(abs(first - second) for first in adjacent_lanes for second in long_edge_lanes) <= 10


def test_layout_separates_parallel_edges_and_routes_a_back_edge_cleanly() -> None:
    result = _layout(
        [("a", "节点 A"), ("b", "节点 B"), ("c", "节点 C")],
        [
            ("a", "b", "并行链路 1"),
            ("a", "b", "并行链路 2"),
            ("b", "c", "前向链路"),
            ("c", "a", "返回链路"),
        ],
        direction="LR",
    )

    assert result.edges["edge-1"].source_port != result.edges["edge-2"].source_port
    assert result.edges["edge-1"].points != result.edges["edge-2"].points
    assert len(result.edges["edge-4"].points) >= 4


def test_layout_is_deterministic() -> None:
    nodes = [("a", "源节点"), ("b", "分支 B"), ("c", "分支 C"), ("d", "目标")]
    edges = [("a", "b", "A-B"), ("a", "c", "A-C"), ("b", "d", "B-D"), ("c", "d", "C-D")]

    assert _layout(nodes, edges) == _layout(nodes, edges)


def test_layout_rejects_unreadable_final_docx_scale() -> None:
    policy = DiagramLayoutPolicy(target_width=120, min_scaled_font_size=12)

    with pytest.raises(DocumentError, match="minimum readable font size"):
        _layout(
            [("source", "源节点"), ("target", "目标节点")],
            [("source", "target", "链路")],
            direction="LR",
            policy=policy,
        )


def test_mermaid_style_profile_can_be_reused_by_a_project_registry() -> None:
    registry = DiagramConverterRegistry()
    style = cn_official_diagram_style(font_family="KaiTi_GB2312")
    registry.add("mermaid", create_mermaid_flowchart_converter(style))

    document = registry.convert(DiagramSource("mermaid", "flowchart LR\nA --> B\n"))
    vertices = [
        cell for cell in document.graph_model.findall(".//mxCell") if cell.get("vertex") == "1"
    ]

    assert CN_OFFICIAL_DIAGRAM_STYLE.font_family == "SimHei"
    assert all("fontFamily=KaiTi_GB2312" in cell.get("style", "") for cell in vertices)


def test_cn_official_diagram_style_rejects_unmaintained_font() -> None:
    with pytest.raises(ValueError, match="cn-official diagram font"):
        cn_official_diagram_style(font_family="Comic Sans MS")


def test_unsupported_mermaid_fails_with_source_line() -> None:
    source = DiagramSource(
        "mermaid",
        "sequenceDiagram\nAlice->>Bob: hello\n",
        SourceLocation("plan.md", 20),
    )

    with pytest.raises(DocumentError, match=r"plan.md:21.*unsupported Mermaid diagram type"):
        default_diagram_registry().convert(source)


def test_native_validator_rejects_mermaid_plugin_image_cell() -> None:
    document = DrawioDocument(
        """<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>
        <mxCell id="2" vertex="1" parent="1" style="shape=image" mermaidData="{}">
        <mxGeometry as="geometry"/></mxCell></root></mxGraphModel>"""
    )

    with pytest.raises(DocumentError, match="Mermaid plugin payloads"):
        document.validate_native_graph(reject_image_cells=True)


def _fake_artifact(tmp_path: Path, source: DiagramSource) -> DiagramArtifact:
    drawio = tmp_path / "diagram.drawio"
    vsdx = tmp_path / "diagram.vsdx"
    png = tmp_path / "diagram.png"
    drawio.write_text("<mxGraphModel><root/></mxGraphModel>", encoding="utf-8")
    vsdx.write_bytes(b"PK\x03\x04fake-vsdx")
    png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00d\x00\x00\x002")
    return DiagramArtifact(source, drawio, {"vsdx": vsdx, "png": png}, png)


def _fake_png(tmp_path: Path, name: str, *, width: int, height: int) -> Path:
    png = tmp_path / name
    png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", width, height))
    return png


def test_png_display_size_uses_natural_size_without_upscaling(tmp_path: Path) -> None:
    png = _fake_png(tmp_path, "natural.png", width=288, height=144)

    cx, cy, width_points, height_points = _png_size(
        png,
        available_width_twips=6 * 1440,
        available_height_twips=8 * 1440,
        profile=DiagramExportProfile(),
    )

    assert cx == 914400
    assert cy == 457200
    assert width_points == pytest.approx(72)
    assert height_points == pytest.approx(36)


def test_png_display_size_caps_tall_diagram_by_page_height(tmp_path: Path) -> None:
    png = _fake_png(tmp_path, "tall.png", width=576, height=2304)

    _, _, width_points, height_points = _png_size(
        png,
        available_width_twips=6 * 1440,
        available_height_twips=8 * 1440,
        profile=DiagramExportProfile(),
    )

    assert width_points == pytest.approx(103.7, abs=0.1)
    assert height_points == pytest.approx(414.7, abs=0.1)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"png_scale": 0}, "png_scale"),
        ({"logical_dpi": 0}, "logical_dpi"),
        ({"max_width_fraction": 0}, "max_width_fraction"),
        ({"max_height_fraction": 1.1}, "max_height_fraction"),
    ),
)
def test_diagram_export_profile_rejects_invalid_display_settings(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        DiagramExportProfile(**kwargs)


@pytest.mark.parametrize(
    ("embed_format", "expected_part", "expected_preview", "expected_marker"),
    (
        ("vsdx", "word/embeddings/diagram1.vsdx", "word/media/diagram1.png", b"OLEObject"),
        ("png", "word/media/diagram1.png", "word/media/diagram1.png", b"pic:pic"),
    ),
)
def test_docx_packages_editable_diagram_with_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    embed_format: str,
    expected_part: str,
    expected_preview: str,
    expected_marker: bytes,
) -> None:
    def fake_build(self, source, output_dir, *, stem):
        return _fake_artifact(tmp_path, source)

    monkeypatch.setattr("docx_harness.renderers.docx.DiagramArtifactBuilder.build", fake_build)
    output = tmp_path / f"diagram-{embed_format}.docx"
    compile_text(
        "```mermaid\nflowchart LR\nA --> B\n```\n",
        output,
        source="plan.md",
        diagram_profile=DiagramExportProfile(embed_format=embed_format, auto_install_drawio=False),
    )

    with ZipFile(output) as package:
        assert expected_part in package.namelist()
        assert not any(name.endswith((".svg", ".emf")) for name in package.namelist())
        assert expected_preview in package.namelist()
        document_xml = package.read("word/document.xml")
        assert expected_marker in document_xml
        expected_size = b'w:dxaOrig="500"' if embed_format == "vsdx" else b'cx="317500"'
        assert expected_size in document_xml
        assert b'w:line="240"' in document_xml
        assert b'w:lineRule="auto"' in document_xml
        content_types = ET.fromstring(package.read("[Content_Types].xml"))
        assert content_types is not None
        assert b"image/png" in package.read("[Content_Types].xml")


def test_diagram_builds_are_offline_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("DRAWIO_CLI", raising=False)
    monkeypatch.setattr("docx_harness.diagrams.drawio_cli.shutil.which", lambda command: None)

    assert DiagramExportProfile().auto_install_drawio is False
    with pytest.raises(DocumentError, match="install-drawio|install draw.io Desktop"):
        DrawioCli().locate()


def test_drawio_cli_uses_product_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("DRAWIO_CLI", raising=False)
    monkeypatch.setattr("docx_harness.diagrams.drawio_cli.shutil.which", lambda command: None)
    executable = tmp_path / "docx-harness" / "drawio" / DRAWIO_VERSION / "squashfs-root" / "AppRun"
    executable.parent.mkdir(parents=True)
    executable.touch()

    assert DrawioCli().locate() == executable


def test_drawio_cli_discovers_standard_windows_install(tmp_path: Path, monkeypatch) -> None:
    program_files = tmp_path / "Program Files"
    executable = program_files / "draw.io" / "draw.io.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(drawio_cli_module.platform, "system", lambda: "Windows")
    monkeypatch.setenv("PROGRAMFILES", str(program_files))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("DRAWIO_CLI", raising=False)
    monkeypatch.setattr(drawio_cli_module.shutil, "which", lambda command: None)

    assert DrawioCli().locate() == executable


def test_drawio_cache_uses_windows_local_app_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(drawio_cli_module.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

    assert drawio_cli_module._default_cache() == (
        tmp_path / "docx-harness" / "drawio" / DRAWIO_VERSION
    )


def test_drawio_auto_install_explains_windows_manual_setup(monkeypatch) -> None:
    monkeypatch.setattr(drawio_cli_module.platform, "system", lambda: "Windows")

    with pytest.raises(DocumentError, match="supports Linux x86_64"):
        drawio_cli_module.install_drawio()
