"""HTML deck surface: deck_plan.yaml → single-file reveal.js HTML.

The same deck_plan drives this and the pptx renderer — animation here is
nearly free because reveal.js fragments execute the reveal/emphasis semantics
directly. The output is one self-contained HTML file (reveal.js and reveal.css
embedded, images inlined as data URIs) that opens offline in any browser.

Mapping (v1):
- reveal steps -> fragment classes with explicit data-fragment-index
  (click steps sequentially; with_previous shares the previous index;
  trigger=after is treated as sequential)
- verbs: appear -> "fragment", fade_in -> "fragment fade-in",
  emphasize/highlight -> "fragment highlight-current"
- charts: bar/column render as deterministic CSS bars from evidence values
  (offline, no JS chart lib); other types fall back to a data table
- diagrams/figures: inlined as data URIs from the PNG cache
- theme tokens -> CSS variables; style.transition -> reveal transition
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass, field
from pathlib import Path

from ..artifacts import Finding
from .theme import RenderTheme, render_theme

_WEB_DIR = Path(__file__).parent / "web"
_TRANSITION_MAP = {"fade": "fade", "push": "slide", "wipe": "slide", "cut": "none"}
_VERB_CLASSES = {
    "appear": "fragment",
    "fade_in": "fragment fade-in",
    "emphasize": "fragment highlight-current",
    "highlight": "fragment highlight-current",
}


@dataclass(slots=True)
class HtmlResult:
    output: Path
    theme: str
    transition: str | None
    findings: list[Finding] = field(default_factory=list)


def render_html_deck(
    plan: dict,
    run_root: Path,
    output: Path,
    *,
    language: str = "en",
    evidence: dict | None = None,
    allow_dark: bool = True,
) -> HtmlResult:
    theme = render_theme(
        plan.get("deck", {}).get("style"), language, allow_dark=allow_dark, run_root=run_root
    )
    result = HtmlResult(
        output=output, theme=theme.theme.name,
        transition=_TRANSITION_MAP.get(
            str((plan.get("deck", {}).get("style") or {}).get("transition", "")).lower()
        ),
    )
    if theme.fallback_reason:
        result.findings.append(
            Finding("deck_plan", "theme", "warn", "fail", theme.fallback_reason, "deck_plan")
        )

    sections = [
        _section(page, plan, theme, result, run_root, evidence) for page in plan["deck"]["pages"]
    ]
    document = _document(
        title=plan["deck"].get("title", "Deck"),
        theme=theme,
        transition=result.transition,
        sections="\n".join(sections),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return result


# -- section assembly -------------------------------------------------------


def _fragment_orders(page: dict) -> dict[str, tuple[str, int]]:
    """element address -> (fragment class, index). click steps advance the
    counter; with_previous reuses the previous step's index; after behaves
    sequentially (v1)."""
    orders: dict[str, tuple[str, int]] = {}
    counter = 0
    previous_index = 0
    for field_name in ("reveal", "emphasis"):
        for entry in page.get(field_name) or []:
            if not isinstance(entry, dict):
                continue
            verb = str(entry.get("verb", "fade_in"))
            classes = _VERB_CLASSES.get(verb, "fragment fade-in")
            if entry.get("trigger") == "with_previous":
                index = previous_index
            else:
                index = counter
                counter += 1
            previous_index = index
            for address in entry.get("elements") or []:
                orders[str(address)] = (classes, index)
    return orders


def _fragment_attrs(address: str, orders: dict[str, tuple[str, int]], base: str = "") -> str:
    """Merged class + fragment index for one element. Fragment classes merge
    into (never duplicate) the element's own class attribute."""
    step = orders.get(address)
    if step is None:
        return f' class="{base}"' if base else ""
    classes, index = step
    merged = f"{base} {classes}".strip()
    return f' class="{merged}" data-fragment-index="{index}"'


def _section(
    page: dict, plan: dict, theme: RenderTheme, result: HtmlResult,
    run_root: Path, evidence: dict | None,
) -> str:
    role = page.get("page_role", "content")
    orders = _fragment_orders(page)
    if role == "cover":
        body = _cover(page, orders)
    elif role in ("agenda", "section_divider", "closing"):
        body = _banner(page, orders)
    else:
        body = _content(page, theme, result, run_root, evidence, orders)
    notes = page.get("notes")
    aside = f'<aside class="notes">{html.escape(str(notes))}</aside>' if notes else ""
    return f"    <section>{body}{aside}</section>"


def _cover(page: dict, orders: dict) -> str:
    points = " · ".join(_point_text(entry)[0] for entry in page.get("support_points", []))
    subtitle = f'<p class="muted">{html.escape(points)}</p>' if points else ""
    return (
        f'<h1{_fragment_attrs("title", orders)}>{html.escape(page["title"])}</h1>{subtitle}'
    )


def _banner(page: dict, orders: dict) -> str:
    items = "".join(
        f'<li{_fragment_attrs(f"support_points[{i}]", orders, "muted")}>'
        f'{html.escape(_point_text(entry)[0])}</li>'
        for i, entry in enumerate(page.get("support_points", []))
    )
    return (
        f'<h1{_fragment_attrs("title", orders)}>{html.escape(page["title"])}</h1>'
        f'<ul class="plain">{items}</ul>'
    )


