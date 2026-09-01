"""Deck renderer: projection/deck_plan.yaml → build/deck.pptx.

Pure code — no model in the loop at render time. The deck plan is
content-complete; this renderer realizes it with a deliberately simple, light
theme. Visual upgrades (designed templates, a measured layout engine, the
constrained animation vocabulary, an HTML surface) must happen renderer-side
and never leak visual fields back into the narrative.

Consumed semantic slots: ``brief.language`` (font selection) and page
``visual.asset_refs`` (path string or ``{ref, caption, evidence}``; the caption
renders under the image). Ignored at this tier: ``emphasis``, ``reveal``,
``deck.style`` (passed through for richer renderers).
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

# Hard constraints like "不要黑底" are enforced here: the tier-1 theme is always
# light. validate_hard_constraints asserts this flag.
THEME_IS_LIGHT = True

_SLIDE_W = Inches(13.333)
_SLIDE_H = Inches(7.5)
_TEXT = RGBColor(0x1F, 0x29, 0x37)
_MUTED = RGBColor(0x6B, 0x72, 0x80)
_ACCENT = RGBColor(0x25, 0x63, 0xEB)


def _font_for(language: str) -> str:
    return "Microsoft YaHei" if language.lower().startswith("zh") else "Calibri"


def _asset_entries(page: dict) -> list[dict]:
    return [
        item if isinstance(item, dict) else {"ref": item}
        for item in (page.get("visual") or {}).get("asset_refs", [])
    ]


def render_deck(plan: dict, run_root: Path, output: Path, *, language: str = "en") -> Path:
    font = _font_for(language)
    prs = Presentation()
    prs.slide_width = _SLIDE_W
    prs.slide_height = _SLIDE_H

    for page in plan["deck"]["pages"]:
        role = page.get("page_role", "content")
        if role == "cover":
            _render_cover(prs, page, font)
        elif role in ("agenda", "section_divider", "closing"):
            _render_banner(prs, page, font)
        else:
            _render_content(prs, page, run_root, font)

    output.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output)
    return output


def _blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _textbox(slide, left, top, width, height) -> object:
    box = slide.shapes.add_textbox(left, top, width, height)
    box.text_frame.word_wrap = True
    return box


def _set(paragraph, text: str, size: int, *, bold: bool = False, font="Calibri") -> None:
    paragraph.text = text
    for run in paragraph.runs:
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = _TEXT
        run.font.name = font


def _muted(paragraph, text: str, size: int, font: str) -> None:
    paragraph.text = text
    for run in paragraph.runs:
        run.font.size = Pt(size)
        run.font.color.rgb = _MUTED
        run.font.name = font


def _add_notes(slide, page: dict) -> None:
    notes = page.get("notes")
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def _render_cover(prs: Presentation, page: dict, font: str) -> None:
    slide = _blank(prs)
    box = _textbox(slide, Inches(1.0), Inches(2.4), Inches(11.3), Inches(2.4))
    _set(box.text_frame.paragraphs[0], page["title"], 40, bold=True, font=font)
    points = page.get("support_points", [])
    if points:
        _muted(box.text_frame.add_paragraph(), "  ·  ".join(points), 18, font)
    _add_notes(slide, page)


def _render_banner(prs: Presentation, page: dict, font: str) -> None:
    slide = _blank(prs)
    accent = slide.shapes.add_shape(
        1, Inches(0.9), Inches(2.35), Inches(1.2), Pt(6)  # MSO_SHAPE.RECTANGLE
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = _ACCENT
    accent.line.fill.background()
    box = _textbox(slide, Inches(1.0), Inches(2.7), Inches(11.3), Inches(2.2))
    _set(box.text_frame.paragraphs[0], page["title"], 32, bold=True, font=font)
    for point in page.get("support_points", []):
        paragraph = box.text_frame.add_paragraph()
        paragraph.space_before = Pt(10)
        _muted(paragraph, point, 18, font)
    _add_notes(slide, page)


def _render_content(prs: Presentation, page: dict, run_root: Path, font: str) -> None:
    slide = _blank(prs)
    title = _textbox(slide, Inches(0.9), Inches(0.55), Inches(11.5), Inches(1.5))
    _set(title.text_frame.paragraphs[0], page["title"], 28, bold=True, font=font)

    body_width = Inches(11.5)
    for entry in _asset_entries(page):
        image = run_root / entry["ref"]
        if not image.is_file():
            continue
        slide.shapes.add_picture(str(image), Inches(6.4), Inches(2.2), width=Inches(6.2))
        body_width = Inches(5.2)
        caption = entry.get("caption")
        if caption:
            box = _textbox(slide, Inches(6.4), Inches(6.55), Inches(6.2), Inches(0.5))
            paragraph = box.text_frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.CENTER
            _muted(paragraph, caption, 12, font)
        break  # tier-1 renders one image per page

    points = page.get("support_points", [])
    if points:
        body = _textbox(slide, Inches(0.9), Inches(2.3), body_width, Inches(4.4))
        first = True
        for point in points:
            paragraph = body.text_frame.paragraphs[0] if first else body.text_frame.add_paragraph()
            first = False
            paragraph.space_after = Pt(10)
            _set(paragraph, "• " + point, 18, font=font)
    _add_notes(slide, page)
