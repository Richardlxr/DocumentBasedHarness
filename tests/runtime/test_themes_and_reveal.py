"""Theme-package loading (increment 1a) and reveal semantics (increment 0)."""

from __future__ import annotations

from pathlib import Path

from comh.render.theme import available_themes, select_theme
from comh.validate import validate_reveal


def test_builtin_themes_load_from_yaml() -> None:
    themes = available_themes()
    assert {"tier1-light", "slate-tech", "midnight", "poster-pop", "gallery-noir"} <= set(themes)
    assert themes["slate-tech"].is_light
    assert not themes["midnight"].is_light
    assert themes["slate-tech"].accent is not None
    assert themes["midnight"].body_size == 22  # sizes survive the yaml round trip


def test_creative_themes_reach_the_surfaces(tmp_path: Path) -> None:
    from comh.render.html_deck import render_html_deck

    themes = available_themes()
    pop, noir = themes["poster-pop"], themes["gallery-noir"]
    assert pop.is_light and not noir.is_light  # luminance pins apply to both directions
    assert pop.cover_title_size > themes["tier1-light"].cover_title_size  # poster scale
    assert noir.cjk_fonts[0] != pop.cjk_fonts[0]  # serif gallery vs sans poster

    plan = {
        "version": 1,
        "deck": {
            "title": "t",
            "style": {"template": "poster-pop"},
            "pages": [{"id": "P01", "page_role": "cover", "title": "发布",
                       "support_points": ["副标"]}],
        },
    }
    render_html_deck(plan, tmp_path, tmp_path / "pop.html", language="zh-CN")
    doc = (tmp_path / "pop.html").read_text(encoding="utf-8")
    assert "--accent:#E8452C" in doc and "--bg:#FFF6E5" in doc  # vermilion on cream
    # a dark-forbidding brief pins gallery-noir back to light, same as midnight
    pinned = select_theme({"template": "gallery-noir"}, allow_dark=False)
    assert pinned.forced_light and pinned.theme.is_light


def test_run_local_theme_takes_precedence(tmp_path: Path) -> None:
    run_themes = tmp_path / "themes" / "client-brand"
    run_themes.mkdir(parents=True)
    (run_themes / "theme.yaml").write_text(
        "name: client-brand\n"
        "is_light: true\n"
        "colors:\n"
        "  background: 'FFFBEB'\n"
        "  text: '292524'\n"
        "  muted: '78716C'\n"
        "  accent: 'B45309'\n"
        "  accent_soft: 'FCD34D'\n"
        "  card_fill: 'FFFFFF'\n"
        "  card_line: 'E7E5E4'\n",
        encoding="utf-8",
    )
    choice = select_theme({"template": "client-brand"}, run_root=tmp_path)
    assert choice.theme.name == "client-brand"
    assert str(choice.theme.accent) == "B45309"
    # defaults fill in for unspecified sizes
    assert choice.theme.content_title_size == 32
    # without the run root, the theme is unknown -> fallback
    fallback = select_theme({"template": "client-brand"})
    assert fallback.fallback_reason


def test_theme_choice_still_enforces_light(tmp_path: Path) -> None:
    choice = select_theme({"template": "midnight"}, allow_dark=False, run_root=tmp_path)
    assert choice.forced_light and choice.theme.is_light
    assert select_theme({"template": "midnight"}, allow_dark=True).theme.name == "midnight"


def test_broken_theme_file_is_skipped(tmp_path: Path) -> None:
    broken = tmp_path / "themes" / "broken"
    broken.mkdir(parents=True)
    (broken / "theme.yaml").write_text("name: broken\nis_light: true\n", encoding="utf-8")
    themes = available_themes(tmp_path)
    assert "broken" not in themes
    assert "tier1-light" in themes  # registry still usable


def _page(**overrides) -> dict:
    page = {
        "id": "P01",
        "page_role": "content",
        "title": "T",
        "support_points": [{"point": "a"}, {"point": "b"}],
        "metric_cards": [{"value_from": "E001"}],
        "visual": {"chart": {"series": [{"value_from": "E001"}]}},
        "callout": {"text": "c"},
        "reveal": [],
        "emphasis": [],
    }
    page.update(overrides)
    return page


def _artifacts(page: dict) -> dict:
    return {"deck_plan": {"deck": {"title": "t", "pages": [page]}}}


def test_valid_reveal_steps_pass() -> None:
    page = _page(
        reveal=[
            {"elements": ["support_points[0]"], "verb": "fade_in", "trigger": "click"},
            {"elements": ["visual", "callout"], "verb": "appear", "trigger": "after"},
        ],
        emphasis=[{"elements": ["title", "metric_cards[0]"], "verb": "highlight"}],
    )
    assert validate_reveal(_artifacts(page)) == []


