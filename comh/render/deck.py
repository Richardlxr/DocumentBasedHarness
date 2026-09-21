"""Deck renderer: projection/deck_plan.yaml → build/deck.pptx.

Pure code — no model in the loop at render time. Content pages compose four
optional blocks, so a page fills its canvas with substance instead of three
short bullets floating in white space:

- **Elaborated points** — ``{point, detail}`` support points render as a bold
  lead-in plus a lighter explanation line; plain strings stay plain bullets.
- **Metric cards** — ``metric_cards`` render big-number tiles whose values are
  pulled from the evidence store at render time (``value_from``), so card
  numbers cannot drift.
- **Native charts** — ``visual.chart`` likewise plots evidence values.
- **Callout** — a bottom "so what" band reinforcing the page's message.

Layout is measured: real glyph metrics drive wrapping, font fitting, and
vertical distribution of leftover space; anything that cannot fit becomes a
layout finding in the render report instead of silent overflow.

``emphasis``/``reveal`` remain read-but-unconsumed semantic slots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from ..artifacts import Finding
from .metrics import FIXED_TEXT_SIZES, fit_box, wrap_lines
from .ooxml import set_east_asian_font, set_shape_translucent_fill
from .scrim import solve_scrim
from .theme import RenderTheme, render_theme

_CHART_TYPES = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
}
_TRANSITIONS: dict[str, dict] = {
    "fade": {},
    "push": {"dir": "l"},
    "wipe": {"dir": "r"},
    "cut": {},
}
_ROUNDED = 5  # MSO_SHAPE.ROUNDED_RECTANGLE

_SLIDE_W = Inches(13.333)
_SLIDE_H = Inches(7.5)
_LINE_SPACING = 1.25
_PT_PER_IN = 72.0
_MARGIN_X = 0.9
_BODY_W = 11.53
_BODY_TOP = 1.85
_BODY_BOTTOM = 5.95


@dataclass(slots=True)
class RenderResult:
    output: Path
    theme: str
    transition: str | None
    findings: list[Finding] = field(default_factory=list)
    # page_id -> {element address -> shape_id}; the animation pass consumes it
    shape_map: dict[str, dict[str, int]] = field(default_factory=dict)
    # page_id -> slide index (for the animation pass)
    slide_index: dict[str, int] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


def render_deck(
    plan: dict,
    run_root: Path,
    output: Path,
    *,
    language: str = "en",
    evidence: dict | None = None,
    allow_dark: bool = True,
    _appearance_themes: list[RenderTheme] | None = None,
) -> RenderResult:
    if "pptx_style" in plan.get("deck", {}).get("style", {}) and _appearance_themes is None:
        from ..pptx_style.compiler import compile_deck

        return compile_deck(
            plan, run_root, output, language=language, evidence=evidence, allow_dark=allow_dark
        )
    theme = (
        _appearance_themes[0]
        if _appearance_themes
        else render_theme(
            plan.get("deck", {}).get("style"), language, allow_dark=allow_dark, run_root=run_root
        )
    )
    result = RenderResult(output=output, theme=theme.theme.name, transition=None)
    if theme.fallback_reason:
        result.findings.append(
            Finding("deck_plan", "theme", "warn", "fail", theme.fallback_reason, "deck_plan")
        )
    if theme.forced_light:
        result.findings.append(
            Finding(
                "deck_plan",
                "theme",
                "warn",
                "fail",
                "brief forbids a dark background; dark template forced to light",
                "deck_plan",
            )
        )

    prs = Presentation()
    prs.slide_width = _SLIDE_W
    prs.slide_height = _SLIDE_H
    total = len(plan["deck"]["pages"])

    for slide_number, page in enumerate(plan["deck"]["pages"]):
        from ..presentation_profile import presentation_structure_errors

        if errors := presentation_structure_errors(page):
            raise ValueError(f"page {page.get('id')}: {'; '.join(errors)}")
        if _appearance_themes:
            theme = _appearance_themes[slide_number]
        role = page.get("page_role", "content")
        page_id = page.get("id", f"P{slide_number + 1:02d}")
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _paint_background(slide, theme.theme.background)
        _apply_slide_background(slide, page, run_root, theme, result)
        shapes: dict[str, list[int]] = {}
        if role == "cover":
            _render_cover(slide, page, theme, result, shapes)
        elif role == "agenda":
            _render_agenda(slide, page, theme, result, shapes)
        elif role in ("section_divider", "closing"):
            _render_banner(slide, page, theme, result, shapes)
        elif role == "hero_split":
            _render_hero_split(slide, page, run_root, theme, result, evidence, shapes)
        elif role == "fullscreen_backdrop":
            _render_fullscreen_backdrop(slide, page, run_root, theme, result, evidence, shapes)
        elif role == "timeline":
            _render_timeline(slide, page, theme, result, evidence, shapes)
        elif role == "versus":
            _render_versus(slide, page, theme, result, evidence, shapes)
        else:
            _render_content(slide, page, run_root, theme, result, evidence, shapes)
        result.shape_map[page_id] = shapes
        result.slide_index[page_id] = slide_number
        if role != "cover" and not _appearance_themes:
            _add_footer(slide, page_id, slide_number, total, plan, theme)
        _add_notes(slide, page)

    _check_geometry(prs, result)
    from .editability import audit_editability

    result.metadata["editability"], edit_findings = audit_editability(
        prs, [p["id"] for p in plan["deck"]["pages"]]
    )
    result.findings.extend(edit_findings)
    _apply_transition(prs, plan, result)
    _apply_animations(prs, plan, result)
    output.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output)
    return result


# -- shared helpers ---------------------------------------------------------


def _apply_slide_background(
    slide, page: dict, run_root: Path, theme: RenderTheme, result: RenderResult
) -> None:
    bg_spec = (page.get("visual") or {}).get("background") or page.get("background")
    if not bg_spec or not isinstance(bg_spec, dict) or not bg_spec.get("asset"):
        return
    asset_path = run_root / str(bg_spec["asset"])
    if not asset_path.is_file():
        result.findings.append(
            Finding(
                "deck_plan",
                "asset",
                "warn",
                "fail",
                f"page {page.get('id', '')} background image not found: {bg_spec['asset']}",
                "deck_plan",
            )
        )
        return

    scrim_res = solve_scrim(
        asset_path,
        theme.theme.text,
        theme.theme.background,
        base_alpha=float(bg_spec.get("opacity") or 0.0),
    )
    if not scrim_res.passed:
        result.findings.append(
            Finding(
                "deck_plan",
                "background-contrast",
                "error",
                "fail",
                f"page {page.get('id', '')}: background image contrast against theme "
                "text is below 4.5:1 even at alpha=0.90",
                "deck_plan",
            )
        )

    overlay_type = str(bg_spec.get("overlay", "theme")).lower()
    if overlay_type == "frosted-glass":
        result.findings.append(
            Finding(
                "deck_plan",
                "theme-overlay",
                "info",
                "pass",
                f"page {page.get('id', '')}: 'frosted-glass' overlay rendered as solid "
                "translucent scrim in PPTX",
                "deck_plan",
            )
        )

    pic = slide.shapes.add_picture(str(asset_path), Inches(0), Inches(0), _SLIDE_W, _SLIDE_H)
    pic.name = "background_image"

    if scrim_res.alpha > 0.001:
        scrim_shape = slide.shapes.add_shape(1, Inches(0), Inches(0), _SLIDE_W, _SLIDE_H)
        scrim_shape.name = "background_scrim"
        set_shape_translucent_fill(scrim_shape, theme.theme.background, scrim_res.alpha)
        scrim_shape.line.fill.background()


def _paint_background(slide, color) -> None:
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _textbox(slide, left, top, width, height) -> object:
    box = slide.shapes.add_textbox(left, top, width, height)
    box.text_frame.word_wrap = True
    return box


def _set(
    paragraph, text: str, *, size: int, font: str, color, bold: bool = False, italic: bool = False
) -> None:
    paragraph.text = text
    for run in paragraph.runs:
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
        run.font.name = font
        if FIXED_TEXT_SIZES.get():
            set_east_asian_font(run, font)


def _add_notes(slide, page: dict) -> None:
    notes = page.get("notes")
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def _fit_or_report(
    text: str,
    *,
    page_id: str,
    element: str,
    width_in: float,
    height_in: float,
    max_size: int,
    min_size: int,
    family: str,
    findings: list[Finding],
) -> int:
    fit = fit_box(
        text,
        width_pt=width_in * _PT_PER_IN,
        height_pt=height_in * _PT_PER_IN,
        max_size=max_size,
        min_size=max_size if FIXED_TEXT_SIZES.get() else min_size,
        family=family,
    )
    if fit.overflows:
        findings.append(
            Finding(
                "deck_plan",
                "layout",
                "warn",
                "fail",
                f"page {page_id} {element} does not fit at minimum size "
                f"{fit.font_size}pt ({fit.lines} wrapped lines) — split or demote content",
                "deck_plan",
            )
        )
    return fit.font_size


def _point_parts(entry) -> tuple[str, str | None]:
    if isinstance(entry, dict):
        return str(entry.get("point", "")), entry.get("detail")
    return str(entry), None


def _evidence_number(items: dict, ref: str, page_id: str, what: str) -> tuple[float, str | None]:
    item = items.get(ref)
    if item is None:
        raise RuntimeError(
            f"page {page_id} {what} references evidence '{ref}' which does not exist; "
            f"run `comh validate all`"
        )
    value = item.get("value") or {}
    number = value.get("number")
    if number is None:
        raise RuntimeError(
            f"page {page_id} {what}: evidence '{ref}' has no value.number; "
            f"cards and charts plot structured data only"
        )
    return float(number), value.get("unit")


def _fmt(number: float) -> str:
    return f"{number:g}"


def _versus_labels(page: dict, result) -> tuple[str, str]:
    """Versus column labels come from visual.columns: [left, right] — the
    renderer must not invent content, so a missing spec degrades to bare A/B
    with a warn pointing at the field."""
    columns = (page.get("visual") or {}).get("columns")
    if isinstance(columns, list) and len(columns) == 2 and all(str(c).strip() for c in columns):
        return str(columns[0]).strip(), str(columns[1]).strip()
    result.findings.append(
        Finding(
            "deck_plan",
            "layout",
            "warn",
            "pass",
            f"page {page.get('id', '')}: versus needs visual.columns: [left, right] "
            "column labels; rendering bare A/B for now",
            "deck_plan",
        )
    )
    return "A", "B"


# -- page kinds --------------------------------------------------------------


def _render_cover(
    slide, page: dict, theme: RenderTheme, result: RenderResult, shapes: dict
) -> None:
    """Editorial cover: left accent band, display-scale left-aligned title,
    accent rule, muted meta — typography is the hero."""
    t = theme.theme
    band = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.16), Inches(7.5))
    band.name = "decor"
    band.fill.solid()
    band.fill.fore_color.rgb = t.accent
    band.line.fill.background()
    shapes["title"] = []

    points = page.get("support_points", [])
    joined = "  ·  ".join(p[0] for p in (_point_parts(x) for x in points))
    subtitle_lines = len(wrap_lines(joined, t.body_size, 10.8 * _PT_PER_IN, theme.body_font))
    size = _fit_or_report(
        page["title"],
        page_id=page["id"],
        element="title",
        width_in=10.8,
        height_in=2.6 - 0.4 * subtitle_lines,
        max_size=t.cover_title_size,
        min_size=30,
        family=theme.title_font,
        findings=result.findings,
    )
    box = _textbox(slide, Inches(0.9), Inches(2.15), Inches(10.8), Inches(2.6))
    _set(
        box.text_frame.paragraphs[0],
        page["title"],
        size=size,
        font=theme.title_font,
        color=t.title_color,
        bold=t.title_bold,
        italic=t.title_italic,
    )
    if joined:
        paragraph = box.text_frame.add_paragraph()
        paragraph.space_before = Pt(14)
        _set(paragraph, joined, size=t.body_size, font=theme.body_font, color=t.muted)
    rule = slide.shapes.add_shape(1, Inches(0.9), Inches(5.15), Inches(1.4), Pt(4))
    rule.name = "decor"
    rule.fill.solid()
    rule.fill.fore_color.rgb = t.accent
    rule.line.fill.background()


def _render_agenda(
    slide, page: dict, theme: RenderTheme, result: RenderResult, shapes: dict
) -> None:
    """Editorial agenda: hairline-separated rows of accent index numbers and
    items, spread across the body zone."""
    t = theme.theme
    shapes["title"] = []
    title = _textbox(slide, Inches(_MARGIN_X), Inches(0.55), Inches(_BODY_W), Inches(1.0))
    _set(
        title.text_frame.paragraphs[0],
        page["title"],
        size=t.banner_title_size,
        font=theme.title_font,
        color=t.title_color,
        bold=t.title_bold,
        italic=t.title_italic,
    )

    entries = page.get("support_points", [])
    top, bottom = 2.0, 6.7
    n = max(len(entries), 1)
    row_h = (bottom - top) / n
    if row_h < 0.55:
        result.findings.append(
            Finding(
                "deck_plan",
                "layout",
                "warn",
                "fail",
                f"page {page.get('id', '?')}: {len(entries)} agenda rows leave only "
                f"{row_h:.2f}in each (needs ~0.55in) — merge or split into two pages",
                "deck_plan",
            )
        )
    for index, entry in enumerate(entries):
        point, _detail = _point_parts(entry)
        y = top + index * row_h
        number = _textbox(slide, Inches(_MARGIN_X), Inches(y + 0.1), Inches(0.95), Inches(0.55))
        _set(
            number.text_frame.paragraphs[0],
            f"{index + 1:02d}",
            size=t.index_number_size,
            font=theme.title_font,
            color=t.accent,
            bold=True,
        )
        item = _textbox(slide, Inches(1.95), Inches(y + 0.12), Inches(10.4), Inches(0.55))
        _set(
            item.text_frame.paragraphs[0],
            point,
            size=t.body_size + 2,
            font=theme.body_font,
            color=t.text,
        )
        shapes[f"support_points[{index}]"] = [item.shape_id]
        if index < n - 1:
            hair = slide.shapes.add_shape(
                1, Inches(_MARGIN_X), Inches(y + row_h - 0.07), Inches(_BODY_W), Pt(0.75)
            )
            hair.name = "decor"
            hair.fill.solid()
            hair.fill.fore_color.rgb = t.card_line
            hair.line.fill.background()
    shapes["support_points"] = [
        sid for i in range(len(entries)) for sid in shapes.get(f"support_points[{i}]", [])
    ]


def _render_banner(
    slide, page: dict, theme: RenderTheme, result: RenderResult, shapes: dict
) -> None:
    t = theme.theme
    accent = slide.shapes.add_shape(1, Inches(0.9), Inches(2.35), Inches(1.2), Pt(6))
    accent.name = "decor"
    accent.fill.solid()
    accent.fill.fore_color.rgb = t.accent
    accent.line.fill.background()
    points = page.get("support_points", [])
    body_lines = sum(
        len(wrap_lines(p, t.body_size, _BODY_W * _PT_PER_IN, theme.body_font))
        for p, _ in (_point_parts(x) for x in points)
    )
    size = _fit_or_report(
        page["title"],
        page_id=page["id"],
        element="title",
        width_in=_BODY_W,
        height_in=2.2 - 0.32 * body_lines,
        max_size=t.banner_title_size,
        min_size=24,
        family=theme.title_font,
        findings=result.findings,
    )
    box = _textbox(slide, Inches(1.0), Inches(2.7), Inches(_BODY_W), Inches(2.4))
    shapes["title"] = [box.shape_id]
    _set(
        box.text_frame.paragraphs[0],
        page["title"],
        size=size,
        font=theme.title_font,
        color=t.title_color,
        bold=t.title_bold,
        italic=t.title_italic,
    )
    for entry in points:
        point, _ = _point_parts(entry)
        paragraph = box.text_frame.add_paragraph()
        paragraph.text = point
        paragraph.space_before = Pt(10)
        _set(paragraph, point, size=t.body_size, font=theme.body_font, color=t.muted)


def _add_footer(
    slide, page_id: str, index: int, total: int, plan: dict, theme: RenderTheme
) -> None:
    """Page furniture: deck title bottom-left, NN / NN bottom-right."""
    t = theme.theme
    brand = _textbox(slide, Inches(_MARGIN_X), Inches(7.06), Inches(8.0), Inches(0.32))
    _set(
        brand.text_frame.paragraphs[0],
        plan.get("deck", {}).get("title", ""),
        size=t.footer_size,
        font=theme.body_font,
        color=t.muted,
    )
    number = _textbox(slide, Inches(11.0), Inches(7.06), Inches(1.43), Inches(0.32))
    paragraph = number.text_frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.RIGHT
    _set(
        paragraph,
        f"{index + 1:02d} / {total:02d}",
        size=t.footer_size,
        font=theme.body_font,
        color=t.muted,
    )


def _render_content(
    slide,
    page: dict,
    run_root: Path,
    theme: RenderTheme,
    result: RenderResult,
    evidence: dict | None,
    shapes: dict,
) -> None:
    t = theme.theme
    page_id = page["id"]
    visual = page.get("visual") or {}
    chart_spec = visual.get("chart")
    diagram_spec = visual.get("diagram")
    cards = page.get("metric_cards") or []
    arrangement = visual.get("arrangement", "split")

    title_top = 0.42
    kicker = str(page.get("kicker") or "")
    if kicker:
        kick = _textbox(slide, Inches(_MARGIN_X), Inches(0.42), Inches(_BODY_W), Inches(0.34))
        _set(
            kick.text_frame.paragraphs[0],
            kicker,
            size=t.kicker_size,
            font=theme.body_font,
            color=t.accent,
            bold=True,
        )
        title_top = 0.78
    size = _fit_or_report(
        page["title"],
        page_id=page_id,
        element="title",
        width_in=_BODY_W,
        height_in=1.15,
        max_size=t.content_title_size,
        min_size=20,
        family=theme.title_font,
        findings=result.findings,
    )
    title = _textbox(slide, Inches(_MARGIN_X), Inches(title_top), Inches(_BODY_W), Inches(1.1))
    shapes["title"] = [title.shape_id]
    _set(
        title.text_frame.paragraphs[0],
        page["title"],
        size=size,
        font=theme.title_font,
        color=t.title_color,
        bold=t.title_bold,
        italic=t.title_italic,
    )
    # full-width hairline with a short accent segment — editorial separation
    hair_y = title_top + 1.06
    hair = slide.shapes.add_shape(1, Inches(_MARGIN_X), Inches(hair_y), Inches(_BODY_W), Pt(0.75))
    hair.name = "decor"
    hair.fill.solid()
    hair.fill.fore_color.rgb = t.card_line
    hair.line.fill.background()
    underline = slide.shapes.add_shape(
        1, Inches(_MARGIN_X), Inches(hair_y) - Pt(1.5), Inches(0.7), Pt(3.5)
    )
    underline.name = "decor"
    underline.fill.solid()
    underline.fill.fore_color.rgb = t.accent
    underline.line.fill.background()

    # decorative furniture: top accent strip only. The former corner wash
    # (a filled 5.6in oval under the figure column) read as an occluding
    # disc against top-right content, so it was removed — decoration must
    # not visually cross the content zone.
    strip = slide.shapes.add_shape(1, Inches(0), Inches(0), _SLIDE_W, Pt(5))
    strip.name = "decor"
    strip.fill.solid()
    strip.fill.fore_color.rgb = t.accent
    strip.line.fill.background()

    content_top = _BODY_TOP if title_top < 0.5 else _BODY_TOP + 0.2
    # Reserve the conclusion band only when it exists. Otherwise the body can
    # use that space while staying clear of the footer (starts at 7.06in).
    content_bottom = _BODY_BOTTOM if page.get("callout") else 6.8
    if cards:
        _render_metric_cards(
            slide,
            cards,
            theme,
            result,
            evidence,
            page_id,
            shapes,
            content_top,
            run_root,
        )
        content_top += 1.8

    body_width = _BODY_W
    full_visual = arrangement == "full" or not page.get("support_points")
    vx, vw = (_MARGIN_X, _BODY_W) if full_visual else (6.55, 5.9)
    if visual.get("table") is not None:
        from .table import render_table

        frame = render_table(
            slide,
            visual["table"],
            evidence,
            page_id,
            theme,
            x=vx,
            y=content_top,
            w=vw,
            h=content_bottom - content_top,
        )
        shapes["visual"] = [frame.shape_id]
        body_width = 5.35
    elif chart_spec is not None:
        _add_chart(
            slide,
            page_id,
            chart_spec,
            t,
            result,
            evidence,
            x=vx,
            y=content_top,
            w=vw,
            h=content_bottom - content_top,
            shapes=shapes,
        )
        body_width = 5.35
    elif diagram_spec is not None:
        _add_diagram(
            slide,
            page_id,
            diagram_spec,
            theme,
            result,
            run_root,
            shapes,
            has_callout=bool(page.get("callout")),
            x=vx,
            y=content_top,
            w=vw,
            h=content_bottom - content_top,
        )
        body_width = 5.35
    else:
        _add_figure(
            slide,
            page,
            run_root,
            theme,
            result,
            shapes,
            x=vx,
            y=content_top,
            w=vw,
            h=content_bottom - content_top,
        )
        body_width = 5.35 if _has_figure(page, run_root) else _BODY_W

    points = page.get("support_points", [])
    if points and arrangement == "columns":
        _render_reading_columns(slide, page, theme, shapes, content_top, content_bottom)
    elif points:
        _render_points(
            slide,
            points,
            page_id=page_id,
            x=_MARGIN_X,
            y=content_top,
            width_in=body_width,
            height_in=content_bottom - content_top,
            theme=theme,
            findings=result.findings,
            shapes=shapes,
            run_root=run_root,
        )

    callout = page.get("callout")
    if callout:
        _render_callout(slide, callout, theme, result, page_id, shapes)


def _has_figure(page: dict, run_root: Path) -> bool:
    return any((run_root / entry["ref"]).is_file() for entry in _asset_entries(page))


def _asset_entries(page: dict) -> list[dict]:
    return [
        item if isinstance(item, dict) else {"ref": item}
        for item in (page.get("visual") or {}).get("asset_refs", [])
    ]


def _fit_image(slide, png: Path, *, x: float, y: float, max_w: float, max_h: float):
    """Place a PNG inside the (max_w, max_h) box, preserving aspect ratio."""
    from PIL import Image

    with Image.open(png) as image:
        width_px, height_px = image.size
    scale = min(max_w / max(width_px, 1), max_h / max(height_px, 1))
    picture = slide.shapes.add_picture(
        str(png), Inches(x), Inches(y), Inches(width_px * scale), Inches(height_px * scale)
    )
    return picture


def _add_diagram(
    slide,
    page_id: str,
    spec: dict,
    theme: RenderTheme,
    result: RenderResult,
    run_root: Path,
    shapes: dict,
    *,
    has_callout: bool = False,
    x: float = 6.55,
    y: float = _BODY_TOP,
    w: float = 5.9,
    h: float | None = None,
) -> None:
    from .native_diagram import diagram_scene, render_native_diagram

    height = h if h is not None else _visual_max_h(has_callout)
    caption = spec.get("caption")
    scene = diagram_scene(str(spec.get("mermaid", "")), theme.body_font)
    objects = render_native_diagram(
        slide, scene, theme, x=x, y=y, w=w, h=height - (0.5 if caption else 0)
    )
    shapes["visual"] = [obj.shape_id for obj in objects]
    if caption:
        box = _textbox(slide, Inches(x), Inches(y + height - 0.4), Inches(w), Inches(0.4))
        shapes["visual"].append(box.shape_id)
        paragraph = box.text_frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        _set(
            paragraph,
            caption,
            size=theme.theme.caption_size,
            font=theme.body_font,
            color=theme.theme.muted,
        )


def _render_reading_columns(slide, page, theme, shapes, top, bottom):
    """Aligned stages with local explanations; no repeated full-width scan."""
    points = page["support_points"]
    if not 2 <= len(points) <= 3:
        raise ValueError(f"page {page['id']}: reading columns require two or three points")
    gap = 0.45
    width = (_BODY_W - gap * (len(points) - 1)) / len(points)
    for i, entry in enumerate(points):
        point, detail = _point_parts(entry)
        x = _MARGIN_X + i * (width + gap)
        ids = []
        for text, y, height, size, bold in (
            (point, top, 0.85, theme.theme.body_size, True),
            (detail or "", top + 1.05, bottom - top - 1.05, theme.theme.body_size, False),
        ):
            fit = fit_box(
                text,
                width_pt=width * 72 - 8,
                height_pt=height * 72 - 8,
                max_size=size,
                min_size=size,
                family=theme.body_font,
            )
            if fit.overflows:
                raise ValueError(
                    f"page {page['id']}: reading column {i + 1} does not fit at {size}pt"
                )
            box = _textbox(slide, Inches(x), Inches(y), Inches(width), Inches(height))
            box.text_frame.margin_left = box.text_frame.margin_right = Pt(4)
            box.text_frame.margin_top = box.text_frame.margin_bottom = Pt(4)
            _set(
                box.text_frame.paragraphs[0],
                text,
                size=size,
                font=theme.body_font,
                color=theme.theme.accent if bold else theme.theme.text,
                bold=bold,
            )
            ids.append(box.shape_id)
        shapes[f"support_points[{i}]"] = ids


def _add_figure(
    slide,
    page: dict,
    run_root: Path,
    theme: RenderTheme,
    result: RenderResult,
    shapes: dict,
    *,
    x: float = 6.55,
    y: float = _BODY_TOP,
    w: float = 5.9,
    h: float | None = None,
) -> None:
    for entry in _asset_entries(page):
        image = run_root / entry["ref"]
        if not image.is_file():
            result.findings.append(
                Finding(
                    "deck_plan",
                    "asset",
                    "warn",
                    "fail",
                    f"page {page['id']} figure '{entry['ref']}' not found under the run root",
                    "deck_plan",
                )
            )
            continue
        max_h = h if h is not None else _visual_max_h(bool(page.get("callout")))
        if entry.get("caption"):
            max_h -= 0.5
        picture = _fit_image(slide, image, x=x, y=y, max_w=w, max_h=max_h)
        shapes["visual"] = [picture.shape_id]
        caption = entry.get("caption")
        if caption:
            bottom = (picture.top + picture.height) / _EMU_PER_IN
            box = _textbox(slide, Inches(x), Inches(bottom + 0.06), Inches(w), Inches(0.4))
            paragraph = box.text_frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.CENTER
            _set(
                paragraph,
                caption,
                size=theme.theme.caption_size,
                font=theme.body_font,
                color=theme.theme.muted,
            )
        return


def _visual_max_h(has_callout: bool) -> float:
    """Height cap for the right-column visual so it (plus its caption, which
    hugs the image bottom) stays clear of the callout band and the footer."""
    if has_callout:
        return 5.5 - _BODY_TOP  # image bottom ≤5.5, caption ends ≤5.96 < callout 6.1
    return 6.5 - _BODY_TOP  # image bottom ≤6.5, caption ends ≤6.96 < footer 7.06


def _render_metric_cards(
    slide,
    cards: list,
    theme: RenderTheme,
    result: RenderResult,
    evidence: dict | None,
    page_id: str,
    shapes: dict,
    top: float,
    run_root: Path,
) -> None:
    t = theme.theme
    items = {item["id"]: item for item in (evidence or {}).get("items", [])}
    if len(cards) > 4:
        result.findings.append(
            Finding(
                "deck_plan",
                "layout",
                "warn",
                "fail",
                f"page {page_id} has {len(cards)} metric cards (max 4); extras dropped",
                "deck_plan",
            )
        )
        cards = cards[:4]
    gap = 0.25
    width = (_BODY_W - gap * (len(cards) - 1)) / len(cards)
    for index, card in enumerate(cards):
        ref = str(card.get("value_from", ""))
        number, unit = _evidence_number(items, ref, page_id, "metric card")
        left = _MARGIN_X + index * (width + gap)
        shape = slide.shapes.add_shape(
            _ROUNDED, Inches(left), Inches(top), Inches(width), Inches(1.6)
        )
        shape.name = f"card:metric[{index}]"
        shapes[f"metric_cards[{index}]"] = [shape.shape_id]
        shape.fill.solid()
        shape.fill.fore_color.rgb = t.card_fill
        shape.line.color.rgb = t.card_line
        shape.line.width = Pt(1)
        shape.shadow.inherit = False
        card_icon = str(card.get("icon") or "")
        icon_placed = False
        if card_icon:
            from .icons import icon_exists, icon_png

            if icon_exists(card_icon):
                try:
                    png = icon_png(
                        card_icon,
                        color=t.accent,
                        background=t.card_fill,
                        px=48,
                        run_root=run_root,
                    )
                    icon_shape = slide.shapes.add_picture(
                        str(png),
                        Inches(left + width / 2 - 0.17),
                        Inches(top + 0.14),
                        height=Inches(0.34),
                    )
                    icon_shape.name = f"icon:{card_icon}"
                    icon_placed = True
                except RuntimeError as error:
                    result.findings.append(
                        Finding(
                            "deck_plan",
                            "icon",
                            "warn",
                            "fail",
                            f"page {page_id}: icon '{card_icon}' could not rasterize ({error})",
                            "deck_plan",
                        )
                    )
            else:
                result.findings.append(
                    Finding(
                        "deck_plan",
                        "icon",
                        "warn",
                        "fail",
                        f"page {page_id}: unknown icon '{card_icon}' (search "
                        f"assets/vendor/tabler-outline/icons-index.json)",
                        "deck_plan",
                    )
                )
        else:
            top_bar = slide.shapes.add_shape(
                1, Inches(left + 0.18), Inches(top + 0.16), Inches(0.5), Pt(3.5)
            )
            top_bar.name = "decor"
            top_bar.fill.solid()
            top_bar.fill.fore_color.rgb = t.accent
            top_bar.line.fill.background()
        value_text = _fmt(number) + (f" {unit}" if unit else "")
        value_top, value_height = (top + 0.52, 0.62) if icon_placed else (top + 0.34, 0.8)
        value_box = _textbox(
            slide, Inches(left), Inches(value_top), Inches(width), Inches(value_height)
        )
        _set(
            value_box.text_frame.paragraphs[0],
            value_text,
            size=t.card_value_size,
            font=theme.title_font,
            color=t.accent,
            bold=True,
        )
        value_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        label = str(card.get("label") or card.get("value_from", ""))
        label_box = _textbox(slide, Inches(left), Inches(top + 1.14), Inches(width), Inches(0.4))
        _set(
            label_box.text_frame.paragraphs[0],
            label,
            size=t.card_label_size,
            font=theme.body_font,
            color=t.muted,
        )
        label_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER


def _render_points(
    slide,
    points: list,
    *,
    page_id: str,
    x: float,
    y: float,
    width_in: float,
    height_in: float,
    theme: RenderTheme,
    findings: list[Finding],
    shapes: dict,
    run_root: Path | None = None,
) -> None:
    """Each point renders as a rounded card (point bold + detail muted inside),
    and the stack spreads evenly across the body zone — no floating text
    huddling at the top, no blank canyon under it."""
    t = theme.theme
    detail_size = t.detail_size
    pad_h, pad_v = 0.22, 0.15  # card padding, inches

    def card_height(entry, size: int) -> float:
        point, detail = _point_parts(entry)
        inner_w = (width_in - 2 * pad_h - 0.42) * _PT_PER_IN
        lines = len(wrap_lines(point, size, inner_w, theme.body_font)) * size * _LINE_SPACING
        if detail:
            detail_lines = wrap_lines(detail, detail_size, inner_w, theme.body_font)
            lines += len(detail_lines) * detail_size * 1.3
        return lines / _PT_PER_IN + 2 * pad_v

    max_size = t.body_size if width_in < _BODY_W else t.body_size_wide
    size = 14
    for candidate in [max_size] if FIXED_TEXT_SIZES.get() else range(max_size, 13, -1):
        if sum(card_height(e, candidate) for e in points) <= height_in:
            size = candidate
            break
    else:
        findings.append(
            Finding(
                "deck_plan",
                "layout",
                "warn",
                "fail",
                f"page {page_id} body points do not fit at "
                f"{max_size if FIXED_TEXT_SIZES.get() else 14}pt — demote content to "
                f"notes/appendix (see stages/deck.md)",
                "deck_plan",
            )
        )

    heights = [card_height(entry, size) for entry in points]
    gaps = max(1, len(points) - 1)
    gap = max(0.14, min((height_in - sum(heights)) / gaps, 0.42))

    cursor = y
    for index, entry in enumerate(points):
        point, detail = _point_parts(entry)
        card = slide.shapes.add_shape(
            _ROUNDED, Inches(x), Inches(cursor), Inches(width_in), Inches(heights[index])
        )
        card.name = f"card:point[{index}]"
        icon_name = str(entry.get("icon") or "") if isinstance(entry, dict) else ""
        icon_width = 0.0
        if icon_name and run_root is not None:
            from .icons import icon_exists, icon_png

            if icon_exists(icon_name):
                try:
                    png = icon_png(
                        icon_name,
                        color=t.accent,
                        background=t.card_fill,
                        px=44,
                        run_root=run_root,
                    )
                    picture = slide.shapes.add_picture(
                        str(png),
                        Inches(x + 0.22),
                        Inches(cursor + heights[index] / 2 - 0.14),
                        height=Inches(0.28),
                    )
                    picture.name = f"icon:{icon_name}"
                    icon_width = 0.42
                except RuntimeError as error:
                    findings.append(
                        Finding(
                            "deck_plan",
                            "icon",
                            "warn",
                            "fail",
                            f"page {page_id}: icon '{icon_name}' could not rasterize ({error})",
                            "deck_plan",
                        )
                    )
            else:
                findings.append(
                    Finding(
                        "deck_plan",
                        "icon",
                        "warn",
                        "fail",
                        f"page {page_id}: unknown icon '{icon_name}'",
                        "deck_plan",
                    )
                )
        card.fill.solid()
        card.fill.fore_color.rgb = t.card_fill
        card.line.color.rgb = t.card_line
        card.line.width = Pt(1)
        card.shadow.inherit = False
        frame = card.text_frame
        frame.word_wrap = True
        frame.margin_left = Inches(pad_h + icon_width)
        frame.margin_right = Inches(pad_h)
        frame.margin_top = Inches(pad_v)
        frame.margin_bottom = Inches(pad_v)
        _set(
            frame.paragraphs[0],
            point,
            size=size,
            font=theme.body_font,
            color=t.text,
            bold=t.body_bold,
            italic=t.body_italic,
        )
        if detail:
            detail_para = frame.add_paragraph()
            detail_para.space_before = Pt(2)
            _set(detail_para, detail, size=detail_size, font=theme.body_font, color=t.muted)
        shapes[f"support_points[{index}]"] = [card.shape_id]
        cursor += heights[index] + gap
    # block-level address: the whole stack animates together in pptx v1
    shapes["support_points"] = [
        shape_id
        for index in range(len(points))
        for shape_id in shapes.get(f"support_points[{index}]", [])
    ]


def _render_callout(
    slide,
    callout: dict,
    theme: RenderTheme,
    result: RenderResult,
    page_id: str,
    shapes: dict,
    *,
    x: float = _MARGIN_X,
    y: float = 6.1,
    w: float = _BODY_W,
) -> None:
    t = theme.theme
    text = str(callout.get("text", ""))
    band = slide.shapes.add_shape(_ROUNDED, Inches(x), Inches(y), Inches(w), Inches(0.85))
    band.name = "callout"
    shapes["callout"] = [band.shape_id]
    band.fill.solid()
    band.fill.fore_color.rgb = t.card_fill
    band.line.color.rgb = t.card_line
    band.line.width = Pt(1)
    band.shadow.inherit = False
    bar = slide.shapes.add_shape(1, Inches(x + 0.08), Inches(y + 0.12), Pt(5), Inches(0.61))
    bar.name = "decor"
    bar.fill.solid()
    bar.fill.fore_color.rgb = t.accent
    bar.line.fill.background()
    size = _fit_or_report(
        text,
        page_id=page_id,
        element="callout",
        width_in=w - 0.7,
        height_in=0.62,
        max_size=t.callout_size,
        min_size=14,
        family=theme.body_font,
        findings=result.findings,
    )
    box = _textbox(slide, Inches(x + 0.35), Inches(y + 0.04), Inches(w - 0.7), Inches(0.78))
    _set(box.text_frame.paragraphs[0], text, size=size, font=theme.body_font, color=t.text)


def _render_hero_split(
    slide,
    page: dict,
    run_root: Path,
    theme: RenderTheme,
    result: RenderResult,
    evidence: dict | None,
    shapes: dict,
) -> None:
    """Hero Split: full-height hero visual on right, title/points on left."""
    t = theme.theme
    page_id = page["id"]
    title_top = 0.42
    kicker = str(page.get("kicker") or "")
    if kicker:
        kick = _textbox(slide, Inches(_MARGIN_X), Inches(0.42), Inches(5.8), Inches(0.34))
        _set(
            kick.text_frame.paragraphs[0],
            kicker,
            size=t.kicker_size,
            font=theme.body_font,
            color=t.accent,
            bold=True,
        )
        title_top = 0.78
    size = _fit_or_report(
        page["title"],
        page_id=page_id,
        element="title",
        width_in=5.8,
        height_in=1.3,
        max_size=t.content_title_size,
        min_size=20,
        family=theme.title_font,
        findings=result.findings,
    )
    title = _textbox(slide, Inches(_MARGIN_X), Inches(title_top), Inches(5.8), Inches(1.3))
    shapes["title"] = [title.shape_id]
    _set(
        title.text_frame.paragraphs[0],
        page["title"],
        size=size,
        font=theme.title_font,
        color=t.title_color,
        bold=t.title_bold,
        italic=t.title_italic,
    )

    hair_y = title_top + 1.35
    hair = slide.shapes.add_shape(1, Inches(_MARGIN_X), Inches(hair_y), Inches(5.8), Pt(0.75))
    hair.name = "decor"
    hair.fill.solid()
    hair.fill.fore_color.rgb = t.card_line
    hair.line.fill.background()

    # Points on left
    points = page.get("support_points", [])
    callout = page.get("callout")
    bottom_bound = 5.95 if callout else 6.7
    if points:
        _render_points(
            slide,
            points,
            page_id=page_id,
            x=_MARGIN_X,
            y=hair_y + 0.2,
            width_in=5.8,
            height_in=bottom_bound - (hair_y + 0.2),
            theme=theme,
            findings=result.findings,
            shapes=shapes,
            run_root=run_root,
        )
    if callout:
        _render_callout(slide, callout, theme, result, page_id, shapes, x=_MARGIN_X, y=6.0, w=5.8)

    # Hero visual on right
    visual = page.get("visual") or {}
    if visual.get("table"):
        from .table import render_table

        frame = render_table(
            slide,
            visual["table"],
            evidence,
            page_id,
            theme,
            x=7.1,
            y=_BODY_TOP,
            w=5.3,
            h=_BODY_BOTTOM - _BODY_TOP,
        )
        shapes["visual"] = [frame.shape_id]
    elif visual.get("chart"):
        _add_chart(
            slide,
            page_id,
            visual["chart"],
            t,
            result,
            evidence,
            x=7.1,
            y=_BODY_TOP,
            w=5.3,
            h=_BODY_BOTTOM - _BODY_TOP,
            shapes=shapes,
        )
    elif visual.get("diagram"):
        _add_diagram(
            slide,
            page_id,
            visual["diagram"],
            theme,
            result,
            run_root,
            shapes,
            x=7.1,
            w=5.3,
            h=_BODY_BOTTOM - _BODY_TOP,
        )
    else:
        _add_figure(slide, page, run_root, theme, result, shapes)


def _render_fullscreen_backdrop(
    slide,
    page: dict,
    run_root: Path,
    theme: RenderTheme,
    result: RenderResult,
    evidence: dict | None,
    shapes: dict,
) -> None:
    """Fullscreen Backdrop: centered focus card over full-bleed background."""
    t = theme.theme
    page_id = page["id"]
    card_w, card_h = 10.2, 5.5
    card_x, card_y = (_SLIDE_W.inches - card_w) / 2, 0.95
    card = slide.shapes.add_shape(
        _ROUNDED, Inches(card_x), Inches(card_y), Inches(card_w), Inches(card_h)
    )
    card.name = "backdrop_card"
    card.fill.solid()
    card.fill.fore_color.rgb = t.card_fill
    card.line.color.rgb = t.card_line
    card.line.width = Pt(1)

    title_top = card_y + 0.3
    kicker = str(page.get("kicker") or "")
    if kicker:
        kick = _textbox(
            slide, Inches(card_x + 0.5), Inches(title_top), Inches(card_w - 1.0), Inches(0.34)
        )
        _set(
            kick.text_frame.paragraphs[0],
            kicker,
            size=t.kicker_size,
            font=theme.body_font,
            color=t.accent,
            bold=True,
        )
        title_top += 0.36
    size = _fit_or_report(
        page["title"],
        page_id=page_id,
        element="title",
        width_in=card_w - 1.0,
        height_in=1.1,
        max_size=t.content_title_size,
        min_size=20,
        family=theme.title_font,
        findings=result.findings,
    )
    title = _textbox(
        slide, Inches(card_x + 0.5), Inches(title_top), Inches(card_w - 1.0), Inches(1.1)
    )
    shapes["title"] = [title.shape_id]
    _set(
        title.text_frame.paragraphs[0],
        page["title"],
        size=size,
        font=theme.title_font,
        color=t.title_color,
        bold=t.title_bold,
        italic=t.title_italic,
    )

    hair_y = title_top + 1.15
    hair = slide.shapes.add_shape(
        1, Inches(card_x + 0.5), Inches(hair_y), Inches(card_w - 1.0), Pt(0.75)
    )
    hair.name = "decor"
    hair.fill.solid()
    hair.fill.fore_color.rgb = t.card_line
    hair.line.fill.background()

    points = page.get("support_points", [])
    callout = page.get("callout")
    bottom_bound = (card_y + card_h - 1.0) if callout else (card_y + card_h - 0.3)
    if points:
        _render_points(
            slide,
            points,
            page_id=page_id,
            x=card_x + 0.5,
            y=hair_y + 0.15,
            width_in=card_w - 1.0,
            height_in=bottom_bound - (hair_y + 0.15),
            theme=theme,
            findings=result.findings,
            shapes=shapes,
            run_root=run_root,
        )
    if callout:
        _render_callout(
            slide,
            callout,
            theme,
            result,
            page_id,
            shapes,
            x=card_x + 0.5,
            y=card_y + card_h - 0.9,
            w=card_w - 1.0,
        )


def _render_timeline(
    slide,
    page: dict,
    theme: RenderTheme,
    result: RenderResult,
    evidence: dict | None,
    shapes: dict,
) -> None:
    """Timeline: 3-4 horizontal milestone cards."""
    t = theme.theme
    page_id = page["id"]
    entries = page.get("support_points") or []
    if len(entries) > 4:
        result.findings.append(
            Finding(
                "deck_plan",
                "layout",
                "warn",
                "pass",
                f"page {page_id}: timeline has {len(entries)} milestones "
                "(recommended 3-4) — excess items may cause layout crowding",
                "deck_plan",
            )
        )

    title_top = 0.42
    kicker = str(page.get("kicker") or "")
    if kicker:
        kick = _textbox(slide, Inches(_MARGIN_X), Inches(0.42), Inches(_BODY_W), Inches(0.34))
        _set(
            kick.text_frame.paragraphs[0],
            kicker,
            size=t.kicker_size,
            font=theme.body_font,
            color=t.accent,
            bold=True,
        )
        title_top = 0.78
    size = _fit_or_report(
        page["title"],
        page_id=page_id,
        element="title",
        width_in=_BODY_W,
        height_in=1.1,
        max_size=t.content_title_size,
        min_size=20,
        family=theme.title_font,
        findings=result.findings,
    )
    title = _textbox(slide, Inches(_MARGIN_X), Inches(title_top), Inches(_BODY_W), Inches(1.1))
    shapes["title"] = [title.shape_id]
    _set(
        title.text_frame.paragraphs[0],
        page["title"],
        size=size,
        font=theme.title_font,
        color=t.title_color,
        bold=t.title_bold,
        italic=t.title_italic,
    )

    hair_y = title_top + 1.12
    hair = slide.shapes.add_shape(1, Inches(_MARGIN_X), Inches(hair_y), Inches(_BODY_W), Pt(0.75))
    hair.name = "decor"
    hair.fill.solid()
    hair.fill.fore_color.rgb = t.card_line
    hair.line.fill.background()

    n = max(len(entries), 1)
    gap = 0.25
    card_w = (_BODY_W - gap * (n - 1)) / n
    card_y = hair_y + 0.35
    card_h = 4.2

    for i, entry in enumerate(entries):
        card_x = _MARGIN_X + i * (card_w + gap)
        card = slide.shapes.add_shape(
            _ROUNDED, Inches(card_x), Inches(card_y), Inches(card_w), Inches(card_h)
        )
        card.name = f"milestone_{i}"
        card.fill.solid()
        card.fill.fore_color.rgb = t.card_fill
        card.line.color.rgb = t.card_line
        card.line.width = Pt(1)

        # Step Badge
        badge = slide.shapes.add_shape(
            9, Inches(card_x + 0.2), Inches(card_y + 0.25), Inches(0.45), Inches(0.45)
        )
        badge.fill.solid()
        badge.fill.fore_color.rgb = t.accent
        badge.line.fill.background()
        badge_text = _textbox(
            slide, Inches(card_x + 0.2), Inches(card_y + 0.25), Inches(0.45), Inches(0.45)
        )
        _set(
            badge_text.text_frame.paragraphs[0],
            f"{i + 1:02d}",
            size=11,
            font=theme.title_font,
            color=t.background,
            bold=True,
        )
        badge_text.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

        pt_text, pt_detail = _point_parts(entry)
        pt_size = _fit_or_report(
            pt_text,
            page_id=page_id,
            element=f"milestone[{i}]",
            width_in=card_w - 0.4,
            height_in=1.2,
            max_size=t.body_size,
            min_size=14,
            family=theme.body_font,
            findings=result.findings,
        )
        box = _textbox(
            slide,
            Inches(card_x + 0.2),
            Inches(card_y + 0.85),
            Inches(card_w - 0.4),
            Inches(card_h - 1.0),
        )
        _set(
            box.text_frame.paragraphs[0],
            pt_text,
            size=pt_size,
            font=theme.body_font,
            color=t.text,
            bold=True,
        )
        if pt_detail:
            # detail must fit the card too: measure it, shrink toward the
            # floor, and report when even the floor overflows
            box_h = card_h - 1.0
            inner_w = (card_w - 0.6) * _PT_PER_IN
            title_lines = len(wrap_lines(pt_text, pt_size, inner_w, theme.body_font))
            budget = box_h * _PT_PER_IN - 8 - title_lines * pt_size * _LINE_SPACING
            detail_size = t.detail_size
            for candidate in (
                [t.detail_size] if FIXED_TEXT_SIZES.get() else range(t.detail_size, 10, -1)
            ):
                lines = wrap_lines(pt_detail, candidate, inner_w, theme.body_font)
                if len(lines) * candidate * 1.3 <= budget:
                    detail_size = candidate
                    break
            else:
                detail_size = 11
                result.findings.append(
                    Finding(
                        "deck_plan",
                        "layout",
                        "warn",
                        "fail",
                        f"page {page_id}: milestone[{i}] detail does not fit the card "
                        f"even at 11pt — trim it or demote to notes",
                        "deck_plan",
                    )
                )
            p = box.text_frame.add_paragraph()
            p.space_before = Pt(8)
            _set(p, pt_detail, size=detail_size, font=theme.body_font, color=t.muted)
        shapes[f"support_points[{i}]"] = [card.shape_id, box.shape_id]


def _render_versus(
    slide,
    page: dict,
    theme: RenderTheme,
    result: RenderResult,
    evidence: dict | None,
    shapes: dict,
) -> None:
    """Versus: 2-column side-by-side comparison."""
    t = theme.theme
    page_id = page["id"]

    title_top = 0.42
    kicker = str(page.get("kicker") or "")
    if kicker:
        kick = _textbox(slide, Inches(_MARGIN_X), Inches(0.42), Inches(_BODY_W), Inches(0.34))
        _set(
            kick.text_frame.paragraphs[0],
            kicker,
            size=t.kicker_size,
            font=theme.body_font,
            color=t.accent,
            bold=True,
        )
        title_top = 0.78
    size = _fit_or_report(
        page["title"],
        page_id=page_id,
        element="title",
        width_in=_BODY_W,
        height_in=1.1,
        max_size=t.content_title_size,
        min_size=20,
        family=theme.title_font,
        findings=result.findings,
    )
    title = _textbox(slide, Inches(_MARGIN_X), Inches(title_top), Inches(_BODY_W), Inches(1.1))
    shapes["title"] = [title.shape_id]
    _set(
        title.text_frame.paragraphs[0],
        page["title"],
        size=size,
        font=theme.title_font,
        color=t.title_color,
        bold=t.title_bold,
        italic=t.title_italic,
    )

    hair_y = title_top + 1.12
    hair = slide.shapes.add_shape(1, Inches(_MARGIN_X), Inches(hair_y), Inches(_BODY_W), Pt(0.75))
    hair.name = "decor"
    hair.fill.solid()
    hair.fill.fore_color.rgb = t.card_line
    hair.line.fill.background()

    entries = page.get("support_points") or []
    half = (len(entries) + 1) // 2
    left_entries = entries[:half]
    right_entries = entries[half:]

    card_w = (_BODY_W - 0.4) / 2
    card_y = hair_y + 0.25
    card_h = 4.4

    left_label, right_label = _versus_labels(page, result)
    for col_idx, (col_items, col_label) in enumerate(
        [(left_entries, left_label), (right_entries, right_label)]
    ):
        cx = _MARGIN_X + col_idx * (card_w + 0.4)
        card = slide.shapes.add_shape(
            _ROUNDED, Inches(cx), Inches(card_y), Inches(card_w), Inches(card_h)
        )
        card.name = f"versus_col_{col_idx}"
        card.fill.solid()
        card.fill.fore_color.rgb = t.card_fill
        card.line.color.rgb = t.card_line
        card.line.width = Pt(1)

        hdr = _textbox(
            slide, Inches(cx + 0.3), Inches(card_y + 0.2), Inches(card_w - 0.6), Inches(0.4)
        )
        _set(
            hdr.text_frame.paragraphs[0],
            col_label,
            size=13,
            font=theme.body_font,
            color=t.accent,
            bold=True,
        )

        _render_points(
            slide,
            col_items,
            page_id=page_id,
            x=cx + 0.3,
            y=card_y + 0.7,
            width_in=card_w - 0.6,
            height_in=card_h - 0.9,
            theme=theme,
            findings=result.findings,
            shapes=shapes,
        )


# -- charts -----------------------------------------------------------------


def _add_chart(
    slide,
    page_id: str,
    spec: dict,
    t,
    result: RenderResult,
    evidence: dict | None,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    shapes: dict,
) -> None:
    chart_type = str(spec.get("type", "column")).lower()
    if chart_type not in _CHART_TYPES:
        result.findings.append(
            Finding(
                "deck_plan",
                "chart",
                "warn",
                "fail",
                f"page {page_id} chart type '{chart_type}' unknown "
                f"(known: {', '.join(_CHART_TYPES)}); skipping chart",
                "deck_plan",
            )
        )
        return
    items = {item["id"]: item for item in (evidence or {}).get("items", [])}
    values: list[float] = []
    labels: list[str] = []
    units: set[str] = set()
    for entry in spec.get("series", []):
        ref = entry.get("value_from", "")
        number, unit = _evidence_number(items, ref, page_id, "chart")
        values.append(number)
        labels.append(str(entry.get("label", ref)))
        if unit:
            units.add(str(unit))

    data = CategoryChartData()
    data.categories = labels
    series_name = str(spec.get("series_name") or ("; ".join(sorted(units)) or "value"))
    data.add_series(series_name, tuple(values))
    frame = slide.shapes.add_chart(
        _CHART_TYPES[chart_type],
        Inches(x),
        Inches(y),
        Inches(w),
        Inches(h),
        data,
    )
    shapes["visual"] = [frame.shape_id]
    chart = frame.chart
    chart.has_legend = False
    if spec.get("title"):
        chart.has_title = True
        chart.chart_title.text_frame.text = str(spec["title"])
    try:
        series = chart.series[0]
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = t.accent
    except (IndexError, AttributeError):  # pragma: no cover - chart type quirks
        pass


# -- transitions --------------------------------------------------------------


def _apply_transition(prs: Presentation, plan: dict, result: RenderResult) -> None:
    style = plan.get("deck", {}).get("style") or {}
    requested = style.get("transition")
    if not requested:
        return
    tag = str(requested).lower()
    if tag not in _TRANSITIONS:
        result.findings.append(
            Finding(
                "deck_plan",
                "transition",
                "warn",
                "fail",
                f"transition '{requested}' unknown (known: {', '.join(_TRANSITIONS)}); skipped",
                "deck_plan",
            )
        )
        return
    for slide in prs.slides:
        element = slide._element  # noqa: SLF001 - python-pptx has no transition API
        transition = element.makeelement(qn("p:transition"), {"spd": "med"})
        child = element.makeelement(qn(f"p:{tag}"), dict(_TRANSITIONS[tag]))
        transition.append(child)
        element.append(transition)  # CT_Slide: after cSld/clrMapOvr, before timing
    result.transition = tag


# -- pptx animations (experimental, opt-in via style.animations) -------------
#
# python-pptx has no animation API; this injects minimal <p:timing> trees for
# the two entrance verbs PowerPoint accepts most reliably (appear, fade_in).
# Every step is click-triggered (with_previous joins the current click group).
# Emphasis verbs and per-paragraph granularity are HTML-only for now and
# produce info findings. OFF by default: set deck.style.animations to true and
# verify in a real PowerPoint before trusting it (timing XML is the documented
# corruption risk of this format).

_PPTX_VERBS = {"appear": 1, "fade_in": 10}  # entrance presetIDs


def _el(parent, tag: str, **attrs):
    element = parent.makeelement(qn(f"p:{tag}"), {k: str(v) for k, v in attrs.items()})
    parent.append(element)
    return element


def _effect_group(parent, shape_ids: list[int], fade: bool, counter: iter) -> None:
    """One <p:par> click group containing entrance effects for each shape."""
    outer = _el(parent, "par")
    outer_ct = _el(outer, "cTn", id=next(counter), fill="hold")
    _el(_el(outer_ct, "stCondLst"), "cond", delay="indefinite")
    inner = _el(_el(outer_ct, "childTnLst"), "par")
    inner_ct = _el(inner, "cTn", id=next(counter), fill="hold")
    _el(_el(inner_ct, "stCondLst"), "cond", delay="0")
    effects = _el(_el(inner_ct, "childTnLst"), "par")
    for position, shape_id in enumerate(shape_ids):
        # first effect in a click group is clickEffect; the rest animate with it
        node_type = "clickEffect" if position == 0 else "withEffect"
        effect = _el(
            effects,
            "cTn",
            id=next(counter),
            fill="hold",
            grpId="0",
            nodeType=node_type,
            presetID="10" if fade else "1",
            presetClass="entr",
            presetSubtype="0",
        )
        _el(_el(effect, "stCondLst"), "cond", delay="0")
        behaviors = _el(effect, "childTnLst")
        visible = _el(behaviors, "set")
        set_ctn = _el(
            _el(_el(visible, "cBhvr"), "cTn", id=next(counter), dur="1", fill="hold"),
            "stCondLst",
        )
        _el(set_ctn, "cond", delay="0")
        behavior = visible.find(qn("p:cBhvr"))
        _el(_el(behavior, "tgtEl"), "spTgt", spid=shape_id)
        names = _el(_el(behavior, "attrNameLst"), "attrName")
        names.text = "style.visibility"
        _el(visible, "to").append(visible.makeelement(qn("p:strVal"), {"val": "visible"}))
        if fade:
            anim = _el(behaviors, "animEffect", transition="in", filter="fade")
            _el(_el(anim, "cBhvr"), "cTn", id=next(counter), dur="500")
            _el(_el(anim.find(qn("p:cBhvr")), "tgtEl"), "spTgt", spid=shape_id)


def _apply_animations(prs: Presentation, plan: dict, result: RenderResult) -> None:
    style = plan.get("deck", {}).get("style") or {}
    if not style.get("animations"):
        return
    for page in plan.get("deck", {}).get("pages", []):
        page_id = page.get("id")
        shapes = result.shape_map.get(page_id) or {}
        steps = [s for s in (page.get("reveal") or []) if isinstance(s, dict)]
        if not steps:
            continue
        groups: list[tuple[list[int], bool]] = []
        for step in steps:
            verb = str(step.get("verb", "fade_in"))
            fade = verb == "fade_in"
            if verb not in _PPTX_VERBS:
                result.findings.append(
                    Finding(
                        "deck_plan",
                        "animation",
                        "info",
                        "pass",
                        f"page {page_id}: verb '{verb}' executes on the HTML surface only "
                        f"(pptx v1: appear/fade_in)",
                        "deck_plan",
                    )
                )
            targets: list[int] = []
            for address in step.get("elements") or []:
                address = str(address)
                if address.startswith("support_points["):
                    result.findings.append(
                        Finding(
                            "deck_plan",
                            "animation",
                            "info",
                            "pass",
                            f"page {page_id}: '{address}' animates as the whole points block "
                            f"in pptx v1 (paragraph-level is HTML-only)",
                            "deck_plan",
                        )
                    )
                ids = shapes.get(address) or shapes.get(address.split("[")[0]) or []
                for shape_id in ids:
                    if shape_id not in targets:
                        targets.append(shape_id)
            if not targets:
                continue
            if step.get("trigger") == "with_previous" and groups:
                groups[-1][0].extend(targets)
            else:
                groups.append((targets, fade))
        if not groups:
            continue
        slide = prs.slides[result.slide_index[page_id]]
        timing = _el(slide._element, "timing")  # noqa: SLF001
        tn_list = _el(_el(timing, "tnLst"), "par")
        root = _el(tn_list, "cTn", id=1, dur="indefinite", restart="never", nodeType="tmRoot")
        seq = _el(_el(_el(root, "childTnLst"), "seq"), "cTn", concurrent="1", nextAc="seek")
        main = _el(seq, "cTn", id=2, dur="indefinite", nodeType="mainSeq")
        counter = iter(range(3, 3 + 64 * len(groups)))
        holder = _el(main, "childTnLst")
        for targets, fade in groups:
            _effect_group(holder, targets, fade, counter)
        prev = _el(seq, "prevCondLst")
        _el(_el(_el(prev, "cond", evt="onPrev", delay="0"), "tgtEl"), "sldTgt")
        nxt = _el(seq, "nextCondLst")
        _el(_el(_el(nxt, "cond", evt="onNext", delay="0"), "tgtEl"), "sldTgt")


# -- post-render geometry validation ------------------------------------------
#
# Occlusion and overlap are exactly the class of defect a harness can catch
# deterministically: after building every slide, read back each shape's
# bounding box and verify (a) nothing falls off the canvas (the y=-19048in
# unit-mixing bug shipped once; never again) and (b) no two content blocks
# overlap unless one contains the other (intentional layering). Decorative
# furniture (hairlines, accent segments, bands) is name-tagged "decor" and
# exempt. Findings land in qa/render-deck.yaml like every other check.


def _shape_bbox(shape) -> tuple[float, float, float, float]:
    return (
        shape.left / _EMU_PER_IN,
        shape.top / _EMU_PER_IN,
        (shape.left + shape.width) / _EMU_PER_IN,
        (shape.top + shape.height) / _EMU_PER_IN,
    )


_EMU_PER_IN = 914400
_TOLERANCE = 0.06  # inches


def _contains(
    outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]
) -> bool:
    return (
        outer[0] - _TOLERANCE <= inner[0]
        and outer[1] - _TOLERANCE <= inner[1]
        and outer[2] + _TOLERANCE >= inner[2]
        and outer[3] + _TOLERANCE >= inner[3]
    )


def _overlap_area(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, width) * max(0.0, height)


def _check_geometry(prs: Presentation, result: RenderResult) -> None:
    slide_w = prs.slide_width / _EMU_PER_IN
    slide_h = prs.slide_height / _EMU_PER_IN
    for slide_number, slide in enumerate(prs.slides, 1):
        boxes: list[tuple[str, tuple[float, float, float, float]]] = []
        for shape in slide.shapes:
            name = shape.name or "shape"
            bbox = _shape_bbox(shape)
            if name != "decor" and (
                bbox[0] < -_TOLERANCE
                or bbox[1] < -_TOLERANCE
                or bbox[2] > slide_w + _TOLERANCE
                or bbox[3] > slide_h + _TOLERANCE
            ):
                result.findings.append(
                    Finding(
                        "deck_plan",
                        "geometry",
                        "warn",
                        "fail",
                        f"slide {slide_number}: '{name}' falls outside the canvas "
                        f"({bbox[0]:.2f},{bbox[1]:.2f})-({bbox[2]:.2f},{bbox[3]:.2f})",
                        "deck_plan",
                    )
                )
            if name != "decor" and not name.startswith("diagram-edge:"):
                boxes.append((name, bbox))
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                name_a, box_a = boxes[i]
                name_b, box_b = boxes[j]
                if _contains(box_a, box_b) or _contains(box_b, box_a):
                    continue  # intentional layering (child inside parent)
                area = _overlap_area(box_a, box_b)
                smaller = min(
                    (box_a[2] - box_a[0]) * (box_a[3] - box_a[1]),
                    (box_b[2] - box_b[0]) * (box_b[3] - box_b[1]),
                )
                if smaller > 0 and area / smaller > 0.04:
                    result.findings.append(
                        Finding(
                            "deck_plan",
                            "geometry",
                            "warn",
                            "fail",
                            f"slide {slide_number}: '{name_a}' overlaps '{name_b}' "
                            f"({area / smaller:.0%} of the smaller block)",
                            "deck_plan",
                        )
                    )