def _point_text(entry) -> tuple[str, str | None]:
    if isinstance(entry, dict):
        return str(entry.get("point", "")), entry.get("detail")
    return str(entry), None


def _content(
    page: dict, theme: RenderTheme, result: HtmlResult, run_root: Path,
    evidence: dict | None, orders: dict,
) -> str:
    parts: list[str] = [
        f'<h2{_fragment_attrs("title", orders)}>{html.escape(page["title"])}</h2>'
    ]

    cards = page.get("metric_cards") or []
    if cards:
        items = []
        for index, card in enumerate(cards):
            value_html = _card_value(card, evidence, result, page["id"])
            label = html.escape(str(card.get("label", "")))
            items.append(
                f'<div{_fragment_attrs(f"metric_cards[{index}]", orders, "card")}>'
                f'<div class="card-value">{value_html}</div>'
                f'<div class="card-label muted">{label}</div></div>'
            )
        parts.append(f'<div class="cards">{"".join(items)}</div>')

    visual = page.get("visual") or {}
    visual_html = ""
    if visual.get("chart"):
        chart_html = _css_chart(visual["chart"], evidence, result, page["id"], theme)
        if chart_html:
            visual_html = f'<div{_fragment_attrs("visual", orders)}>{chart_html}</div>'
    elif visual.get("diagram"):
        visual_html = _image_block(run_root, "visual", visual["diagram"], theme, orders)
    elif visual.get("asset_refs"):
        entries = [
            e if isinstance(e, dict) else {"ref": e} for e in visual["asset_refs"]
        ]
        existing = next((e for e in entries if (run_root / e["ref"]).is_file()), None)
        if existing:
            visual_html = _image_block(run_root, "visual", existing, theme, orders)
        else:
            result.findings.append(
                Finding(
                    "deck_plan", "asset", "warn", "fail",
                    f"page {page['id']} figure not found under the run root (html)",
                    "deck_plan",
                )
            )

    points_html = _points(page, orders, bool(visual_html))
    if visual_html:
        parts.append(f'<div class="columns"><div class="col">{points_html}</div>'
                     f'<div class="col">{visual_html}</div></div>')
    elif points_html:
        parts.append(points_html)

    callout = page.get("callout")
    if callout:
        text = html.escape(str(callout.get("text", "")))
        parts.append(
            f'<div{_fragment_attrs("callout", orders, "callout")}>'
            f'<span class="callout-bar"></span>{text}</div>'
        )
    return "".join(parts)


def _points(page: dict, orders: dict, has_visual: bool) -> str:
    items = []
    for index, entry in enumerate(page.get("support_points") or []):
        point, detail = _point_text(entry)
        fragment = _fragment_attrs(f"support_points[{index}]", orders, "point")
        detail_html = ""
        if detail:
            detail_html = f'<div class="detail muted">{html.escape(str(detail))}</div>'
        items.append(f'<div{fragment}><div class="point-line">'
                     f'• <b>{html.escape(point)}</b></div>{detail_html}</div>')
    if not items:
        return ""
    return f'<div class="points{" narrow" if has_visual else ""}">{"".join(items)}</div>'


def _card_value(card: dict, evidence: dict | None, result: HtmlResult, page_id: str) -> str:
    del result  # evidence lookups fail loud in _evidence_number itself
    from .deck import _evidence_number, _fmt

    items = {item["id"]: item for item in (evidence or {}).get("items", [])}
    number, unit = _evidence_number(items, str(card.get("value_from", "")), page_id, "metric card")
    value = _fmt(number) + (f" {unit}" if unit else "")
    return html.escape(value)


def _css_chart(spec: dict, evidence: dict | None, result: HtmlResult, page_id: str, theme) -> str:
    from .deck import _evidence_number, _fmt

    chart_type = str(spec.get("type", "column")).lower()
    items = {item["id"]: item for item in (evidence or {}).get("items", [])}
    entries = []
    for entry in spec.get("series", []):
        number, _ = _evidence_number(items, str(entry.get("value_from", "")), page_id, "chart")
        entries.append((str(entry.get("label", entry.get("value_from", ""))), number))
    if not entries:
        return ""
    title = f'<div class="chart-title muted">{html.escape(str(spec.get("title", "")))}</div>'
    if chart_type in ("bar", "column"):
        peak = max(abs(value) for _, value in entries) or 1.0
        bars = "".join(
            f'<div class="bar-row"><span class="bar-label">{html.escape(label)}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:'
            f'{abs(value) / peak * 100:.1f}%"></span></span>'
            f'<span class="bar-value">{html.escape(_fmt(value))}</span></div>'
            for label, value in entries
        )
        direction = "bar-row horizontal" if chart_type == "bar" else "bar-row"
        return f'<div class="chart">{title}<div class="bars {direction}s">{bars}</div></div>'
    # other chart types fall back to a table in v1 (offline, deterministic)
    rows = "".join(
        f'<tr><td>{html.escape(label)}</td><td>{_fmt(value)}</td></tr>'
        for label, value in entries
    )
    result.findings.append(
        Finding(
            "deck_plan", "chart", "info", "pass",
            f"page {page_id}: '{chart_type}' chart renders as a table in the HTML v1 surface",
            "deck_plan",
        )
    )
    return f'<div class="chart">{title}<table class="chart-table">{rows}</table></div>'


