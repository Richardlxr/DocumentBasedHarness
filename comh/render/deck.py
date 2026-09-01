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
from .metrics import fit_box, wrap_lines
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
_BODY_TOP = 2.0
_BODY_BOTTOM = 5.95


@dataclass(slots=True)
class RenderResult:
    output: Path
    theme: str
    transition: str | None
    findings: list[Finding] = field(default_factory=list)


def render_deck(
    plan: dict,
    run_root: Path,
    output: Path,
    *,
    language: str = "en",
    evidence: dict | None = None,
    allow_dark: bool = True,
) -> RenderResult:
    theme = render_theme(plan.get("deck", {}).get("style"), language, allow_dark=allow_dark)
    result = RenderResult(output=output, theme=theme.theme.name, transition=None)
    if theme.fallback_reason:
        result.findings.append(
            Finding("deck_plan", "theme", "warn", "fail", theme.fallback_reason, "deck_plan")
        )
    if theme.forced_light:
        result.findings.append(
            Finding(
                "deck_plan", "theme", "warn", "fail",
                "brief forbids a dark background; dark template forced to light", "deck_plan",
            )
        )

    prs = Presentation()
    prs.slide_width = _SLIDE_W
    prs.slide_height = _SLIDE_H

    for page in plan["deck"]["pages"]:
        role = page.get("page_role", "content")
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _paint_background(slide, theme.theme.background)
        if role == "cover":
            _render_cover(slide, page, theme, result)
        elif role in ("agenda", "section_divider", "closing"):
            _render_banner(slide, page, theme, result)
        else:
            _render_content(slide, page, run_root, theme, result, evidence)
        _add_notes(slide, page)

    _apply_transition(prs, plan, result)
    output.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output)
    return result


# -- shared helpers ---------------------------------------------------------


def _paint_background(slide, color) -> None:
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _textbox(slide, left, top, width, height) -> object:
    box = slide.shapes.add_textbox(left, top, width, height)
    box.text_frame.word_wrap = True
    return box