def test_reveal_address_errors(tmp_path: Path) -> None:
    page = _page(
        reveal=[
            {"elements": ["support_points[5]"], "verb": "fade_in"},   # out of range
            {"elements": ["bogus[0]"], "verb": "fade_in"},            # unknown base
            {"elements": ["title[0]"], "verb": "fade_in"},            # indexed scalar
        ],
        emphasis=[{"elements": ["callout"]}],                          # ok
    )
    page.pop("callout")
    findings = validate_reveal(_artifacts(page))
    details = " | ".join(f.detail for f in findings)
    assert "support_points[5] out of range (2 points)" in details
    assert "unknown element 'bogus'" in details
    assert "'title' takes no index" in details
    assert "'callout' addressed but the page has none" in details
    assert all(f.severity == "error" for f in findings)


def test_reveal_visual_address_requires_visual() -> None:
    page = _page()
    page.pop("visual")
    page["reveal"] = [{"elements": ["visual"], "verb": "fade_in"}]
    findings = validate_reveal(_artifacts(page))
    assert any("no chart/diagram/figure" in f.detail for f in findings)


def test_unknown_verb_and_trigger_warn_legacy_strings_pass() -> None:
    page = _page(
        reveal=[
            {"elements": ["title"], "verb": "zoom_around", "trigger": "on_hover"},
            "先出基线，再出分区（自由备注）",
        ],
        emphasis=["P99 降低 18.2%（本页唯一大数字）"],
    )
    findings = validate_reveal(_artifacts(page))
    checks = {f.check for f in findings}
    assert "reveal-verb" in checks and "reveal-trigger" in checks
    assert all(f.severity == "warn" for f in findings)


def test_icon_validation_and_search() -> None:
    from comh.render.icons import icon_exists, icon_svg, search_icons
    from comh.validate import validate_visuals

    assert icon_exists("database") and not icon_exists("not-an-icon")
    assert any(e["name"] == "database" for e in search_icons("database", 5))
    svg = icon_svg("database", "4F46E5")
    assert 'stroke="#4F46E5"' in svg

    artifacts = {
        "evidence": {"items": []},
        "deck_plan": {"deck": {"title": "t", "pages": [{
            "id": "P01", "page_role": "content", "title": "x",
            "metric_cards": [{"value_from": "E001", "icon": "no-such-icon"}],
        }]}},
    }
    findings = validate_visuals(artifacts)
    assert any("unknown icon 'no-such-icon'" in f.detail and f.severity == "error"
               for f in findings)


def test_pptx_card_icons_render(tmp_path: Path):
    from pptx import Presentation

    from comh.render.deck import render_deck

    plan = {
        "version": 1,
        "deck": {"title": "t", "pages": [{
            "id": "P01", "page_role": "content", "title": "x",
            "metric_cards": [{"value_from": "E001", "icon": "gauge"}],
        }]},
    }
    evidence = {"items": [{"id": "E001", "kind": "datum", "content": "5",
                           "value": {"number": 5, "unit": "ms"},
                           "source": {"source": "S", "locator": "x"}}]}
    result = render_deck(plan, tmp_path, tmp_path / "i.pptx", evidence=evidence)
    assert not [f for f in result.findings if f.check == "icon"]
    prs = Presentation(str(tmp_path / "i.pptx"))
    assert any(sh.shape_type == 13 for sh in prs.slides[0].shapes), "icon embedded"


def test_malformed_yaml_is_a_finding_not_a_traceback(tmp_path: Path):
    from comh.artifacts import load_artifact
    from comh.scaffold import init_run

    run = init_run(tmp_path / "run", "yaml-run")
    (run / "evidence" / "evidence.yaml").write_text("version: 1\nitems: [broken", encoding="utf-8")
    data, findings = load_artifact(run, "evidence")
    assert data is None
    assert any("not valid YAML" in f.detail and f.severity == "error" for f in findings)


def test_agenda_overflow_gets_layout_finding(tmp_path: Path):
    from comh.render.deck import render_deck

    plan = {
        "version": 1,
        "deck": {"title": "t", "pages": [{
            "id": "P02", "page_role": "agenda", "title": "目录",
            "support_points": [f"事项{i}" for i in range(10)],
        }]},
    }
    result = render_deck(plan, tmp_path, tmp_path / "agenda.pptx")
    overflow = [f for f in result.findings if f.check == "layout" and "agenda rows" in f.detail]
    assert overflow and overflow[0].owning_artifact == "deck_plan"


def test_theme_from_pptx_extracts_brand(tmp_path: Path):
    from pptx import Presentation as BuildPresentation

    from comh.render.theme import resolve_style, theme_from_pptx

    template = tmp_path / "brand.pptx"
    BuildPresentation().save(str(template))
    out = theme_from_pptx(template, "brand", tmp_path)
    assert out.is_file()
    choice = resolve_style({"template": "brand"}, run_root=tmp_path)
    assert choice.theme.name == "brand"
    assert choice.theme.is_light  # default office template is light
    assert str(choice.theme.accent) == "4F81BD"  # office default template accent1
    assert choice.theme.cjk_fonts[0]  # CJK fonts present (default fallback ok)
