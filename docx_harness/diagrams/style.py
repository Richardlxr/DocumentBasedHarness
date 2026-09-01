from __future__ import annotations

from dataclasses import dataclass, replace

CN_OFFICIAL_DIAGRAM_FONTS = (
    "SimHei",
    "FangSong_GB2312",
    "KaiTi_GB2312",
    "FZXiaoBiaoSong-B05",
    "NSimSun",
)


@dataclass(frozen=True, slots=True)
class DiagramStyleProfile:
    """Reusable draw.io visual tokens; projects may replace any field."""

    font_family: str = "SimHei"
    node_font_size: int = 13
    edge_font_size: int = 11
    text_color: str = "#263238"
    inverted_text_color: str = "#FFFFFF"
    stroke_color: str = "#7A8589"
    focus_stroke_color: str = "#526A78"
    external_stroke_color: str = "#83978D"
    edge_color: str = "#67777E"
    primary_fill: str = "#4F6673"
    card_fill: str = "#F8FAFB"
    focus_fill: str = "#E7EDF1"
    external_fill: str = "#F1F5F2"
    decision_fill: str = "#EFEBDD"
    label_fill: str = "#FFFFFF"
    node_stroke_width: float = 0.85
    focus_stroke_width: float = 1.45
    edge_stroke_width: float = 0.9
    emphasized_edge_width: float = 1.7


SWISS_TECHNICAL_DIAGRAM_STYLE = DiagramStyleProfile()
CN_OFFICIAL_DIAGRAM_STYLE = SWISS_TECHNICAL_DIAGRAM_STYLE


def cn_official_diagram_style(*, font_family: str = "SimHei") -> DiagramStyleProfile:
    """Select one of the maintained public-document font families."""

    if font_family not in CN_OFFICIAL_DIAGRAM_FONTS:
        raise ValueError(
            f"cn-official diagram font must be one of {', '.join(CN_OFFICIAL_DIAGRAM_FONTS)}"
        )
    return replace(CN_OFFICIAL_DIAGRAM_STYLE, font_family=font_family)
