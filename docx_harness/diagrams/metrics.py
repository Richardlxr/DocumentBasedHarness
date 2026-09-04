from __future__ import annotations

import os
import platform
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageFont

from ..errors import DocumentError

_WINDOWS_FONT_FILES = {
    "arial": ("arial.ttf",),
    "arial black": ("ariblk.ttf",),
    "calibri": ("calibri.ttf",),
    "georgia": ("georgia.ttf",),
    "microsoft yahei": ("msyh.ttc",),
    "segoe ui": ("segoeui.ttf",),
    "simhei": ("simhei.ttf",),
    "times new roman": ("times.ttf",),
}
_WINDOWS_FALLBACK_FAMILIES = ("Microsoft YaHei", "Segoe UI", "Arial")


def _conservative_width(text: str, size: int) -> float:
    return sum(
        (1.0 if unicodedata.east_asian_width(char) in {"W", "F"} else 0.52) * size
        for char in text
    )


def _windows_font_directories() -> tuple[Path, ...]:
    directories: list[Path] = []
    if windows := os.environ.get("WINDIR"):
        directories.append(Path(windows) / "Fonts")
    if local := os.environ.get("LOCALAPPDATA"):
        directories.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return tuple(directories)


def _windows_registry_fonts() -> tuple[tuple[str, str], ...]:
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


def _windows_font_path(family: str, bold: bool) -> Path | None:
    family_key = family.casefold()
    matches: list[tuple[int, str]] = []
    for name, value in _windows_registry_fonts():
        name_key = name.casefold()
        if family_key not in name_key:
            continue
        has_bold = any(token in name_key for token in ("bold", "semibold", "black", "heavy"))
        matches.append((int(has_bold != bold) * 1000 + len(name_key), value))
    for _rank, value in sorted(matches):
        registered = Path(os.path.expandvars(value))
        candidates = (registered,) if registered.is_absolute() else tuple(
            directory / registered for directory in _windows_font_directories()
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    for directory in _windows_font_directories():
        for filename in _WINDOWS_FONT_FILES.get(family_key, ()):
            candidate = directory / filename
            if candidate.is_file():
                return candidate
    return None


@dataclass(slots=True)
class FontMetrics:
    """Resolve, cache, measure, and deterministically wrap real font glyphs."""

    family: str
    _paths: dict[tuple[int, bool], Path] = field(default_factory=dict)
    _measurements: dict[tuple[str, int, bool], tuple[float, float]] = field(default_factory=dict)

    def _font(self, size: int, bold: bool = False):
        path = self._resolve(size, bold)
        return ImageFont.truetype(str(path), size=size)

    def _resolve(self, size: int, bold: bool) -> Path:
        key = (size, bold)
        if key in self._paths:
            return self._paths[key]
        configured = Path(self.family).expanduser()
        if configured.exists():
            self._paths[key] = configured
            return configured
        if platform.system() == "Windows":
            candidate = _windows_font_path(self.family, bold)
            if candidate is None:
                candidate = next(
                    (
                        fallback
                        for family in _WINDOWS_FALLBACK_FAMILIES
                        if family.casefold() != self.family.casefold()
                        if (fallback := _windows_font_path(family, bold)) is not None
                    ),
                    None,
                )
            if candidate is not None:
                self._paths[key] = candidate
                return candidate
        command = shutil.which("fc-match")
        if command:
            query = f"{self.family}:style={'Bold' if bold else 'Regular'}"
            try:
                completed = subprocess.run(
                    [command, "-f", "%{file}\n", query],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
            except subprocess.TimeoutExpired as error:
                raise DocumentError(f"font lookup timed out for '{self.family}'") from error
            candidate = Path(completed.stdout.splitlines()[0]) if completed.stdout.strip() else None
            if candidate is not None and candidate.exists():
                self._paths[key] = candidate
                return candidate
        raise DocumentError(
            f"diagram font '{self.family}' cannot be resolved; install it or use a font path"
        )

    def measure(self, text: str, size: int, bold: bool = False) -> tuple[float, float]:
        cache_key = (text, size, bold)
        cached = self._measurements.get(cache_key)
        if cached is not None:
            return cached
        font = self._font(size, bold)
        sample = text or "国"
        box = font.getbbox(sample)
        width = max(
            float(font.getlength(sample)),
            float(box[2] - box[0]),
            _conservative_width(sample, size),
        )
        line_box = font.getbbox("国Ag")
        height = float(line_box[3] - line_box[1]) * 1.18
        result = width * 1.06, height
        self._measurements[cache_key] = result
        return result

    def wrap(self, value: str, size: int, max_width: float, bold: bool = False) -> str:
        output: list[str] = []
        for raw_line in value.splitlines() or [""]:
            if self.measure(raw_line, size, bold)[0] <= max_width:
                output.append(raw_line)
                continue
            current = ""
            last_break = -1
            for char in raw_line:
                candidate = current + char
                if char.isspace() or char in "/、，；：,;:）)]":
                    last_break = len(candidate)
                if current and self.measure(candidate, size, bold)[0] > max_width:
                    split = last_break if last_break > 0 else len(current)
                    output.append(candidate[:split].rstrip())
                    current = candidate[split:].lstrip()
                    last_break = -1
                else:
                    current = candidate
            if current or not output:
                output.append(current.rstrip())
        return "\n".join(output)
