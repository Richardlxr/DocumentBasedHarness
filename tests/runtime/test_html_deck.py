"""HTML deck surface tests (reveal.js single-file output)."""

from __future__ import annotations

import re
from pathlib import Path

from comh.render.html_deck import render_html_deck

EVIDENCE = {
    "items": [
        {"id": "E001", "kind": "datum", "content": "220ms",
         "value": {"number": 220, "unit": "ms"}, "source": {"source": "S", "locator": "x"}},
        {"id": "E002", "kind": "datum", "content": "180ms",
         "value": {"number": 180, "unit": "ms"}, "source": {"source": "S", "locator": "x"}},
    ]
}

PLAN = {
    "version": 1,
    "deck": {
        "title": "测试 Deck",
        "style": {"template": "slate-tech", "transition": "fade"},
        "pages": [
            {"id": "P01", "page_role": "cover", "title": "封面", "support_points": ["副标题"]},
            {
                "id": "P02",
                "page_role": "content",
                "title": "标题 18.2%",
                "support_points": [
                    {"point": "加粗导语", "detail": "展开一行"},
                ],
                "metric_cards": [{"label": "P99", "value_from": "E001"}],
                "visual": {"chart": {"type": "column", "title": "P99", "series": [
                    {"label": "a", "value_from": "E001"},
                    {"label": "b", "value_from": "E002"},
                ]}},
                "callout": {"text": "结论条"},
                "notes": "讲稿",
                "reveal": [
                    {"elements": ["support_points[0]"], "verb": "fade_in", "trigger": "click"},
                    {"elements": ["visual"], "verb": "fade_in", "trigger": "click"},
                    {"elements": ["callout"], "verb": "fade_in", "trigger": "with_previous"},
                ],
                "emphasis": [{"elements": ["title"], "verb": "highlight"}],
            },
        ],
    },
}


def test_html_deck_single_file_with_fragments(tmp_path: Path):
    result = render_html_deck(
        PLAN, tmp_path, tmp_path / "deck.html", language="zh-CN", evidence=EVIDENCE
    )
    doc = (tmp_path / "deck.html").read_text(encoding="utf-8")

    assert result.theme == "slate-tech"
    assert doc.count("<section>") == 2
    assert "Reveal.initialize" in doc and 'transition:"fade"' in doc
    # reveal.js embedded: opens offline
    assert "cdn" not in doc.lower() and len(doc) > 100_000
    # fragments carry explicit indices; with_previous shares the previous index
    indices = sorted({int(i) for i in re.findall(r'data-fragment-index="(\d+)"', doc)})
    assert indices == [0, 1, 2]  # callout (with_previous) shares visual's index 1
    callout = re.search(r'<div class="callout fragment[^"]*" data-fragment-index="(\d+)"', doc)
    assert callout and callout.group(1) == "1"
    # evidence-backed cards and CSS bars
    assert "220 ms" in doc and re.search(r'class="card-value"', doc)
    assert len(re.findall(r'class="bar-fill"', doc)) == 2
    assert "结论条" in doc and "<aside class=\"notes\">讲稿</aside>" in doc
    assert "--accent" in doc  # theme tokens as CSS variables


def test_html_deck_line_chart_falls_back_to_table(tmp_path: Path):
    plan = {
        "version": 1,
        "deck": {
            "title": "t",
            "pages": [{
                "id": "P01", "page_role": "content", "title": "x",
                "visual": {"chart": {"type": "line", "series": [
                    {"label": "a", "value_from": "E001"},
                ]}},
            }],
        },
    }
    result = render_html_deck(plan, tmp_path, tmp_path / "line.html", evidence=EVIDENCE)
    doc = (tmp_path / "line.html").read_text(encoding="utf-8")
    assert "chart-table" in doc
    assert any("renders as a table" in f.detail for f in result.findings)
