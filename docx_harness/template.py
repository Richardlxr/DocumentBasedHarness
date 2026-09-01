from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.shared import Cm, Pt

from .renderers.ooxml import configure_run_style, ensure_style
from .renderers.styles import (
    BODY_STYLE,
    BODY_TEXT_STYLE,
    BULLET_STYLE,
    CODE_BLOCK_STYLE,
    CODE_CHARACTER_STYLE,
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


@dataclass(frozen=True, slots=True)
class TemplateConfig:
    body_font: str = "等线"
    heading_font: str = "等线"
    code_font: str = "Consolas"
    body_size_pt: float = 10.5
    inline_code_size_pt: float | None = None
    code_block_size_pt: float | None = None
    page_width_cm: float = 21.0
    page_height_cm: float = 29.7
    page_margin_cm: float = 2.54
    accent_color: str = "1F4E78"


def configure_document(document, config: TemplateConfig | None = None) -> None:
    config = config or TemplateConfig()
    # Code sizes follow the configured body size by default, while remaining
    # independently overridable by a project or custom preset.
    inline_code_size_pt = (
        config.body_size_pt if config.inline_code_size_pt is None else config.inline_code_size_pt
    )
    code_block_size_pt = (
        max(1, config.body_size_pt - 1)
        if config.code_block_size_pt is None
        else config.code_block_size_pt
    )
    for section in document.sections:
        section.page_width = Cm(config.page_width_cm)
        section.page_height = Cm(config.page_height_cm)
        section.top_margin = Cm(config.page_margin_cm)
        section.bottom_margin = Cm(config.page_margin_cm)
        section.left_margin = Cm(config.page_margin_cm)
        section.right_margin = Cm(config.page_margin_cm)

    styles = document.styles
    body = ensure_style(styles, BODY_STYLE, WD_STYLE_TYPE.PARAGRAPH, "Normal")
    configure_run_style(body, font=config.body_font, size=config.body_size_pt)
    body.paragraph_format.space_after = Pt(6)
    body.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    body.paragraph_format.line_spacing = 1.25

    body_text = ensure_style(styles, BODY_TEXT_STYLE, WD_STYLE_TYPE.PARAGRAPH, BODY_STYLE)
    configure_run_style(body_text, font=config.body_font, size=config.body_size_pt)
    body_text.paragraph_format.space_after = Pt(6)
    body_text.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    body_text.paragraph_format.line_spacing = 1.25

    for level, name in HEADING_STYLES.items():
        heading = ensure_style(styles, name, WD_STYLE_TYPE.PARAGRAPH, f"Heading {level}")
        configure_run_style(
            heading,
            font=config.heading_font,
            size=max(11, 18 - level * 1.5),
            bold=True,
            color=config.accent_color,
        )
        heading.paragraph_format.keep_with_next = True
        heading.paragraph_format.space_before = Pt(max(6, 14 - level))
        heading.paragraph_format.space_after = Pt(4)

    quote = ensure_style(styles, QUOTE_STYLE, WD_STYLE_TYPE.PARAGRAPH, "Quote")
    configure_run_style(quote, font=config.body_font, size=config.body_size_pt, color="44546A")
    quote.paragraph_format.left_indent = Cm(0.75)

    code_block = ensure_style(styles, CODE_BLOCK_STYLE, WD_STYLE_TYPE.PARAGRAPH, "Normal")
    configure_run_style(code_block, font=config.code_font, size=code_block_size_pt)
    code_block.paragraph_format.left_indent = Cm(0.5)
    code_block.paragraph_format.space_after = Pt(6)

    code_character = ensure_style(styles, CODE_CHARACTER_STYLE, WD_STYLE_TYPE.CHARACTER)
    configure_run_style(code_character, font=config.code_font, size=inline_code_size_pt)

    math_block = ensure_style(styles, MATH_BLOCK_STYLE, WD_STYLE_TYPE.PARAGRAPH, BODY_STYLE)
    configure_run_style(math_block, font=config.body_font, size=config.body_size_pt)
    math_block.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    math_block.paragraph_format.first_line_indent = Pt(0)
    math_block.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    math_block.paragraph_format.line_spacing = 1.0

    bullet = ensure_style(styles, BULLET_STYLE, WD_STYLE_TYPE.PARAGRAPH, "List Bullet")
    configure_run_style(bullet, font=config.body_font, size=config.body_size_pt)
    number = ensure_style(styles, NUMBER_STYLE, WD_STYLE_TYPE.PARAGRAPH, "List Number")
    configure_run_style(number, font=config.body_font, size=config.body_size_pt)

    table = ensure_style(styles, TABLE_STYLE, WD_STYLE_TYPE.TABLE, "Table Grid")
    configure_run_style(table, font=config.body_font, size=9.5)
    test_table = ensure_style(styles, TEST_CASE_TABLE_STYLE, WD_STYLE_TYPE.TABLE, "Table Grid")
    configure_run_style(test_table, font=config.body_font, size=9.5)

    table_text = ensure_style(styles, TABLE_TEXT_STYLE, WD_STYLE_TYPE.PARAGRAPH, BODY_STYLE)
    configure_run_style(table_text, font=config.body_font, size=9.5)
    table_text.paragraph_format.first_line_indent = Pt(0)
    table_text.paragraph_format.space_before = Pt(0)
    table_text.paragraph_format.space_after = Pt(0)

    table_bullet = ensure_style(styles, TABLE_BULLET_STYLE, WD_STYLE_TYPE.PARAGRAPH, "List Bullet")
    configure_run_style(table_bullet, font=config.body_font, size=9.5)
    table_number = ensure_style(styles, TABLE_NUMBER_STYLE, WD_STYLE_TYPE.PARAGRAPH, "List Number")
    configure_run_style(table_number, font=config.body_font, size=9.5)

    table_code_block = ensure_style(
        styles, TABLE_CODE_BLOCK_STYLE, WD_STYLE_TYPE.PARAGRAPH, TABLE_TEXT_STYLE
    )
    configure_run_style(table_code_block, font=config.code_font, size=9.5)
    table_code_character = ensure_style(styles, TABLE_CODE_CHARACTER_STYLE, WD_STYLE_TYPE.CHARACTER)
    configure_run_style(table_code_character, font=config.code_font, size=9.5)

    table_math_block = ensure_style(
        styles, TABLE_MATH_BLOCK_STYLE, WD_STYLE_TYPE.PARAGRAPH, TABLE_TEXT_STYLE
    )
    configure_run_style(table_math_block, font=config.body_font, size=9.5)
    table_math_block.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    table_math_block.paragraph_format.first_line_indent = Pt(0)
    table_math_block.paragraph_format.space_before = Pt(0)
    table_math_block.paragraph_format.space_after = Pt(0)

    table_heading = ensure_style(
        styles, TABLE_HEADING_STYLE, WD_STYLE_TYPE.PARAGRAPH, TABLE_TEXT_STYLE
    )
    configure_run_style(table_heading, font=config.body_font, size=9.5, bold=True)
    table_heading.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    table_heading.paragraph_format.space_after = Pt(0)

    table_field_label = ensure_style(
        styles, TABLE_FIELD_LABEL_STYLE, WD_STYLE_TYPE.PARAGRAPH, TABLE_TEXT_STYLE
    )
    configure_run_style(table_field_label, font=config.body_font, size=9.5, bold=True)
    table_field_label.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    table_field_label.paragraph_format.space_after = Pt(0)

    test_title = ensure_style(
        styles, TEST_CASE_TITLE_STYLE, WD_STYLE_TYPE.PARAGRAPH, TABLE_TEXT_STYLE
    )
    configure_run_style(test_title, font=config.heading_font, size=11, bold=True, color="000000")
    test_title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    test_title.paragraph_format.space_after = Pt(0)

    document.core_properties.creator = "docx-harness"
    document.core_properties.subject = "Generated DOCX template"


def create_template(
    output: str | Path,
    config: TemplateConfig | None = None,
    *,
    preset: str = "standard",
) -> Path:
    from .presets import get_template_preset

    definition = get_template_preset(preset)
    config = config or definition.config_factory()
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    configure_document(document, config)
    definition.configure(document, config)
    document.save(destination)
    return destination