def _set(paragraph, text: str, *, size: int, font: str, color, bold: bool = False) -> None:
    paragraph.text = text
    for run in paragraph.runs:
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = font


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
        min_size=min_size,
        family=family,
    )
    if fit.overflows:
        findings.append(
            Finding(
                "deck_plan", "layout", "warn", "fail",
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


# -- page kinds --------------------------------------------------------------


def _render_cover(slide, page: dict, theme: RenderTheme, result: RenderResult) -> None:
    t = theme.theme
    points = page.get("support_points", [])
    joined = "  ·  ".join(p[0] for p in (_point_parts(x) for x in points))
    subtitle_lines = len(wrap_lines(joined, t.body_size, _BODY_W * _PT_PER_IN, theme.body_font))
    size = _fit_or_report(
        page["title"], page_id=page["id"], element="title",
        width_in=_BODY_W, height_in=2.4 - 0.35 * subtitle_lines,
        max_size=t.cover_title_size, min_size=28, family=theme.title_font,
        findings=result.findings,
    )
    box = _textbox(slide, Inches(1.0), Inches(2.4), Inches(_BODY_W), Inches(2.4))
    _set(
        box.text_frame.paragraphs[0], page["title"],
        size=size, font=theme.title_font, color=t.text, bold=True,
    )
    if joined:
        paragraph = box.text_frame.add_paragraph()
        _set(paragraph, joined, size=t.body_size, font=theme.body_font, color=t.muted)


def _render_banner(slide, page: dict, theme: RenderTheme, result: RenderResult) -> None:
    t = theme.theme
    accent = slide.shapes.add_shape(1, Inches(0.9), Inches(2.35), Inches(1.2), Pt(6))
    accent.fill.solid()
    accent.fill.fore_color.rgb = t.accent
    accent.line.fill.background()
    points = page.get("support_points", [])
    body_lines = sum(
        len(wrap_lines(p, t.body_size, _BODY_W * _PT_PER_IN, theme.body_font)) for p, _ in
        (_point_parts(x) for x in points)
    )
    size = _fit_or_report(
        page["title"], page_id=page["id"], element="title",
        width_in=_BODY_W, height_in=2.2 - 0.32 * body_lines,
        max_size=t.banner_title_size, min_size=24, family=theme.title_font,
        findings=result.findings,
    )
    box = _textbox(slide, Inches(1.0), Inches(2.7), Inches(_BODY_W), Inches(2.4))
    _set(
        box.text_frame.paragraphs[0], page["title"],
        size=size, font=theme.title_font, color=t.text, bold=True,
    )
    for entry in points:
        point, _ = _point_parts(entry)
        paragraph = box.text_frame.add_paragraph()
        paragraph.text = point
        paragraph.space_before = Pt(10)
        _set(paragraph, point, size=t.body_size, font=theme.body_font, color=t.muted)


def _render_content(
    slide, page: dict, run_root: Path, theme: RenderTheme,
    result: RenderResult, evidence: dict | None,
) -> None:
    t = theme.theme
    page_id = page["id"]
    chart_spec = (page.get("visual") or {}).get("chart")
    cards = page.get("metric_cards") or []

    size = _fit_or_report(
        page["title"], page_id=page_id, element="title",
        width_in=_BODY_W, height_in=1.4, max_size=t.content_title_size, min_size=20,
        family=theme.title_font, findings=result.findings,
    )
    title = _textbox(slide, Inches(_MARGIN_X), Inches(0.5), Inches(_BODY_W), Inches(1.4))
    _set(
        title.text_frame.paragraphs[0], page["title"],
        size=size, font=theme.title_font, color=t.text, bold=True,
    )
    underline = slide.shapes.add_shape(1, Inches(_MARGIN_X), Inches(1.62), Inches(0.7), Pt(5))
    underline.fill.solid()
    underline.fill.fore_color.rgb = t.accent
    underline.line.fill.background()

    content_top = _BODY_TOP
    if cards:
        _render_metric_cards(slide, cards, theme, result, evidence, page_id)
        content_top = _BODY_TOP + 1.65

    body_width = _BODY_W
    if chart_spec is not None:
        _add_chart(
            slide, page_id, chart_spec, t, result, evidence,
            x=6.55, y=content_top, w=5.9, h=_BODY_BOTTOM - content_top,
        )
        body_width = 5.35
    else:
        _add_figure(slide, page, run_root, theme, result)
        body_width = 5.35 if _has_figure(page, run_root) else _BODY_W

    points = page.get("support_points", [])
    if points:
        _render_points(
            slide, points, page_id=page_id, x=_MARGIN_X, y=content_top,
            width_in=body_width, height_in=_BODY_BOTTOM - content_top,
            theme=theme, findings=result.findings,
        )

    callout = page.get("callout")
    if callout:
        _render_callout(slide, callout, theme, result, page_id)


def _has_figure(page: dict, run_root: Path) -> bool:
    return any((run_root / entry["ref"]).is_file() for entry in _asset_entries(page))


def _asset_entries(page: dict) -> list[dict]:
    return [
        item if isinstance(item, dict) else {"ref": item}
        for item in (page.get("visual") or {}).get("asset_refs", [])
    ]


def _add_figure(
    slide, page: dict, run_root: Path, theme: RenderTheme, result: RenderResult
) -> None:
    for entry in _asset_entries(page):
        image = run_root / entry["ref"]
        if not image.is_file():
            result.findings.append(
                Finding(
                    "deck_plan", "asset", "warn", "fail",
                    f"page {page['id']} figure '{entry['ref']}' not found under the run root",
                    "deck_plan",
                )
            )
            continue
        slide.shapes.add_picture(str(image), Inches(6.55), Inches(_BODY_TOP), width=Inches(5.9))
        caption = entry.get("caption")
        if caption:
            box = _textbox(slide, Inches(6.55), Inches(6.05), Inches(5.9), Inches(0.4))
            paragraph = box.text_frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.CENTER
            _set(
                paragraph, caption, size=theme.theme.caption_size,
                font=theme.body_font, color=theme.theme.muted,
            )
        return


def _render_metric_cards(
    slide, cards: list, theme: RenderTheme, result: RenderResult,
    evidence: dict | None, page_id: str,
) -> None:
    t = theme.theme
    items = {item["id"]: item for item in (evidence or {}).get("items", [])}
    if len(cards) > 4:
        result.findings.append(
            Finding(
                "deck_plan", "layout", "warn", "fail",
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
            _ROUNDED, Inches(left), Inches(_BODY_TOP), Inches(width), Inches(1.45)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = t.card_fill
        shape.line.color.rgb = t.card_line
        shape.line.width = Pt(1)
        shape.shadow.inherit = False
        value_text = _fmt(number) + (f" {unit}" if unit else "")
        value_box = _textbox(
            slide, Inches(left), Inches(_BODY_TOP + 0.12), Inches(width), Inches(0.75)
        )
        _set(
            value_box.text_frame.paragraphs[0], value_text,
            size=t.card_value_size, font=theme.title_font, color=t.accent, bold=True,
        )
        value_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        label = str(card.get("label") or card.get("value_from", ""))
        label_box = _textbox(
            slide, Inches(left), Inches(_BODY_TOP + 0.92), Inches(width), Inches(0.45)
        )
        _set(
            label_box.text_frame.paragraphs[0], label,
            size=t.card_label_size, font=theme.body_font, color=t.muted,
        )
        label_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER


def _render_points(
    slide, points: list, *, page_id: str, x: float, y: float,
    width_in: float, height_in: float, theme: RenderTheme, findings: list[Finding],
) -> None:
    t = theme.theme
    detail_size = t.detail_size

    def measure_full(size: int) -> float:
        total = 0.0
        for entry in points:
            point, detail = _point_parts(entry)
            max_pt = width_in * _PT_PER_IN
            point_lines = wrap_lines("• " + point, size, max_pt, theme.body_font)
            total += len(point_lines) * size * _LINE_SPACING + 6
            if detail:
                detail_lines = wrap_lines(
                    detail, detail_size, (width_in - 0.35) * _PT_PER_IN, theme.body_font
                )
                total += len(detail_lines) * detail_size * 1.3 + 8
        return total

    max_size = t.body_size if width_in < _BODY_W else t.body_size_wide
    size = 14
    for candidate in range(max_size, 13, -1):
        if measure_full(candidate) <= height_in * _PT_PER_IN:
            size = candidate
            break
    else:
        findings.append(
            Finding(
                "deck_plan", "layout", "warn", "fail",
                f"page {page_id} body points do not fit at 14pt — demote content to "
                f"notes/appendix (see stages/deck.md)",
                "deck_plan",
            )
        )

    needed = measure_full(size)
    leftover = height_in * _PT_PER_IN - needed
    extra_gap = max(0.0, min(leftover / max(len(points), 1), 26.0))

    box = _textbox(slide, Inches(x), Inches(y), Inches(width_in), Inches(height_in))
    first = True
    for entry in points:
        point, detail = _point_parts(entry)
        if first:
            paragraph = box.text_frame.paragraphs[0]
        else:
            paragraph = box.text_frame.add_paragraph()
            paragraph.space_before = Pt(extra_gap)
        first = False
        _set(
            paragraph, "• " + point,
            size=size, font=theme.body_font, color=t.text, bold=detail is not None,
        )
        if detail:
            detail_para = box.text_frame.add_paragraph()
            detail_para.space_before = Pt(2)
            _set(
                detail_para, detail, size=detail_size,
                font=theme.body_font, color=t.muted,
            )


def _render_callout(
    slide, callout: dict, theme: RenderTheme, result: RenderResult, page_id: str
) -> None:
    t = theme.theme
    text = str(callout.get("text", ""))
    band = slide.shapes.add_shape(
        _ROUNDED, Inches(_MARGIN_X), Inches(6.1), Inches(_BODY_W), Inches(0.85)
    )
    band.fill.solid()
    band.fill.fore_color.rgb = t.card_fill
    band.line.color.rgb = t.card_line
    band.line.width = Pt(1)
    band.shadow.inherit = False
    bar = slide.shapes.add_shape(
        1, Inches(_MARGIN_X + 0.08), Inches(6.22), Pt(5), Inches(0.61)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = t.accent
    bar.line.fill.background()
    size = _fit_or_report(
        text, page_id=page_id, element="callout",
        width_in=_BODY_W - 0.7, height_in=0.62,
        max_size=t.callout_size, min_size=14, family=theme.body_font,
        findings=result.findings,
    )
    box = _textbox(
        slide, Inches(_MARGIN_X + 0.35), Inches(6.14), Inches(_BODY_W - 0.7), Inches(0.78)
    )
    _set(box.text_frame.paragraphs[0], text, size=size, font=theme.body_font, color=t.text)


# -- charts -----------------------------------------------------------------


def _add_chart(
    slide, page_id: str, spec: dict, t, result: RenderResult,
    evidence: dict | None, *, x: float, y: float, w: float, h: float,
) -> None:
    chart_type = str(spec.get("type", "column")).lower()
    if chart_type not in _CHART_TYPES:
        result.findings.append(
            Finding(
                "deck_plan", "chart", "warn", "fail",
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
        Inches(x), Inches(y), Inches(w), Inches(h), data,
    )
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
                "deck_plan", "transition", "warn", "fail",
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
