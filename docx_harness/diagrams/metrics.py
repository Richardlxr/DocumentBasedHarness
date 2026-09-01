from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageFont

from ..errors import DocumentError


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
        width = max(float(font.getlength(sample)), float(box[2] - box[0]))
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
