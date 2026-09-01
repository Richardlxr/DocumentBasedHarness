"""Deck renderer: projection/deck_plan.yaml → build/deck.pptx.

Pure code — no model in the loop at render time. Tier-2 capabilities:

- **Themes** (``deck.style.template``): palette + typography records from the
  registry; unknown names fall back with a finding. A brief that forbids dark
  backgrounds pins the render to a light theme deterministically.
- **Measured layout**: real glyph metrics (see ``metrics.py``) drive wrapping
  and font fitting; anything that cannot fit at the minimum size becomes a
  layout finding in the render report instead of silent overflow.
- **Evidence-backed charts** (``visual.chart``): values are pulled from the
  evidence store at render time by ``value_from`` references — chart numbers
  physically cannot drift from their source. Missing evidence fails loudly.
- **Slide transitions** (``deck.style.transition``): a safe OOXML whitelist
  (fade/push/wipe/cut). Per-element animation timing trees are deliberately
  deferred: they need verification in real PowerPoint before shipping.

``emphasis``/``reveal`` remain read-but-unconsumed semantic slots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
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

_SLIDE_W = Inches(13.333)
_SLIDE_H = Inches(7.5)
_LINE_SPACING = 1.25
_PT_PER_IN = 72.0


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


def _paint_background(slide, color: RGBColor) -> None:
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _textbox(slide, left, top, width, height) -> object:
    box = slide.shapes.add_textbox(left, top, width, height)
    box.text_frame.word_wrap = True
    return box


def _style_runs(paragraph, *, size: int, font: str, color: RGBColor, bold: bool = False) -> None:
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


# -- page kinds --------------------------------------------------------------


def _render_cover(slide, page: dict, theme: RenderTheme, result: RenderResult) -> None:
    t = theme.theme
    points = page.get("support_points", [])
    joined = "  ·  ".join(points)
    subtitle_lines = len(wrap_lines(joined, t.body_size, 11.3 * _PT_PER_IN, theme.body_font))
    size = _fit_or_report(
        page["title"], page_id=page["id"], element="title",
        width_in=11.3, height_in=2.4 - 0.35 * subtitle_lines,
        max_size=t.cover_title_size, min_size=26, family=theme.title_font,
        findings=result.findings,
    )
    box = _textbox(slide, Inches(1.0), Inches(2.4), Inches(11.3), Inches(2.4))
    box.text_frame.paragraphs[0].text = page["title"]
    _style_runs(
        box.text_frame.paragraphs[0], size=size, font=theme.title_font,
        color=t.text, bold=True,
    )
    if points:
        paragraph = box.text_frame.add_paragraph()
        paragraph.text = joined
        _style_runs(paragraph, size=t.body_size, font=theme.body_font, color=t.muted)


def _render_banner(slide, page: dict, theme: RenderTheme, result: RenderResult) -> None:
    t = theme.theme
    accent = slide.shapes.add_shape(1, Inches(0.9), Inches(2.35), Inches(1.2), Pt(6))
    accent.fill.solid()
    accent.fill.fore_color.rgb = t.accent
    accent.line.fill.background()
    points = page.get("support_points", [])
    body_lines = sum(
        len(wrap_lines(p, t.body_size, 11.3 * _PT_PER_IN, theme.body_font)) for p in points
    )
    size = _fit_or_report(
        page["title"], page_id=page["id"], element="title",
        width_in=11.3, height_in=2.2 - 0.32 * body_lines,
        max_size=t.banner_title_size, min_size=22, family=theme.title_font,
        findings=result.findings,
    )
    box = _textbox(slide, Inches(1.0), Inches(2.7), Inches(11.3), Inches(2.2))
    box.text_frame.paragraphs[0].text = page["title"]
    _style_runs(
        box.text_frame.paragraphs[0], size=size, font=theme.title_font,
        color=t.text, bold=True,
    )
    for point in points:
        paragraph = box.text_frame.add_paragraph()
        paragraph.text = point
        paragraph.space_before = Pt(10)
        _style_runs(paragraph, size=t.body_size, font=theme.body_font, color=t.muted)


def _render_content(
    slide, page: dict, run_root: Path, theme: RenderTheme,
    result: RenderResult, evidence: dict | None,
) -> None:
    t = theme.theme
    chart_spec = (page.get("visual") or {}).get("chart")

    size = _fit_or_report(
        page["title"], page_id=page["id"], element="title",
        width_in=11.5, height_in=1.5, max_size=t.content_title_size, min_size=20,
        family=theme.title_font, findings=result.findings,
    )
    title = _textbox(slide, Inches(0.9), Inches(0.55), Inches(11.5), Inches(1.5))
    title.text_frame.paragraphs[0].text = page["title"]
    _style_runs(
        title.text_frame.paragraphs[0], size=size, font=theme.title_font,
        color=t.text, bold=True,
    )

    body_width = 11.5
    if chart_spec is not None:
        _add_chart(slide, page, chart_spec, t, result, evidence)
        body_width = 5.2
    else:
        body_width = _add_figure(slide, page, run_root, theme, result) or body_width

    points = page.get("support_points", [])
    if points:
        body_size = _fit_points(
            points, page_id=page["id"], width_in=body_width, theme=theme, findings=result.findings
        )
        body = _textbox(slide, Inches(0.9), Inches(2.3), Inches(body_width), Inches(4.4))
        first = True
        for point in points:
            paragraph = body.text_frame.paragraphs[0] if first else body.text_frame.add_paragraph()
            first = False
            paragraph.text = "• " + point
            paragraph.space_after = Pt(10)
            _style_runs(paragraph, size=body_size, font=theme.body_font, color=t.text)


def _fit_points(
    points: list[str], *, page_id: str, width_in: float, theme: RenderTheme, findings: list[Finding]
) -> int:
    t = theme.theme
    for size in range(t.body_size, 13, -1):
        needed = sum(
            len(wrap_lines("• " + p, size, width_in * _PT_PER_IN, theme.body_font))
            * size * _LINE_SPACING + 10
            for p in points
        )
        if needed <= 4.4 * _PT_PER_IN:
            return size
    findings.append(
        Finding(
            "deck_plan", "layout", "warn", "fail",
            f"page {page_id} body points do not fit at 14pt — demote content to "
            f"notes/appendix (see stages/deck.md)",
            "deck_plan",
        )
    )
    return 14


# -- figures and charts ------------------------------------------------------


def _asset_entries(page: dict) -> list[dict]:
    return [
        item if isinstance(item, dict) else {"ref": item}
        for item in (page.get("visual") or {}).get("asset_refs", [])
    ]


def _add_figure(
    slide, page: dict, run_root: Path, theme: RenderTheme, result: RenderResult
) -> float | None:
    """Render the first existing image asset with its caption; returns used width."""
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
        slide.shapes.add_picture(str(image), Inches(6.4), Inches(2.2), width=Inches(6.2))
        caption = entry.get("caption")
        if caption:
            box = _textbox(slide, Inches(6.4), Inches(6.55), Inches(6.2), Inches(0.5))
            paragraph = box.text_frame.paragraphs[0]
            paragraph.alignment = PP_ALIGN.CENTER
            paragraph.text = caption
            _style_runs(
                paragraph, size=theme.theme.caption_size, font=theme.body_font,
                color=theme.theme.muted,
            )
        return 5.2
    return None


def _add_chart(
    slide, page: dict, spec: dict, t, result: RenderResult, evidence: dict | None
) -> None:
    chart_type = str(spec.get("type", "column")).lower()
    if chart_type not in _CHART_TYPES:
        result.findings.append(
            Finding(
                "deck_plan", "chart", "warn", "fail",
                f"page {page['id']} chart type '{chart_type}' unknown "
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
        item = items.get(ref)
        if item is None:
            raise RuntimeError(
                f"page {page['id']} chart references evidence '{ref}' which does not exist; "
                f"run `comh validate all`"
            )
        number = (item.get("value") or {}).get("number")
        if number is None:
            raise RuntimeError(
                f"page {page['id']} chart: evidence '{ref}' has no value.number; "
                f"charts may only plot structured data"
            )
        values.append(float(number))
        labels.append(str(entry.get("label", ref)))
        unit = (item.get("value") or {}).get("unit")
        if unit:
            units.add(str(unit))

    data = CategoryChartData()
    data.categories = labels
    series_name = str(spec.get("series_name") or ("; ".join(sorted(units)) or "value"))
    data.add_series(series_name, tuple(values))
    frame = slide.shapes.add_chart(
        _CHART_TYPES[chart_type], Inches(6.4), Inches(2.1), Inches(6.2), Inches(4.2), data
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
