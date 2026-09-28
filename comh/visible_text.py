"""Known reader-facing fields only. Never mistake notes or planning metadata for copy."""

from __future__ import annotations

import html
import re

from markdown_it import MarkdownIt


def diagram_texts(source: str) -> list[str]:
    """Labels in the supported flowchart subset; comments and styling directives are metadata."""
    source = "\n".join(
        line
        for line in source.splitlines()
        if not line.lstrip().startswith(("%%", "style ", "classDef ", "class "))
    )
    labels = re.findall(r"[\w]+\s*(?:\[([^\[\]]*)\]|\(([^()]*)\)|\{([^{}]*)\})", source)
    values = [next((v for v in group if v), "") for group in labels]
    values += re.findall(r"\|([^|\n]+)\|", source)
    return [html.unescape(re.sub(r"<[^>]+>", " ", v.strip(" \"'"))) for v in values if v]


def page_texts(page: dict) -> list[tuple[str, str]]:
    pairs = [(key, str(page.get(key, ""))) for key in ("title", "kicker")]
    for index, entry in enumerate(page.get("support_points") or []):
        for field in ("point", "detail", "status") if isinstance(entry, dict) else ("point",):
            text = entry.get(field, "") if isinstance(entry, dict) else entry
            suffix = "" if field == "point" else f".{field}"
            pairs.append((f"support_points[{index}]{suffix}", str(text or "")))
    for index, card in enumerate(page.get("metric_cards") or []):
        pairs.append((f"metric_cards[{index}].label", str(card.get("label", ""))))
    pairs.append(("callout", str((page.get("callout") or {}).get("text", ""))))
    visual = page.get("visual") or {}
    pairs.append(("visual.chart.title", str((visual.get("chart") or {}).get("title", ""))))
    table = visual.get("table") or {}
    for i, label in enumerate(table.get("columns", [])):
        pairs.append((f"visual.table.columns[{i}]", label))
    for i, row in enumerate(table.get("rows", [])):
        for j, cell in enumerate(row):
            value = (
                next((str(cell[k]) for k in ("text", "status", "missing") if k in cell), "")
                if isinstance(cell, dict)
                else cell
            )
            pairs.append((f"visual.table.rows[{i}][{j}]", value))
    pairs.append(("visual.table.note", str(table.get("note", ""))))
    for index, label in enumerate(visual.get("columns") or []):
        pairs.append((f"visual.columns[{index}]", str(label)))
    for index, series in enumerate((visual.get("chart") or {}).get("series") or []):
        pairs.append((f"visual.chart.series[{index}].label", str(series.get("label", ""))))
    for index, asset in enumerate(visual.get("asset_refs") or []):
        if isinstance(asset, dict):
            pairs.append((f"visual.asset_refs[{index}].caption", str(asset.get("caption", ""))))
    diagram = visual.get("diagram") or {}
    pairs.append(("visual.diagram.caption", str(diagram.get("caption", ""))))
    for index, label in enumerate(diagram_texts(diagram.get("mermaid", ""))):
        pairs.append((f"visual.diagram.labels[{index}]", label))
    return [(element, text) for element, text in pairs if text.strip()]


def report_texts(text: str) -> list[tuple[str, str]]:
    """Visible prose, headings and table cells; fenced code is not audience prose."""
    result = []
    for token in MarkdownIt("commonmark").enable("table").parse(text):
        if token.type == "inline":
            value = "".join(
                "\n" if t.type in {"softbreak", "hardbreak"} else t.content
                for t in token.children or []
                if t.type in {"text", "code_inline", "softbreak", "hardbreak"}
            )
            if value.strip():
                result.append((f"report line {(token.map or [0])[0] + 1}", value))
    return result
