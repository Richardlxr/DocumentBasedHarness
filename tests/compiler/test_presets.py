from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from docx_harness.presets import (
    CN_OFFICIAL_PAGE_NUMBER_STYLE,
    CN_OFFICIAL_RED_LINE_STYLE,
    available_template_presets,
)
from docx_harness.project import init_project, init_workspace, load_project, render_project
from docx_harness.renderers.styles import (
    BODY_STYLE,
    BODY_TEXT_STYLE,
    CODE_BLOCK_STYLE,
    CODE_CHARACTER_STYLE,
    HEADING_STYLES,
    MATH_BLOCK_STYLE,
    TABLE_CODE_BLOCK_STYLE,
    TABLE_CODE_CHARACTER_STYLE,
    TABLE_FIELD_LABEL_STYLE,
    TABLE_HEADING_STYLE,
    TABLE_MATH_BLOCK_STYLE,
    TABLE_STYLE,
    TABLE_TEXT_STYLE,
    TEST_CASE_TABLE_STYLE,
    TEST_CASE_TITLE_STYLE,
)
from docx_harness.template import create_template


def _close(actual, expected, tolerance=4000) -> bool:
    return abs(actual - expected) < tolerance


def test_lists_multiple_template_presets() -> None:
    assert available_template_presets() == ("standard", "cn-official")


def test_cn_official_preset_configures_gbt_9704_reference_layout(tmp_path: Path) -> None:
    template = create_template(tmp_path / "cn-official.docx", preset="cn-official")
    document = Document(template)
    section = document.sections[0]

    assert _close(section.page_width, Cm(21.0))
    assert _close(section.page_height, Cm(29.7))
    assert _close(section.top_margin, Cm(3.7))
    assert _close(section.bottom_margin, Cm(3.5))
    assert _close(section.left_margin, Cm(2.8))
    assert _close(section.right_margin, Cm(2.6))

    body = document.styles[BODY_STYLE]
    assert body.font.name == "仿宋_GB2312"
    assert body.font.size == Pt(14)
    assert body.paragraph_format.first_line_indent == Pt(0)
    assert body.paragraph_format.line_spacing == Pt(28.95)

    body_text = document.styles[BODY_TEXT_STYLE]
    assert body_text.base_style == body
    assert body_text.font.name == "仿宋_GB2312"
    assert body_text.font.size == Pt(14)
    assert body_text.paragraph_format.first_line_indent == Pt(28)
    assert body_text.paragraph_format.line_spacing == Pt(28.95)

    assert document.styles[CODE_BLOCK_STYLE].font.name == "Consolas"
    assert document.styles[CODE_BLOCK_STYLE].font.size == Pt(13)
    assert document.styles[CODE_CHARACTER_STYLE].font.name == "Consolas"
    assert document.styles[CODE_CHARACTER_STYLE].font.size == Pt(14)
    assert document.styles[MATH_BLOCK_STYLE].font.size == Pt(14)
    assert document.styles[MATH_BLOCK_STYLE].paragraph_format.alignment == (
        WD_ALIGN_PARAGRAPH.CENTER
    )

    assert document.styles[TABLE_STYLE].font.size == Pt(12)
    assert document.styles[TEST_CASE_TABLE_STYLE].font.size == Pt(12)
    assert document.styles[TABLE_TEXT_STYLE].font.size == Pt(12)
    assert document.styles[TABLE_TEXT_STYLE].paragraph_format.first_line_indent == Pt(0)
    assert document.styles[TABLE_HEADING_STYLE].font.size == Pt(12)
    assert document.styles[TABLE_HEADING_STYLE].paragraph_format.alignment == (
        WD_ALIGN_PARAGRAPH.CENTER
    )
    assert document.styles[TABLE_FIELD_LABEL_STYLE].font.size == Pt(12)
    assert document.styles[TABLE_FIELD_LABEL_STYLE].paragraph_format.alignment == (
        WD_ALIGN_PARAGRAPH.LEFT
    )
    assert document.styles[TABLE_CODE_BLOCK_STYLE].font.size == Pt(12)
    assert document.styles[TABLE_CODE_CHARACTER_STYLE].font.size == Pt(12)
    assert document.styles[TABLE_MATH_BLOCK_STYLE].font.size == Pt(12)
    assert document.styles[TEST_CASE_TITLE_STYLE].font.size == Pt(12)
    assert str(document.styles[TEST_CASE_TITLE_STYLE].font.color.rgb) == "000000"
    assert document.styles[TEST_CASE_TITLE_STYLE].paragraph_format.alignment == (
        WD_ALIGN_PARAGRAPH.CENTER
    )

    title = document.styles[HEADING_STYLES[1]]
    assert title.font.name == "方正小标宋简体"
    assert title.font.size == Pt(22)
    assert title.paragraph_format.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert document.styles[HEADING_STYLES[2]].font.name == "黑体"
    assert document.styles[HEADING_STYLES[3]].font.name == "楷体_GB2312"
    assert CN_OFFICIAL_RED_LINE_STYLE in document.styles

    assert document.settings.odd_and_even_pages_header_footer
    odd_footer = section.footer.paragraphs[0]
    even_footer = section.even_page_footer.paragraphs[0]
    assert odd_footer.style.name == CN_OFFICIAL_PAGE_NUMBER_STYLE
    assert odd_footer.alignment == WD_ALIGN_PARAGRAPH.RIGHT
    assert even_footer.alignment == WD_ALIGN_PARAGRAPH.LEFT
    assert "PAGE" in odd_footer._p.xml


def test_cn_official_project_renders_with_its_own_preset(tmp_path: Path) -> None:
    workspace = init_workspace(tmp_path)
    project = init_project("official-notices", workspace=workspace, preset="cn-official")
    config = load_project(project)
    output = render_project(project, "documents/example.md")
    document = Document(output)

    assert config.template_preset == "cn-official"
    assert document.paragraphs[0].style.name == HEADING_STYLES[1]
    assert document.paragraphs[0].style.font.size == Pt(22)
    assert document.sections[0].top_margin == Document(config.template).sections[0].top_margin
