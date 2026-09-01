"""Token override / luminance pinning (increment 1b) and pptx animations
(increment 3, experimental)."""

from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile

from pptx import Presentation

from comh.render.deck import render_deck
from comh.render.theme import background_is_light, merge_tokens, render_theme, resolve_style
from comh.validate import validate_hard_constraints

EVIDENCE = {
    "items": [
        {"id": "E001", "kind": "datum", "content": "220ms",
         "value": {"number": 220, "unit": "ms"}, "source": {"source": "S", "locator": "x"}},
    ]
}


def test_merge_tokens_overrides_palette_and_sizes() -> None:
    base = resolve_style({"template": "slate-tech"}).theme
    assert str(base.accent) == "4F46E5"
    merged = merge_tokens(base, {"colors": {"accent": "B45309"}, "sizes": {"body": 26}})
    assert str(merged.accent) == "B45309"
    assert merged.body_size == 26
    assert merged.name == base.name  # same theme, new tokens


def test_dark_override_is_pinned_by_luminance() -> None:
    style = {
        "template": "slate-tech",
        "tokens_override": {"colors": {"background": "0F172A"}},
    }
    # without pinning the override applies (theme really is dark now)
    assert not background_is_light(resolve_style(style).theme.background)
    forced = resolve_style(style, allow_dark=False)
    assert forced.forced_light, "recoloring a light theme to midnight must be caught"
    assert background_is_light(forced.theme.background)


def test_render_theme_applies_override() -> None:
    theme = render_theme(
        {"template": "tier1-light", "tokens_override": {"colors": {"accent": "00897B"}}},
        "zh-CN",
    )
    assert str(theme.theme.accent) == "00897B"
    assert theme.title_font == "Microsoft YaHei"


def test_validator_flags_dark_override_under_no_dark_constraint() -> None:
    artifacts = {
        "brief": {"constraints": {"hard": ["不要黑底"]}},
        "deck_plan": {
            "deck": {
                "title": "t",
                "style": {
                    "template": "tier1-light",
                    "tokens_override": {"colors": {"background": "111827"}},
                },
                "pages": [],
            }
        },
    }
    findings = validate_hard_constraints(artifacts, None)
    assert any(
        f.severity == "error" and "effective deck background is dark" in f.detail
        for f in findings
    )


ANIM_PLAN = {
    "version": 1,
    "deck": {
        "title": "t",
        "style": {"animations": True},
        "pages": [
            {
                "id": "P01",
                "page_role": "content",
                "title": "标题",
                "support_points": [{"point": "a", "detail": "d"}],
                "metric_cards": [{"label": "v", "value_from": "E001"}],
                "callout": {"text": "c"},
                "reveal": [
                    {"elements": ["title"], "verb": "fade_in", "trigger": "click"},
                    {"elements": ["metric_cards[0]", "callout"], "verb": "appear",
                     "trigger": "click"},
                ],
            }
        ],
    },
}


def test_pptx_animations_inject_timing_xml(tmp_path: Path):
    result = render_deck(
        ANIM_PLAN, tmp_path, tmp_path / "anim.pptx", language="zh-CN", evidence=EVIDENCE
    )
    assert not result.findings, [f.detail for f in result.findings]
    shapes = result.shape_map["P01"]
    assert {"title", "support_points", "metric_cards[0]", "callout"} <= set(shapes)

    # round-trip: python-pptx can reopen the file (timing XML did not corrupt it)
    prs = Presentation(str(tmp_path / "anim.pptx"))
    assert len(prs.slides) == 1

    with ZipFile(tmp_path / "anim.pptx") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
    assert "<p:timing>" in slide_xml and 'nodeType="mainSeq"' in slide_xml
    targets = set(re.findall(r'<p:spTgt spid="(\d+)"', slide_xml))
    ids = {str(shapes["title"][0]), str(shapes["metric_cards[0]"][0]), str(shapes["callout"][0])}
    assert ids <= targets
    assert slide_xml.count('nodeType="clickEffect"') == 2
    assert 'filter="fade"' in slide_xml


def test_pptx_animations_off_by_default(tmp_path: Path):
    plan = {"version": 1, "deck": dict(ANIM_PLAN["deck"])}
    plan["deck"]["style"] = {}
    render_deck(plan, tmp_path, tmp_path / "off.pptx", evidence=EVIDENCE)
    with ZipFile(tmp_path / "off.pptx") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
    assert "<p:timing>" not in slide_xml


def test_rendered_shapes_stay_on_canvas(tmp_path: Path):
    """Regression for the unit-mixing bug that put an accent segment at
    y=-19048in: every shape of every slide must sit inside the canvas."""
    from pptx import Presentation

    result = render_deck(
        ANIM_PLAN, tmp_path, tmp_path / "bounds.pptx", language="zh-CN", evidence=EVIDENCE
    )
    assert not [f for f in result.findings if f.check == "geometry"], [
        f.detail for f in result.findings
    ]
    prs = Presentation(str(tmp_path / "bounds.pptx"))
    emu = 914400
    for slide in prs.slides:
        for shape in slide.shapes:
            assert shape.top / emu >= -0.06, f"{shape.name} off-canvas top"
            assert shape.left / emu >= -0.06, f"{shape.name} off-canvas left"
            assert (shape.top + shape.height) / emu <= 7.5 + 0.06
            assert (shape.left + shape.width) / emu <= 13.34


def test_geometry_checker_flags_overlap_and_off_canvas():
    from pptx import Presentation
    from pptx.util import Inches

    from comh.render.deck import RenderResult, _check_geometry

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    good = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
    good.name = "title"
    clash = slide.shapes.add_textbox(Inches(2), Inches(1.2), Inches(2), Inches(1))
    clash.name = "card:point[0]"
    lost = slide.shapes.add_textbox(Inches(1), Inches(-3), Inches(2), Inches(1))
    lost.name = "kicker"
    decor = slide.shapes.add_textbox(Inches(1.5), Inches(1.1), Inches(0.5), Inches(0.2))
    decor.name = "decor"  # overlaps both, but decor is exempt

    result = RenderResult(output=Path("x.pptx"), theme="t", transition=None)
    _check_geometry(prs, result)
    details = " | ".join(f.detail for f in result.findings)
    assert "overlaps 'card:point[0]'" in details or "overlaps 'title'" in details
    assert "'kicker' falls outside the canvas" in details
    assert len([f for f in result.findings if f.check == "geometry"]) == 2
