"""Theme-package loading (increment 1a) and reveal semantics (increment 0)."""

from __future__ import annotations

from pathlib import Path

from comh.render.theme import available_themes, select_theme
from comh.validate import validate_reveal


def test_builtin_themes_load_from_yaml() -> None:
    themes = available_themes()
    assert {"tier1-light", "slate-tech", "midnight"} <= set(themes)
    assert themes["slate-tech"].is_light
    assert not themes["midnight"].is_light
    assert themes["slate-tech"].accent is not None
    assert themes["midnight"].body_size == 22  # sizes survive the yaml round trip


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
