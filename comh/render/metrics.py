"""Measured text metrics for the deck layout engine.

Same philosophy as the vendored compiler's diagram chain: measure real glyphs,
wrap deterministically, and detect overflow before the file is opened — never
guess. Measurement resolves the actual TTF via fontconfig (fc-match), falling
back to a conservative character-width model when no resolver is available.
The measured family approximates the font PowerPoint will substitute; a small
margin is added to stay conservative.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PIL import ImageFont

_MARGIN = 1.08  # measured widths are estimates of the final render; stay safe
_FALLBACK_LATIN = 0.52  # width in em for the fallback model
_FALLBACK_CJK = 1.0
FIXED_TEXT_SIZES = ContextVar("fixed_text_sizes", default=False)

_WINDOWS_FONT_FILES = {
    "aptos": ("aptos.ttf",),
    "aptos display": ("aptos-display.ttf", "aptos.ttf"),
    "arial": ("arial.ttf",),
    "arial black": ("ariblk.ttf",),
    "calibri": ("calibri.ttf",),
    "georgia": ("georgia.ttf",),
    "microsoft yahei": ("msyh.ttc",),
    "segoe ui": ("segoeui.ttf",),
    "simhei": ("simhei.ttf",),
    "times new roman": ("times.ttf",),
}


@contextmanager
def fixed_text_sizes():
    """A style-template build must report excess content instead of shrinking its typography."""
    token = FIXED_TEXT_SIZES.set(True)
    try:
        yield
    finally:
        FIXED_TEXT_SIZES.reset(token)


def _is_cjk(char: str) -> bool:
    return unicodedata.east_asian_width(char) in {"W", "F"}


def _conservative_width(text: str, size_pt: int) -> float:
    return sum(
        (_FALLBACK_CJK if _is_cjk(char) else _FALLBACK_LATIN) * size_pt for char in text
    )


def _windows_font_directories() -> tuple[Path, ...]:
    directories: list[Path] = []
    if windows := os.environ.get("WINDIR"):
        directories.append(Path(windows) / "Fonts")
    if local := os.environ.get("LOCALAPPDATA"):
        directories.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return tuple(directories)


def _windows_registry_fonts() -> tuple[tuple[str, str], ...]:
    """Read system and per-user font registrations without importing winreg elsewhere."""

    try:
        import winreg
    except ImportError:
        return ()
    entries: list[tuple[str, str]] = []
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                index = 0
                while True:
                    try:
                        name, value, _kind = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    if isinstance(value, str):
                        entries.append((name, value))
                    index += 1
        except OSError:
            continue
    return tuple(entries)


def _registered_windows_font_path(family: str, bold: bool, italic: bool) -> str | None:
    family_key = family.casefold()
    matches: list[tuple[int, str]] = []
    for name, value in _windows_registry_fonts():
        name_key = name.casefold()
        if family_key not in name_key:
            continue
        has_bold = any(token in name_key for token in ("bold", "semibold", "black", "heavy"))
        has_italic = any(token in name_key for token in ("italic", "oblique"))
        style_penalty = int(has_bold != bold) + int(has_italic != italic)
        matches.append((style_penalty * 1000 + len(name_key), value))
    for _rank, value in sorted(matches):
        registered = Path(os.path.expandvars(value))
        candidates = (registered,) if registered.is_absolute() else tuple(
            directory / registered for directory in _windows_font_directories()
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def _windows_font_path(family: str, bold: bool, italic: bool) -> str | None:
    if registered := _registered_windows_font_path(family, bold, italic):
        return registered
    filenames = _WINDOWS_FONT_FILES.get(family.casefold(), ())
    for directory in _windows_font_directories():
        for filename in filenames:
            candidate = directory / filename
            if candidate.is_file():
                return str(candidate)
    return None


@cache
def _font_path(family: str, bold: bool = False, italic: bool = False) -> str | None:
    if platform.system() == "Windows":
        return _windows_font_path(family, bold, italic)
    configured = shutil.which("fc-match")
    if not configured:
        return None
    try:
        style = " ".join(s for s, enabled in (("Bold", bold), ("Italic", italic)) if enabled)
        completed = subprocess.run(
            [configured, "-f", "%{file}\n", f"{family}:style={style or 'Regular'}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    first = completed.stdout.splitlines()[0].strip() if completed.stdout.strip() else ""
    return first or None


@cache
def _font(
    family: str, size_pt: int, bold: bool = False, italic: bool = False
) -> ImageFont.FreeTypeFont | None:
    path = _font_path(family, bold, italic)
    if not path:
        return None
    try:
        return ImageFont.truetype(path, size=size_pt)
    except OSError:
        return None


def font_resolution(family: str, *, bold: bool = False, italic: bool = False) -> dict:
    """Record measurement substitution; this does not identify the presentation player's font."""
    font = _font(family, 24, bold, italic)
    actual = font.getname()[0] if font is not None else None
    return {
        "requested": family,
        "measurement_family": actual,
        "measurement_file": _font_path(family, bold, italic),
        "requested_style": {"bold": bold, "italic": italic},
        "substitution": actual is None or actual.casefold() != family.casefold(),
        "method": (
            "Windows font lookup/Pillow"
            if font is not None and platform.system() == "Windows"
            else "fontconfig/Pillow"
            if font is not None
            else "conservative character widths"
        ),
        "player_font": "unverified",
    }


@cache
def text_width(
    text: str,
    size_pt: int,
    family: str = "Microsoft YaHei",
    *,
    bold: bool = False,
    italic: bool = False,
) -> float:
    """Width of ``text`` in points (1 pt treated as 1 px at 72 dpi)."""
    font = _font(family, size_pt, bold, italic)
    conservative = _conservative_width(text, size_pt)
    if font is not None and text:
        # Fontconfig may substitute a font without the requested CJK glyphs. Its tofu box is
        # often much narrower than the Office glyph, so never let real-font measurement be less
        # conservative than the language-aware fallback model.
        return max(float(font.getlength(text)), conservative) * _MARGIN
    return conservative * _MARGIN


def wrap_lines(
    text: str, size_pt: int, max_width_pt: float, family: str = "Microsoft YaHei"
) -> list[str]:
    """Deterministic greedy wrap. Explicit newlines are honored."""
    lines: list[str] = []
    for raw in text.splitlines() or [""]:
        current = ""
        for char in raw:
            if text_width(current + char, size_pt, family) <= max_width_pt or not current:
                current += char
            else:
                lines.append(current)
                current = char
        lines.append(current)
    return lines


@dataclass(frozen=True, slots=True)
class FitResult:
    font_size: int
    lines: int
    overflows: bool
    widest_line_pt: float


def fit_box(
    text: str,
    *,
    width_pt: float,
    height_pt: float,
    max_size: int,
    min_size: int,
    line_spacing: float = 1.25,
    family: str = "Microsoft YaHei",
) -> FitResult:
    """Largest font size in [min, max] whose wrapped text fits the box.

    Never silently shrinks below ``min_size``: the result is reported as
    overflowing so the caller can surface a layout finding.
    """
    best = FitResult(min_size, 0, True, 0.0)
    for size in range(max_size, min_size - 1, -1):
        lines = wrap_lines(text, size, width_pt, family)
        widest = max((text_width(line, size, family) for line in lines), default=0.0)
        needed = len(lines) * size * line_spacing
        if needed <= height_pt and widest <= width_pt:
            return FitResult(size, len(lines), False, widest)
        best = FitResult(size, len(lines), needed > height_pt, widest)
    return best
