"""Deck themes: vocabulary, not boundaries.

Themes are data. They live as ``themes/<name>/theme.yaml`` — at the
repository root (the shipped built-ins) and optionally at
``<run_root>/themes/`` (run-local themes take precedence, so a run can carry
its own). ``select_theme`` resolves ``deck.style.template`` with explicit
fallbacks; unknown names fall back to the default with a finding.

``is_light`` participates in hard-constraint enforcement: a brief that forbids
dark backgrounds pins every selectable theme to a light one — deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pptx.dml.color import RGBColor

DEFAULT_THEME_NAME = "tier1-light"

_REPO_THEMES = Path(__file__).resolve().parents[2] / "themes"

_SIZE_FIELDS = {
    "cover_title": "cover_title_size",
    "banner_title": "banner_title_size",
    "content_title": "content_title_size",
    "body": "body_size",
    "body_wide": "body_size_wide",
    "detail": "detail_size",
    "caption": "caption_size",
    "card_value": "card_value_size",
    "card_label": "card_label_size",
    "callout": "callout_size",
    "kicker": "kicker_size",
    "footer": "footer_size",
    "index_number": "index_number_size",
}


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
    cover_title_size: int = 56
    banner_title_size: int = 40
    content_title_size: int = 32
    body_size: int = 22
    body_size_wide: int = 24
    detail_size: int = 17
    caption_size: int = 13
    card_value_size: int = 40
    card_label_size: int = 13
    callout_size: int = 18
    kicker_size: int = 13
    footer_size: int = 11
    index_number_size: int = 26
    latin_fonts: tuple[str, str] = ("Calibri", "Calibri")  # (title, body)
    notes: str = ""


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def _emergency_default() -> DeckTheme:
    return DeckTheme(
        name=DEFAULT_THEME_NAME,
        is_light=True,
        background=_rgb("FFFFFF"),
        text=_rgb("1F2937"),
        muted=_rgb("6B7280"),
        accent=_rgb("2563EB"),
        accent_soft=_rgb("93C5FD"),
        card_fill=_rgb("F1F5F9"),
        card_line=_rgb("CBD5E1"),
    )


def load_theme(path: Path) -> DeckTheme:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    colors = data.get("colors") or {}
    sizes = data.get("sizes") or {}
    fonts = data.get("fonts") or {}
    latin = list(fonts.get("latin") or []) + ["Calibri", "Calibri"]
    kwargs = {_SIZE_FIELDS[key]: int(value) for key, value in sizes.items() if key in _SIZE_FIELDS}
    return DeckTheme(
        name=str(data["name"]),
        is_light=bool(data["is_light"]),
        background=_rgb(colors["background"]),
        text=_rgb(colors["text"]),
        muted=_rgb(colors["muted"]),
        accent=_rgb(colors["accent"]),
        accent_soft=_rgb(colors["accent_soft"]),
        card_fill=_rgb(colors["card_fill"]),
        card_line=_rgb(colors["card_line"]),
        latin_fonts=(str(latin[0]), str(latin[1])),
        notes=str(data.get("notes", "")),
        **kwargs,
    )


@lru_cache(maxsize=8)
def _registry(repo_themes: str, run_themes: str | None) -> dict[str, DeckTheme]:
    """Load themes; run-local directory wins over the repository directory."""
    themes: dict[str, DeckTheme] = {}
    directories = [Path(repo_themes)]
    if run_themes:
        directories.insert(0, Path(run_themes))
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*/theme.yaml")):
            try:
                theme = load_theme(path)
            except (KeyError, ValueError, yaml.YAMLError):
                continue  # a broken theme file must not take the renderer down
            themes[theme.name] = theme
    if not themes:
        default = _emergency_default()
        themes[default.name] = default
    return themes


def available_themes(run_root: Path | None = None) -> dict[str, DeckTheme]:
    run_themes = str((run_root / "themes").resolve()) if run_root else None
    return _registry(str(_REPO_THEMES), run_themes)


@dataclass(frozen=True, slots=True)
class ThemeChoice:
    theme: DeckTheme
    requested: str | None
    fallback_reason: str | None = None
    forced_light: bool = False


def select_theme(
    style: dict | None, *, allow_dark: bool = True, run_root: Path | None = None
) -> ThemeChoice:
    """Resolve ``deck.style.template`` into a theme with explicit fallbacks.

    ``allow_dark=False`` (the brief contains a dark-forbidding hard constraint)
    forces any dark selection to the default light theme — deterministically,
    not by prompt discipline.
    """
    registry = available_themes(run_root)
    default = registry.get(DEFAULT_THEME_NAME) or next(iter(registry.values()))
    requested = (style or {}).get("template")
    if requested is None:
        return ThemeChoice(default, None)
    theme = registry.get(str(requested))
    if theme is None:
        return ThemeChoice(
            default,
            str(requested),
            fallback_reason=f"unknown template '{requested}'; using '{default.name}'",
        )
    if not allow_dark and not theme.is_light:
        return ThemeChoice(default, str(requested), forced_light=True)
    return ThemeChoice(theme, str(requested))


def background_is_light(color: RGBColor) -> bool:
    """Perceived luminance test (ITU-R 601 weights) on a background color."""
    r, g, b = (int(str(color)[i : i + 2], 16) for i in (0, 2, 4))
    return (299 * r + 587 * g + 114 * b) / 1000 >= 128


def merge_tokens(theme: DeckTheme, override: dict | None) -> DeckTheme:
    """Apply ``deck.style.tokens_override`` (same shape as theme.yaml sections)
    on top of a theme. Colors accept hex strings; sizes accept ints; fonts
    accept [title, body]. Unknown keys are ignored — tokens are vocabulary."""
    if not override:
        return theme
    import dataclasses

    changes: dict = {}
    colors = override.get("colors") or {}
    for key in ("background", "text", "muted", "accent", "accent_soft", "card_fill", "card_line"):
        if key in colors:
            changes[key] = _rgb(str(colors[key]).lstrip("#").upper())
    sizes = override.get("sizes") or {}
    for key, field_name in _SIZE_FIELDS.items():
        if key in sizes:
            changes[field_name] = int(sizes[key])
    fonts = override.get("fonts") or {}
    if "latin" in fonts and isinstance(fonts["latin"], (list, tuple)) and fonts["latin"]:
        latin = [str(f) for f in fonts["latin"]] + ["Calibri", "Calibri"]
        changes["latin_fonts"] = (latin[0], latin[1])
    return dataclasses.replace(theme, **changes) if changes else theme


def resolve_style(
    style: dict | None, *, allow_dark: bool = True, run_root: Path | None = None
) -> ThemeChoice:
    """Template selection + token override + luminance-based light pinning.

    This is the single resolution path shared by the renderer and the
    validator: a brief that forbids dark backgrounds pins the *effective*
    background (after overrides), not just the template name — recoloring a
    light theme to midnight via tokens_override is caught deterministically.
    """
    style = style or {}
    choice = select_theme(style, allow_dark=allow_dark, run_root=run_root)
    if choice.forced_light:
        return choice
    merged = merge_tokens(choice.theme, style.get("tokens_override"))
    if not allow_dark and not background_is_light(merged.background):
        # the override made the effective background dark; the pin wins, so the
        # whole override is dropped (not partially applied) and the original
        # light theme renders
        return ThemeChoice(choice.theme, choice.requested, forced_light=True)
    return ThemeChoice(
        theme=merged,
        requested=choice.requested,
        fallback_reason=choice.fallback_reason,
    )


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


def render_theme(
    style: dict | None,
    language: str,
    *,
    allow_dark: bool = True,
    run_root: Path | None = None,
) -> RenderTheme:
    choice = resolve_style(style, allow_dark=allow_dark, run_root=run_root)
    title_font, body_font = fonts_for(choice.theme, language)
    return RenderTheme(
        theme=choice.theme,
        title_font=title_font,
        body_font=body_font,
        forced_light=choice.forced_light,
        fallback_reason=choice.fallback_reason,
    )
