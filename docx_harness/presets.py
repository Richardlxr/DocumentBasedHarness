from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .renderers.fields import append_word_field, request_field_update
from .renderers.ooxml import configure_run_style, ensure_style
from .renderers.styles import (
    BODY_STYLE,
    BODY_TEXT_STYLE,
    BULLET_STYLE,
    HEADING_STYLES,
    MATH_BLOCK_STYLE,
    NUMBER_STYLE,
    QUOTE_STYLE,
    TABLE_BULLET_STYLE,
    TABLE_CODE_BLOCK_STYLE,
    TABLE_CODE_CHARACTER_STYLE,
    TABLE_FIELD_LABEL_STYLE,
    TABLE_HEADING_STYLE,
    TABLE_MATH_BLOCK_STYLE,
    TABLE_NUMBER_STYLE,
    TABLE_STYLE,
    TABLE_TEXT_STYLE,
    TEST_CASE_TABLE_STYLE,
    TEST_CASE_TITLE_STYLE,
)
from .template import TemplateConfig

CN_OFFICIAL_TITLE_STYLE = "CN Official Title"
CN_OFFICIAL_ISSUER_STYLE = "CN Official Issuing Authority"
CN_OFFICIAL_NUMBER_STYLE = "CN Official Document Number"
CN_OFFICIAL_RECIPIENT_STYLE = "CN Official Recipient"
CN_OFFICIAL_SIGNATURE_STYLE = "CN Official Signature"
CN_OFFICIAL_IMPRINT_STYLE = "CN Official Imprint"
CN_OFFICIAL_RED_LINE_STYLE = "CN Official Red Separator"
CN_OFFICIAL_PAGE_NUMBER_STYLE = "CN Official Page Number"


@dataclass(frozen=True, slots=True)
class TemplatePreset:
    name: str
    description: str
    config_factory: Callable[[], TemplateConfig]
    configure: Callable[[object, TemplateConfig], None]


def _standard_config() -> TemplateConfig:
    return TemplateConfig()


def _cn_official_config() -> TemplateConfig:
    return TemplateConfig(
        body_font="仿宋_GB2312",
        heading_font="方正小标宋简体",
        code_font="Consolas",
        body_size_pt=14,
        page_width_cm=21.0,
        page_height_cm=29.7,
        page_margin_cm=2.54,
        accent_color="000000",
    )


def _no_extra_configuration(document, config: TemplateConfig) -> None:
    del document, config


def _configure_body_style(
    style,
    *,
    font: str,
    size: float = 14,
    first_line_indent: bool = False,
) -> None:
    configure_run_style(style, font=font, size=size, bold=False, color="000000")
    paragraph = style.paragraph_format
    paragraph.first_line_indent = Pt(size * 2) if first_line_indent else Pt(0)
    paragraph.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.line_spacing = Pt(28.95)
    paragraph.space_before = Pt(0)
    paragraph.space_after = Pt(0)


def _configure_table_text_style(style, *, font: str, bold: bool = False) -> None:
    configure_run_style(style, font=font, size=12, bold=bold, color="000000")
    paragraph = style.paragraph_format
    paragraph.first_line_indent = Pt(0)
    paragraph.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.line_spacing = 1.0
    paragraph.space_before = Pt(0)
    paragraph.space_after = Pt(0)


def _configure_heading_style(
    style,
    *,
    font: str,
    size: float,
    centered: bool = False,
    first_line_indent: bool = True,
) -> None:
    configure_run_style(style, font=font, size=size, bold=False, color="000000")
    paragraph = style.paragraph_format
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if centered else WD_ALIGN_PARAGRAPH.LEFT
    paragraph.first_line_indent = Pt(size * 2) if first_line_indent else Pt(0)
    paragraph.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    paragraph.line_spacing = Pt(28.95 if size <= 16 else 32)
    paragraph.space_before = Pt(0)
    paragraph.space_after = Pt(0)
    paragraph.keep_with_next = True


def _set_red_separator(style) -> None:
    p_pr = style._element.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        p_pr.append(borders)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "FF0000")
    borders.append(bottom)


def _append_page_field(paragraph) -> None:
    paragraph.add_run("— ")
    append_word_field(paragraph, "PAGE", display="1")
    paragraph.add_run(" —")


def _configure_page_number(paragraph, *, even: bool) -> None:
    paragraph.clear()
    paragraph.style = CN_OFFICIAL_PAGE_NUMBER_STYLE
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT if even else WD_ALIGN_PARAGRAPH.RIGHT
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.left_indent = Pt(16) if even else Pt(0)
    paragraph.paragraph_format.right_indent = Pt(0) if even else Pt(16)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    _append_page_field(paragraph)


