"""Deck themes: vocabulary, not boundaries.

A theme is a small palette/typography record the renderer consumes. The
registry provides built-ins; ``deck.style.template`` may name one, miss it
(fallback + warn), or carry a free-form ``palette_hint`` a future model-driven
renderer could interpret. Unknown keys pass through untouched.

``is_light`` participates in hard-constraint enforcement: a brief that forbids
dark backgrounds pins every selectable theme to a light one.
"""

from __future__ import annotations

from dataclasses import dataclass

from pptx.dml.color import RGBColor


@dataclass(frozen=True, slots=True)
class DeckTheme:
    name: str
    is_light: bool
    background: RGBColor
    text: RGBColor
    muted: RGBColor
    accent: RGBColor
    accent_soft: RGBColor
    card_fill: RGBColor
    card_line: RGBColor
    cover_title_size: int = 44
    banner_title_size: int = 36
    content_title_size: int = 32
    body_size: int = 21
    body_size_wide: int = 24
    detail_size: int = 16
    caption_size: int = 13
    card_value_size: int = 34
    card_label_size: int = 13
    callout_size: int = 18
    latin_fonts: tuple[str, str] = ("Calibri", "Calibri")  # (title, body)
    notes: str = ""


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


TIER1_LIGHT = DeckTheme(
    name="tier1-light",
    is_light=True,
    background=_rgb("FFFFFF"),
    text=_rgb("1F2937"),
    muted=_rgb("6B7280"),
    accent=_rgb("2563EB"),
    accent_soft=_rgb("93C5FD"),
    card_fill=_rgb("F1F5F9"),
    card_line=_rgb("CBD5E1"),
)

SLATE_TECH = DeckTheme(
    name="slate-tech",
    is_light=True,
    background=_rgb("F1F5F9"),
    text=_rgb("0F172A"),
    muted=_rgb("64748B"),
    accent=_rgb("4F46E5"),
    accent_soft=_rgb("A5B4FC"),
    card_fill=_rgb("FFFFFF"),
    card_line=_rgb("CBD5E1"),
    latin_fonts=("Segoe UI", "Segoe UI"),
)

MIDNIGHT = DeckTheme(
    name="midnight",
    is_light=False,
    background=_rgb("0F172A"),
    text=_rgb("F8FAFC"),
    muted=_rgb("94A3B8"),
    accent=_rgb("38BDF8"),
    accent_soft=_rgb("0EA5E9"),
    card_fill=_rgb("1E293B"),
    card_line=_rgb("334155"),
    latin_fonts=("Aptos Display", "Aptos"),
    notes="dark theme; forbidden automatically when the brief pins a light background",
)

DEFAULT_THEME = TIER1_LIGHT

_REGISTRY: dict[str, DeckTheme] = {
    theme.name: theme for theme in (TIER1_LIGHT, SLATE_TECH, MIDNIGHT)
}


@dataclass(frozen=True, slots=True)
class ThemeChoice:
    theme: DeckTheme
    requested: str | None
    fallback_reason: str | None = None
    forced_light: bool = False


def select_theme(style: dict | None, *, allow_dark: bool = True) -> ThemeChoice:
    """Resolve ``deck.style.template`` into a theme with explicit fallbacks.

    ``allow_dark=False`` (the brief contains a dark-forbidding hard constraint)
    forces any dark selection to the default light theme — deterministically,
    not by prompt discipline.
    """
    requested = (style or {}).get("template")
    if requested is None:
        return ThemeChoice(DEFAULT_THEME, None)
    theme = _REGISTRY.get(str(requested))
    if theme is None:
        return ThemeChoice(
            DEFAULT_THEME,
            str(requested),
            fallback_reason=f"unknown template '{requested}'; using '{DEFAULT_THEME.name}'",
        )
    if not allow_dark and not theme.is_light:
        return ThemeChoice(DEFAULT_THEME, str(requested), forced_light=True)
    return ThemeChoice(theme, str(requested))


@dataclass(frozen=True, slots=True)
class RenderTheme:
    """Theme + language resolved into concrete fonts for one render."""

    theme: DeckTheme
    title_font: str
    body_font: str
    forced_light: bool = False
    fallback_reason: str | None = None


def fonts_for(theme: DeckTheme, language: str) -> tuple[str, str]:
    """(title, body) font families for a language: CJK gets CJK faces."""
    if language.lower().startswith("zh"):
        return "Microsoft YaHei", "Microsoft YaHei"
    return theme.latin_fonts


def render_theme(style: dict | None, language: str, *, allow_dark: bool = True) -> RenderTheme:
    choice = select_theme(style, allow_dark=allow_dark)
    title_font, body_font = fonts_for(choice.theme, language)
    return RenderTheme(
        theme=choice.theme,
        title_font=title_font,
        body_font=body_font,
        forced_light=choice.forced_light,
        fallback_reason=choice.fallback_reason,
    )
