"""Text body forms: the relation between items chooses the layout.

A text page used to have one realization — a vertical stack of cards — so a
sequence, four parallel findings, a claim with its conditions and a status
list all looked the same. Each form here is named after the *relation* the
author declares (``visual.arrangement``); the renderer owns the geometry.

Layout is a pure, measured function (``layout_form``) that returns positioned
pieces or raises ``FormFitError``. Type sizes are fixed theme tokens: a form
that does not fit fails with a source-oriented message instead of shrinking
text, so the validator can run the same function as a dry run before render.
The HTML surface renders the same items, addresses and copy (``form_html``).
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from .metrics import text_width, wrap_lines
from .theme import RenderTheme, contrast_ratio

# form -> (min items, max items)
FORMS: dict[str, tuple[int, int]] = {
    "steps": (2, 5),
    "grid": (4, 6),
    "statement": (2, 4),
    "qa": (2, 4),
    "definition": (2, 5),
    "status": (2, 6),
}
TONES = ("positive", "partial", "pending", "negative", "neutral")

_PAD = 0.05  # text box inner margin, inches
_LINE = 1.25
_BODY_X = 0.9
_BODY_W = 11.53


class FormFitError(ValueError):
    """Authored copy does not fit its form at the fixed type size."""


@dataclass(frozen=True, slots=True)
class Piece:
    """One positioned element. Colors name theme attributes; ``ink:<attr>``
    means the more legible of text/background on that fill."""

    address: str | None  # support_points[i]; None = decoration
    kind: str  # text | oval | rounded | rect
    x: float
    y: float
    w: float
    h: float
    text: str = ""
    size: int = 0
    color: str = "text"
    fill: str | None = None
    line: str | None = None
    dashed: bool = False
    bold: bool = False
    center: bool = False


def _parts(entry) -> tuple[str, str]:
    if isinstance(entry, dict):
        return str(entry.get("point", "")), str(entry.get("detail") or "")
    return str(entry), ""


def form_errors(page: dict) -> list[str]:
    """Structural rules for the text forms; geometry is checked by layout_form."""
    visual = page.get("visual") or {}
    arrangement = visual.get("arrangement", "split")
    points = page.get("support_points") or []
    errors = []
    for i, entry in enumerate(points):
        if not isinstance(entry, dict):
            continue
        if ("status" in entry or "tone" in entry) and arrangement != "status":
            errors.append(f"support_points[{i}] status/tone only render in the status arrangement")
        if entry.get("icon") and arrangement in FORMS:
            errors.append(
                f"support_points[{i}] icon does not render in the {arrangement} arrangement"
            )
    if arrangement not in FORMS:
        return errors
    low, high = FORMS[arrangement]
    carriers = [k for k in ("chart", "diagram", "asset_refs", "table") if visual.get(k)]
    if carriers or page.get("metric_cards"):
        errors.append(
            f"{arrangement} is a text body form; it takes no separate visual or metric cards"
        )
    if not low <= len(points) <= high:
        errors.append(f"{arrangement} requires {low}–{high} support_points, got {len(points)}")
    if arrangement == "grid" and len(points) == 5:
        errors.append("grid requires four or six support_points (2×2 or 3×2)")
    if arrangement in {"qa", "definition"}:
        for i, entry in enumerate(points):
            if not _parts(entry)[1].strip():
                what = "answer" if arrangement == "qa" else "explanation"
                errors.append(f"{arrangement} support_points[{i}] needs a detail ({what})")
    if arrangement == "status":
        for i, entry in enumerate(points):
            label = entry.get("status") if isinstance(entry, dict) else None
            if not isinstance(label, str) or not label.strip():
                errors.append(
                    f"status support_points[{i}] needs a visible status label "
                    "(the renderer does not invent status wording)"
                )
            tone = entry.get("tone", "neutral") if isinstance(entry, dict) else "neutral"
            if tone not in TONES:
                errors.append(
                    f"status support_points[{i}] tone '{tone}' is not one of {', '.join(TONES)}"
                )
    return errors


def ink_on(theme: RenderTheme, fill: str) -> str:
    """Text or background, whichever reads better on ``fill``."""
    t = theme.theme
    color = getattr(t, fill)
    return (
        "text"
        if contrast_ratio(t.text, color) >= contrast_ratio(t.background, color)
        else "background"
    )


class _Measure:
    def __init__(self, theme: RenderTheme, page_id: str, form: str):
        self.font = theme.body_font
        self.page_id = page_id
        self.form = form

    def height(self, text: str, size: int, width: float) -> float:
        if not text:
            return 0.0
        lines = wrap_lines(text, size, (width - 2 * _PAD) * 72, self.font)
        return len(lines) * size * _LINE / 72 + 2 * _PAD

    def fail(self, what: str, size: int) -> FormFitError:
        return FormFitError(
            f"page {self.page_id}: {self.form} {what} does not fit at {size}pt; "
            "shorten the copy, move detail to notes, or split the page"
        )


def layout_form(page: dict, theme: RenderTheme, top: float, bottom: float) -> list[Piece]:
    form = (page.get("visual") or {}).get("arrangement")
    if form not in FORMS:
        raise ValueError(f"unknown text form: {form}")
    errors = form_errors(page)
    if errors:
        raise ValueError(f"page {page.get('id')}: {'; '.join(errors)}")
    measure = _Measure(theme, page.get("id", "?"), form)
    points = page["support_points"]
    return _LAYOUTS[form](points, theme, measure, top, bottom - top)


def _spread(total: float, available: float, count: int, low: float, high: float) -> float:
    return max(low, min((available - total) / max(1, count - 1), high))


def _steps(points, theme, m, top, height):
    horizontal = _steps_horizontal(points, theme, m, top, height) if len(points) <= 4 else None
    return horizontal or _steps_vertical(points, theme, m, top, height)


def _steps_horizontal(points, theme, m, top, height):
    t = theme.theme
    n, gap, badge = len(points), 0.4, 0.52
    width = (_BODY_W - gap * (n - 1)) / n
    parts = [_parts(entry) for entry in points]
    # One shared baseline for every step's lead-in and explanation, so the
    # eye reads across the row instead of zig-zagging between columns.
    lead_h = max(m.height(point, t.body_size, width) for point, _ in parts)
    detail_h = max(m.height(detail, t.detail_size, width) for _, detail in parts)
    block_h = badge + 0.25 + lead_h + 0.06 + detail_h
    if block_h > height:
        return None  # too tall for columns; the vertical ladder has more room
    top += (height - block_h) * 0.3
    text_top = top + badge + 0.25
    pieces = []
    for i, (point, detail) in enumerate(parts):
        x = _BODY_X + i * (width + gap)
        address = f"support_points[{i}]"
        pieces.append(
            Piece(
                address,
                "oval",
                x,
                top,
                badge,
                badge,
                str(i + 1),
                t.detail_size,
                ink_on(theme, "accent"),
                fill="accent",
                bold=True,
                center=True,
            )
        )
        if i < n - 1:
            pieces.append(
                Piece(
                    None,
                    "rect",
                    x + badge + 0.12,
                    top + badge / 2 - 0.015,
                    width + gap - badge - 0.24,
                    0.03,
                    fill="card_line",
                )
            )
        pieces.append(
            Piece(address, "text", x, text_top, width, lead_h, point, t.body_size, bold=True)
        )
        if detail:
            pieces.append(
                Piece(
                    address,
                    "text",
                    x,
                    text_top + lead_h + 0.06,
                    width,
                    detail_h,
                    detail,
                    t.detail_size,
                    "muted",
                )
            )
    return pieces


def _steps_vertical(points, theme, m, top, height):
    t = theme.theme
    badge, indent = 0.5, 0.8
    width = _BODY_W - indent
    rows = []
    for entry in points:
        point, detail = _parts(entry)
        hp = m.height(point, t.body_size, width)
        hd = m.height(detail, t.detail_size, width)
        rows.append((point, detail, hp, hd, max(badge, hp + hd)))
    total = sum(r[4] for r in rows)
    if total + 0.12 * (len(rows) - 1) > height:
        raise m.fail("steps", t.body_size)
    gap = _spread(total, height, len(rows), 0.12, 0.45)
    pieces, y = [], top
    for i, (point, detail, hp, hd, row_h) in enumerate(rows):
        address = f"support_points[{i}]"
        pieces.append(
            Piece(
                address,
                "oval",
                _BODY_X,
                y,
                badge,
                badge,
                str(i + 1),
                t.detail_size,
                ink_on(theme, "accent"),
                fill="accent",
                bold=True,
                center=True,
            )
        )
        if i < len(rows) - 1:
            pieces.append(
                Piece(
                    None,
                    "rect",
                    _BODY_X + badge / 2 - 0.015,
                    y + badge + 0.06,
                    0.03,
                    row_h + gap - badge - 0.12,
                    fill="card_line",
                )
            )
        pieces.append(
            Piece(address, "text", _BODY_X + indent, y, width, hp, point, t.body_size, bold=True)
        )
        if detail:
            pieces.append(
                Piece(
                    address,
                    "text",
                    _BODY_X + indent,
                    y + hp,
                    width,
                    hd,
                    detail,
                    t.detail_size,
                    "muted",
                )
            )
        y += row_h + gap
    return pieces


def _grid(points, theme, m, top, height):
    t = theme.theme
    cols = 2 if len(points) == 4 else 3
    gap, pad = 0.3, 0.25
    width = (_BODY_W - gap * (cols - 1)) / cols
    cell_h = (height - gap) / 2
    pieces = []
    for i, entry in enumerate(points):
        point, detail = _parts(entry)
        x = _BODY_X + (i % cols) * (width + gap)
        y = top + (i // cols) * (cell_h + gap)
        inner = width - 2 * pad
        hp = m.height(point, t.body_size, inner)
        hd = m.height(detail, t.detail_size, inner)
        if 0.36 + hp + hd + pad > cell_h:
            raise m.fail(f"item {i + 1}", t.body_size)
        address = f"support_points[{i}]"
        pieces.append(
            Piece(address, "rounded", x, y, width, cell_h, fill="card_fill", line="card_line")
        )
        pieces.append(Piece(None, "rect", x + pad, y + 0.2, 0.5, 0.05, fill="accent"))
        pieces.append(
            Piece(address, "text", x + pad, y + 0.36, inner, hp, point, t.body_size, bold=True)
        )
        if detail:
            pieces.append(
                Piece(
                    address,
                    "text",
                    x + pad,
                    y + 0.36 + hp,
                    inner,
                    hd,
                    detail,
                    t.detail_size,
                    "muted",
                )
            )
    return pieces


def _statement(points, theme, m, top, height):
    t = theme.theme
    lead_size = t.body_size_wide + 4
    point, detail = _parts(points[0])
    text_w = _BODY_W - 0.35
    hp = m.height(point, lead_size, text_w)
    hd = m.height(detail, t.body_size, text_w)
    lead_h = hp + hd
    conditions = points[1:]
    gap = 0.35
    col_w = (_BODY_W - gap * (len(conditions) - 1)) / len(conditions)
    cond_rows = [
        (
            m.height(_parts(e)[0], t.detail_size, col_w),
            m.height(_parts(e)[1], t.detail_size, col_w),
        )
        for e in conditions
    ]
    cond_h = 0.14 + max(a + b for a, b in cond_rows)
    if lead_h + 0.45 + cond_h > height:
        raise m.fail("statement", lead_size)
    between = max(0.45, min(height - lead_h - cond_h, 1.1))
    pieces = [
        Piece("support_points[0]", "rect", _BODY_X, top + 0.04, 0.09, lead_h - 0.08, fill="accent"),
        Piece(
            "support_points[0]",
            "text",
            _BODY_X + 0.35,
            top,
            text_w,
            hp,
            point,
            lead_size,
            bold=True,
        ),
    ]
    if detail:
        pieces.append(
            Piece(
                "support_points[0]",
                "text",
                _BODY_X + 0.35,
                top + hp,
                text_w,
                hd,
                detail,
                t.body_size,
                "muted",
            )
        )
    y = top + lead_h + between
    for i, (entry, (cp, cd)) in enumerate(zip(conditions, cond_rows, strict=True)):
        address = f"support_points[{i + 1}]"
        x = _BODY_X + i * (col_w + gap)
        cond_point, cond_detail = _parts(entry)
        pieces.append(Piece(None, "rect", x, y, col_w, 0.03, fill="card_line"))
        pieces.append(
            Piece(
                address,
                "text",
                x,
                y + 0.14,
                col_w,
                cp,
                cond_point,
                t.detail_size,
                "accent",
                bold=True,
            )
        )
        if cond_detail:
            pieces.append(
                Piece(
                    address,
                    "text",
                    x,
                    y + 0.14 + cp,
                    col_w,
                    cd,
                    cond_detail,
                    t.detail_size,
                    "muted",
                )
            )
    return pieces


def _paired_rows(points, theme, m, top, height, *, left_ratio, left_color, marker):
    t = theme.theme
    col_gap = 0.4
    left_x = _BODY_X + (0.28 if marker else 0)
    left_w = _BODY_W * left_ratio - (left_x - _BODY_X)
    right_x = _BODY_X + _BODY_W * left_ratio + col_gap
    right_w = _BODY_W - (right_x - _BODY_X)
    rows = []
    for entry in points:
        point, detail = _parts(entry)
        hl = m.height(point, t.body_size, left_w)
        hr = m.height(detail, t.body_size, right_w)
        rows.append((point, detail, hl, hr, max(hl, hr)))
    total = sum(r[4] for r in rows)
    if total + 0.2 * (len(rows) - 1) > height:
        raise m.fail("rows", t.body_size)
    gap = _spread(total, height, len(rows), 0.2, 0.55)
    pieces, y = [], top
    for i, (point, detail, hl, hr, row_h) in enumerate(rows):
        address = f"support_points[{i}]"
        if marker:
            pieces.append(
                Piece(None, "rect", _BODY_X, y + 0.1, 0.06, min(hl, 0.5) - 0.1, fill="accent")
            )
        pieces.append(
            Piece(address, "text", left_x, y, left_w, hl, point, t.body_size, left_color, bold=True)
        )
        pieces.append(Piece(address, "text", right_x, y, right_w, hr, detail, t.body_size))
        if i < len(rows) - 1:
            pieces.append(
                Piece(None, "rect", _BODY_X, y + row_h + gap / 2, _BODY_W, 0.01, fill="card_line")
            )
        y += row_h + gap
    return pieces


def _qa(points, theme, m, top, height):
    return _paired_rows(
        points, theme, m, top, height, left_ratio=0.4, left_color="accent", marker=False
    )


def _definition(points, theme, m, top, height):
    return _paired_rows(
        points, theme, m, top, height, left_ratio=0.28, left_color="text", marker=True
    )


def status_style(tone: str) -> dict:
    """Tone → fill/line/dash; the visible label always carries the meaning."""
    return {
        "positive": {"fill": "accent", "line": None, "dashed": False},
        "partial": {"fill": "accent_soft", "line": "accent", "dashed": False},
        "pending": {"fill": "card_fill", "line": "muted", "dashed": True},
        "negative": {"fill": "text", "line": None, "dashed": False},
        "neutral": {"fill": "card_fill", "line": "card_line", "dashed": False},
    }[tone]


def _status(points, theme, m, top, height):
    t = theme.theme
    size = t.detail_size
    labels = [str(e.get("status", "")) for e in points]
    widest = max(text_width(label, size, m.font, bold=True) for label in labels) / 72
    pill_w = max(1.3, widest + 0.4)
    if pill_w > 2.8:
        raise m.fail("status label", size)
    pill_h = size * _LINE / 72 + 0.2
    text_x = _BODY_X + pill_w + 0.35
    text_w = _BODY_W - (text_x - _BODY_X)
    rows = []
    for entry in points:
        point, detail = _parts(entry)
        hp = m.height(point, t.body_size, text_w)
        hd = m.height(detail, t.detail_size, text_w)
        rows.append((entry, point, detail, hp, hd, max(pill_h, hp + hd)))
    total = sum(r[5] for r in rows)
    if total + 0.18 * (len(rows) - 1) > height:
        raise m.fail("rows", t.body_size)
    gap = _spread(total, height, len(rows), 0.18, 0.5)
    pieces, y = [], top
    for i, (entry, point, detail, hp, hd, row_h) in enumerate(rows):
        address = f"support_points[{i}]"
        style = status_style(entry.get("tone", "neutral"))
        ink = "text" if style["fill"] == "card_fill" else ink_on(theme, style["fill"])
        pieces.append(
            Piece(
                address,
                "rounded",
                _BODY_X,
                y + 0.02,
                pill_w,
                pill_h,
                labels[i],
                size,
                ink,
                fill=style["fill"],
                line=style["line"],
                dashed=style["dashed"],
                bold=True,
                center=True,
            )
        )
        pieces.append(Piece(address, "text", text_x, y, text_w, hp, point, t.body_size, bold=True))
        if detail:
            pieces.append(
                Piece(address, "text", text_x, y + hp, text_w, hd, detail, t.detail_size, "muted")
            )
        if i < len(rows) - 1:
            pieces.append(
                Piece(None, "rect", _BODY_X, y + row_h + gap / 2, _BODY_W, 0.01, fill="card_line")
            )
        y += row_h + gap
    return pieces


_LAYOUTS = {
    "steps": _steps,
    "grid": _grid,
    "statement": _statement,
    "qa": _qa,
    "definition": _definition,
    "status": _status,
}


# -- HTML surface -------------------------------------------------------------


def form_html(page: dict, fragment_attrs) -> str:
    """Same items, order and addresses as the PPTX layout; CSS owns geometry.

    ``fragment_attrs(address, base_class)`` returns the element's attribute
    string so reveal steps address the same support_points[i]."""
    form = page["visual"]["arrangement"]
    items = []
    for i, entry in enumerate(page.get("support_points") or []):
        point, detail = (html.escape(v) for v in _parts(entry))
        address = f"support_points[{i}]"
        attrs = fragment_attrs(address, f"form-item form-{form}-item")
        detail_html = f'<div class="form-detail">{detail}</div>' if detail else ""
        if form == "steps":
            body = (
                f'<span class="form-badge">{i + 1}</span>'
                f'<div class="form-text"><div class="form-point">{point}</div>{detail_html}</div>'
            )
        elif form == "status":
            tone = entry.get("tone", "neutral")
            label = html.escape(str(entry.get("status", "")))
            body = (
                f'<span class="form-pill tone-{tone}">{label}</span>'
                f'<div class="form-text"><div class="form-point">{point}</div>{detail_html}</div>'
            )
        elif form in {"qa", "definition"}:
            body = f'<div class="form-point">{point}</div><div class="form-answer">{detail}</div>'
        else:
            body = f'<div class="form-point">{point}</div>{detail_html}'
        items.append(f"<div{attrs}>{body}</div>")
    if form == "statement":
        lead, rest = items[0], items[1:]
        return (
            f'<div class="form form-statement">{lead}'
            f'<div class="form-conditions">{"".join(rest)}</div></div>'
        )
    count = len(items)
    return f'<div class="form form-{form}" data-count="{count}">{"".join(items)}</div>'


def form_css(theme: RenderTheme) -> str:
    t = theme.theme
    badge_ink = getattr(t, ink_on(theme, "accent"))
    tones = []
    for tone in TONES:
        style = status_style(tone)
        fill = getattr(t, style["fill"])
        ink = t.text if style["fill"] == "card_fill" else getattr(t, ink_on(theme, style["fill"]))
        border = (
            f"2px {'dashed' if style['dashed'] else 'solid'} #{getattr(t, style['line'])}"
            if style["line"]
            else "2px solid transparent"
        )
        tones.append(f".form-pill.tone-{tone}{{background:#{fill};color:#{ink};border:{border};}}")
    return (
        """