def _configure_cn_official(document, config: TemplateConfig) -> None:
    styles = document.styles
    body = styles[BODY_STYLE]
    _configure_body_style(body, font=config.body_font, size=14)
    _configure_body_style(
        styles[BODY_TEXT_STYLE],
        font=config.body_font,
        size=14,
        first_line_indent=True,
    )

    title = styles[HEADING_STYLES[1]]
    _configure_heading_style(
        title,
        font=config.heading_font,
        size=22,
        centered=True,
        first_line_indent=False,
    )
    _configure_heading_style(styles[HEADING_STYLES[2]], font="黑体", size=16)
    _configure_heading_style(styles[HEADING_STYLES[3]], font="楷体_GB2312", size=16)
    for level in range(4, 7):
        _configure_heading_style(styles[HEADING_STYLES[level]], font=config.body_font, size=16)

    for name in (BULLET_STYLE, NUMBER_STYLE, QUOTE_STYLE):
        _configure_body_style(styles[name], font=config.body_font, size=14)
    styles[QUOTE_STYLE].paragraph_format.left_indent = Pt(28)
    _configure_body_style(styles[MATH_BLOCK_STYLE], font=config.body_font, size=14)
    styles[MATH_BLOCK_STYLE].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    styles[MATH_BLOCK_STYLE].paragraph_format.first_line_indent = Pt(0)
    styles[MATH_BLOCK_STYLE].paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    styles[MATH_BLOCK_STYLE].paragraph_format.line_spacing = 1.0

    for name in (TABLE_STYLE, TEST_CASE_TABLE_STYLE):
        configure_run_style(
            styles[name], font=config.body_font, size=12, bold=False, color="000000"
        )
    for name in (
        TABLE_TEXT_STYLE,
        TABLE_BULLET_STYLE,
        TABLE_NUMBER_STYLE,
        TABLE_MATH_BLOCK_STYLE,
    ):
        _configure_table_text_style(styles[name], font=config.body_font)
    styles[TABLE_MATH_BLOCK_STYLE].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _configure_table_text_style(styles[TABLE_CODE_BLOCK_STYLE], font=config.code_font)
    configure_run_style(
        styles[TABLE_CODE_CHARACTER_STYLE],
        font=config.code_font,
        size=12,
        bold=False,
        color="000000",
    )
    _configure_table_text_style(styles[TABLE_HEADING_STYLE], font="黑体")
    styles[TABLE_HEADING_STYLE].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _configure_table_text_style(styles[TABLE_FIELD_LABEL_STYLE], font="黑体")
    styles[TABLE_FIELD_LABEL_STYLE].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _configure_table_text_style(styles[TEST_CASE_TITLE_STYLE], font="黑体", bold=True)
    styles[TEST_CASE_TITLE_STYLE].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER

    aliases = {
        CN_OFFICIAL_TITLE_STYLE: (config.heading_font, 22, False, "000000"),
        CN_OFFICIAL_ISSUER_STYLE: (config.heading_font, 36, False, "FF0000"),
        CN_OFFICIAL_NUMBER_STYLE: (config.body_font, 16, False, "000000"),
        CN_OFFICIAL_RECIPIENT_STYLE: (config.body_font, 16, False, "000000"),
        CN_OFFICIAL_SIGNATURE_STYLE: (config.body_font, 16, False, "000000"),
        CN_OFFICIAL_IMPRINT_STYLE: (config.body_font, 14, False, "000000"),
        CN_OFFICIAL_RED_LINE_STYLE: (config.body_font, 1, False, "FF0000"),
        CN_OFFICIAL_PAGE_NUMBER_STYLE: ("宋体", 14, False, "000000"),
    }
    for name, (font, size, bold, color) in aliases.items():
        style = ensure_style(styles, name, WD_STYLE_TYPE.PARAGRAPH, BODY_STYLE)
        configure_run_style(style, font=font, size=size, bold=bold, color=color)
        style.paragraph_format.first_line_indent = Pt(0)
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)

    styles[CN_OFFICIAL_TITLE_STYLE].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    styles[CN_OFFICIAL_ISSUER_STYLE].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_red_separator(styles[CN_OFFICIAL_RED_LINE_STYLE])

    document.settings.odd_and_even_pages_header_footer = True
    for section in document.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(3.7)
        section.bottom_margin = Cm(3.5)
        section.left_margin = Cm(2.8)
        section.right_margin = Cm(2.6)
        section.footer_distance = Cm(2.6)
        section.footer.is_linked_to_previous = False
        section.even_page_footer.is_linked_to_previous = False
        _configure_page_number(section.footer.paragraphs[0], even=False)
        _configure_page_number(section.even_page_footer.paragraphs[0], even=True)

    request_field_update(document)
    document.core_properties.subject = (
        "GB/T 9704-2012-inspired reference preset; project-specific review required"
    )


_PRESETS = {
    "standard": TemplatePreset(
        name="standard",
        description="General A4 document with neutral reusable styles.",
        config_factory=_standard_config,
        configure=_no_extra_configuration,
    ),
    "cn-official": TemplatePreset(
        name="cn-official",
        description=(
            "Chinese Party/government official-document reference based on directly implementable "
            "GB/T 9704-2012 layout conventions."
        ),
        config_factory=_cn_official_config,
        configure=_configure_cn_official,
    ),
}


def available_template_presets() -> tuple[str, ...]:
    return tuple(_PRESETS)


def get_template_preset(name: str) -> TemplatePreset:
    try:
        return _PRESETS[name]
    except KeyError as error:
        raise ValueError(f"unknown template preset: {name}") from error


def describe_template_presets() -> tuple[tuple[str, str], ...]:
    return tuple((preset.name, preset.description) for preset in _PRESETS.values())
