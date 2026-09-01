"""Measured text metrics for the deck layout engine.

Same philosophy as the vendored compiler's diagram chain: measure real glyphs,
wrap deterministically, and detect overflow before the file is opened — never
guess. Measurement resolves the actual TTF via fontconfig (fc-match), falling
back to a conservative character-width model when no resolver is available.
The measured family approximates the font PowerPoint will substitute; a small
margin is added to stay conservative.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import cache

from PIL import ImageFont

_MARGIN = 1.08  # measured widths are estimates of the final render; stay safe
_CJK_RANGES = (
    (0x2E80, 0x9FFF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF), (0x20000, 0x2FA1F)
)
_FALLBACK_LATIN = 0.52  # width in em for the fallback model
_FALLBACK_CJK = 1.0


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _CJK_RANGES)


@cache
def _font_path(family: str) -> str | None:
    configured = shutil.which("fc-match")
    if not configured:
        return None
    try:
        completed = subprocess.run(
            [configured, "-f", "%{file}\n", f"{family}:style=Regular"],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    first = completed.stdout.splitlines()[0].strip() if completed.stdout.strip() else ""
    return first or None


@cache
def _font(family: str, size_pt: int) -> ImageFont.FreeTypeFont | None:
    path = _font_path(family)
    if not path:
        return None
    try:
        return ImageFont.truetype(path, size=size_pt)
    except OSError:
        return None


@cache
def text_width(text: str, size_pt: int, family: str = "Microsoft YaHei") -> float:
    """Width of ``text`` in points (1 pt treated as 1 px at 72 dpi)."""
    font = _font(family, size_pt)
    if font is not None and text:
        return float(font.getlength(text)) * _MARGIN
    em = size_pt
    return sum((_FALLBACK_CJK if _is_cjk(c) else _FALLBACK_LATIN) * em for c in text) * _MARGIN


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