.form { margin-top:14px; }
.form-point { font-weight:700; font-size:var(--body-size); }
.form-detail { color:var(--muted); font-size:var(--detail-size); margin-top:4px; }
.form-steps { display:flex; gap:28px; }
.form-steps[data-count="5"] { flex-direction:column; gap:14px; }
.form-steps-item { flex:1; display:flex; flex-direction:column; gap:14px; position:relative; }
.form-steps[data-count="5"] .form-steps-item { flex-direction:row; align-items:flex-start; }
.form-steps:not([data-count="5"]) .form-steps-item:not(:last-child)::after { content:"";
  position:absolute; top:19px; left:52px; right:-16px; height:2px; background:var(--card-line); }
.form-badge { width:40px; height:40px; border-radius:50%; background:var(--accent);
  color:var(--badge-ink); display:flex; align-items:center; justify-content:center;
  font-weight:700; flex:none; }
.form-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:18px; }
.form-grid[data-count="6"] { grid-template-columns:repeat(3,1fr); }
.form-grid-item { background:var(--card-fill); border:1px solid var(--card-line);
  border-radius:12px; padding:16px 18px; }
.form-grid-item::before { content:""; display:block; width:40px; height:4px;
  background:var(--accent); margin-bottom:10px; }
.form-statement > .form-item:first-child { border-left:7px solid var(--accent);
  padding-left:22px; }