def _image_block(run_root: Path, address: str, entry: dict, theme, orders: dict) -> str:
    del theme
    ref = entry.get("ref")
    path = run_root / str(ref) if ref else _diagram_png_path(entry, run_root)
    if not path.is_file():
        return ""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    caption = entry.get("caption")
    caption_html = (
        f'<div class="caption muted">{html.escape(str(caption))}</div>' if caption else ""
    )
    return (
        f'<figure{_fragment_attrs(address, orders)}>'
        f'<img src="data:image/png;base64,{data}" alt="figure"/>{caption_html}</figure>'
    )


def _diagram_png_path(entry: dict, run_root: Path) -> Path:
    from .diagrams import diagram_png

    try:
        return diagram_png(str(entry.get("mermaid", "")), run_root)
    except Exception:  # noqa: BLE001 - validation reports the details
        return run_root / "build" / "diagrams" / "missing.png"


# -- document shell -----------------------------------------------------------


def _css(theme: RenderTheme) -> str:
    t = theme.theme
    variables = (
        f"--bg:{t.background}; --text:{t.text}; --muted:{t.muted}; --accent:{t.accent};"
        f"--accent-soft:{t.accent_soft}; --card-fill:{t.card_fill}; --card-line:{t.card_line};"
        f"--title-size:{t.content_title_size}px; --body-size:{t.body_size}px;"
        f"--detail-size:{t.detail_size}px; --card-value-size:{t.card_value_size}px;"
        f"--callout-size:{t.callout_size}px;"
    )
    return f":root{{{variables}}}" + """
html, body { margin:0; padding:0; background:var(--bg); color:var(--text);
  font-family:'Microsoft YaHei','Segoe UI',Calibri,sans-serif; }
.reveal { font-size:var(--body-size); }
.reveal h1 { font-size:calc(var(--title-size) * 1.25px); color:var(--text); }
.reveal h2 { font-size:var(--title-size); color:var(--text); text-align:left;
  border-bottom:5px solid var(--accent); display:inline-block; padding-bottom:8px;
  margin:0 0 28px 0; }
.reveal section { text-align:left; }
.muted { color:var(--muted); }
.plain { list-style:none; padding:0; }
.points { margin-top:12px; }
.points.narrow { max-width:46%; }
.point-line { font-size:var(--body-size); }
.detail { font-size:var(--detail-size); margin:4px 0 14px 18px; }
.cards { display:flex; gap:14px; margin:20px 0; }
.card { flex:1; background:var(--card-fill); border:1px solid var(--card-line);
  border-radius:12px; padding:16px 12px; text-align:center; }
.card-value { font-size:var(--card-value-size); font-weight:700; color:var(--accent); }
.card-label { font-size:13px; margin-top:6px; }
.columns { display:flex; gap:28px; align-items:flex-start; }
.col { flex:1; }
figure { margin:0; text-align:center; }
figure img { max-width:100%; max-height:58vh; }
.caption { font-size:13px; margin-top:8px; }
.callout { margin-top:26px; background:var(--card-fill); border:1px solid var(--card-line);
  border-radius:12px; padding:14px 18px; font-size:var(--callout-size); position:relative; }
.callout-bar { position:absolute; left:8px; top:12px; bottom:12px; width:5px;
  background:var(--accent); border-radius:3px; margin-right:12px; }
.chart-title { font-size:15px; margin-bottom:10px; text-align:center; }
.bar-row { display:flex; align-items:center; gap:10px; margin:10px 0; }
.bar-label { width:30%; text-align:right; font-size:15px; }
.bar-track { flex:1; background:var(--card-line); border-radius:6px; height:24px; }
.bar-fill { display:block; height:24px; border-radius:6px; background:var(--accent); }
.bar-value { width:14%; font-size:15px; }
.chart-table { border-collapse:collapse; margin:0 auto; }
.chart-table td { border:1px solid var(--card-line); padding:6px 16px; }
.reveal .fragment.highlight-current.visible { color:var(--accent); }
"""


def _document(title: str, theme: RenderTheme, transition: str | None, sections: str) -> str:
    reveal_css = (_WEB_DIR / "reveal.css").read_text(encoding="utf-8")
    reveal_js = (_WEB_DIR / "reveal.min.js").read_text(encoding="utf-8")
    transition_attr = f'transition:"{transition}",' if transition else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{html.escape(title)}</title>
<style>{reveal_css}</style>
<style>{_css(theme)}</style>
</head>
<body>
<div class="reveal">
<div class="slides">
{sections}
</div>
</div>
<script>{reveal_js}</script>
<script>
Reveal.initialize({{
  embedded: false,
  {transition_attr}
  hash: true,
  slideNumber: true,
  showNotes: false,
}});
</script>
</body>
</html>
"""
