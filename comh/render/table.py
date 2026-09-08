"""Evidence tables: identical cell values in editable PPTX and semantic HTML."""

from __future__ import annotations

import html

from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches, Pt

from .metrics import fit_box, wrap_lines
from .ooxml import set_east_asian_font


def table_rows(spec, evidence, page_id):
    from .deck import _evidence_number, _fmt

    items = {item["id"]: item for item in (evidence or {}).get("items", [])}
    rows = []
    for row in spec["rows"]:
        values = []
        for cell in row:
            if isinstance(cell, dict) and "value_from" in cell:
                number, unit = _evidence_number(items, cell["value_from"], page_id, "table cell")
                values.append(_fmt(number) + (f" {unit}" if unit else ""))
            else:
                values.append(cell["text"] if isinstance(cell, dict) else cell)
        rows.append(values)
    if any(len(row) != len(spec["columns"]) for row in rows):
        raise ValueError(f"page {page_id}: every table row must match its columns")
    return [spec["columns"], *rows]


def render_table(slide, spec, evidence, page_id, theme, *, x, y, w, h):
    rows = table_rows(spec, evidence, page_id)
    weights = spec.get("column_weights") or [1] * len(rows[0])
    if len(weights) != len(rows[0]) or any(v <= 0 for v in weights):
        raise ValueError(f"page {page_id}: table column_weights must be positive and match columns")
    widths = [w * v / sum(weights) for v in weights]
    size = theme.theme.body_size
    heights = [
        max(
            len(wrap_lines(text, size, width * 72 - 14, theme.body_font))
            for text, width in zip(row, widths, strict=False)
        )
        * size
        * 1.25
        / 72
        + 0.16
        for row in rows
    ]
    if sum(heights) > h:
        raise ValueError(
            f"page {page_id}: table does not fit at {size}pt; split rows or simplify text"
        )
    frame = slide.shapes.add_table(
        len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(sum(heights))
    )
    frame.name = "evidence-table"
    table = frame.table
    for column, width in zip(table.columns, widths, strict=False):
        column.width = Inches(width)
    for i, (row, height) in enumerate(zip(rows, heights, strict=False)):
        table.rows[i].height = Inches(height)
        for j, value in enumerate(row):
            fit = fit_box(
                value,
                width_pt=widths[j] * 72 - 14,
                height_pt=height * 72 - 10,
                max_size=size,
                min_size=size,
                family=theme.body_font,
            )
            if fit.overflows:
                raise ValueError(f"page {page_id}: table cell [{i},{j}] does not fit")
            cell = table.cell(i, j)
            cell.margin_left = cell.margin_right = Pt(7)
            cell.margin_top = cell.margin_bottom = Pt(5)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = theme.theme.accent_soft if i == 0 else theme.theme.background
            cell.text = value
            cell.text_frame.word_wrap = True
            for p in cell.text_frame.paragraphs:
                p.line_spacing = 1.15
                p.space_after = p.space_before = Pt(0)
                for run in p.runs:
                    run.font.size = Pt(size)
                    run.font.bold = i == 0
                    run.font.name = theme.body_font
                    run.font.color.rgb = theme.theme.text
                    set_east_asian_font(run, theme.body_font)
    return frame


def table_html(spec, evidence, page_id):
    rows = table_rows(spec, evidence, page_id)
    weights = spec.get("column_weights") or [1] * len(rows[0])
    columns = "".join(f'<col style="width:{v / sum(weights) * 100:.4f}%">' for v in weights)
    output = [f'<table class="evidence-table"><colgroup>{columns}</colgroup>']
    for i, row in enumerate(rows):
        tag = "th" if i == 0 else "td"
        scope = ' scope="col"' if i == 0 else ""
        output.append(
            "<tr>" + "".join(f"<{tag}{scope}>{html.escape(v)}</{tag}>" for v in row) + "</tr>"
        )
    return "".join(output) + "</table>"