.form-statement > .form-item:first-child .form-point {
  font-size:calc(var(--body-size) + 6px); }
.form-conditions { display:flex; gap:26px; margin-top:34px; }
.form-conditions .form-item { flex:1; border-top:2px solid var(--card-line); padding-top:10px; }
.form-conditions .form-point { font-size:var(--detail-size); color:var(--accent); }
.form-qa-item, .form-definition-item { display:flex; gap:28px; padding:12px 0;
  border-bottom:1px solid var(--card-line); }
.form-qa-item:last-child, .form-definition-item:last-child,
.form-status-item:last-child { border-bottom:none; }
.form-qa-item .form-point { flex:0 0 38%; color:var(--accent); }
.form-definition-item .form-point { flex:0 0 26%; border-left:5px solid var(--accent);
  padding-left:12px; }
.form-answer { flex:1; font-size:var(--body-size); }
.form-status-item { display:flex; gap:22px; align-items:flex-start; padding:10px 0;
  border-bottom:1px solid var(--card-line); }
.form-pill { flex:none; min-width:110px; text-align:center; border-radius:999px;
  padding:4px 14px; font-weight:700; font-size:var(--detail-size); }
"""
        + f":root{{--badge-ink:#{badge_ink};}}"
        + "".join(tones)
    )
