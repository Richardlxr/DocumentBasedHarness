"""Icon vocabulary: 5,130 tabler-outline SVGs vendored under
``assets/vendor/tabler-outline`` (MIT, see LICENSE there), with a semantic
index (``icons-index.json``: name/category/tags) the model can search.

Libraries provide vocabulary, not boundaries: icons are optional decoration;
unknown names are validation findings, never crashes.

Surfaces:
- HTML: the recolored SVG is inlined directly (native, no rasterization).
- PPTX: python-pptx cannot embed SVG, so icons rasterize through headless
  Chrome into a PNG whose background is the exact card fill (visually
  seamless) and whose stroke is the recolored accent. Results are cached by
  content hash under ``build/icons/``. Set ``COMH_CHROME`` if Chrome is not
  in the default location.
"""

from __future__ import annotations

import hashlib
import html as html_module
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
ICON_DIR = _REPO_ROOT / "assets" / "vendor" / "tabler-outline"

_POSIX_BROWSER_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


def _installed_browser_candidates() -> tuple[Path, ...]:
    """Return common browser locations which installers do not add to PATH."""

    import os
    import platform

    if platform.system() != "Windows":
        return tuple(Path(value) for value in _POSIX_BROWSER_CANDIDATES)
    candidates: list[Path] = []
    roots = (
        (os.environ.get("PROGRAMFILES"), Path("Google/Chrome/Application/chrome.exe")),
        (os.environ.get("PROGRAMFILES(X86)"), Path("Google/Chrome/Application/chrome.exe")),
        (os.environ.get("LOCALAPPDATA"), Path("Google/Chrome/Application/chrome.exe")),
        (os.environ.get("PROGRAMFILES"), Path("Microsoft/Edge/Application/msedge.exe")),
        (os.environ.get("PROGRAMFILES(X86)"), Path("Microsoft/Edge/Application/msedge.exe")),
        (os.environ.get("LOCALAPPDATA"), Path("Microsoft/Edge/Application/msedge.exe")),
        (os.environ.get("LOCALAPPDATA"), Path("Chromium/Application/chrome.exe")),
    )
    candidates.extend(Path(root) / relative for root, relative in roots if root)
    return tuple(candidates)


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    import json

    path = ICON_DIR / "icons-index.json"
    if not path.is_file():
        return {}
    return {entry["name"]: entry for entry in json.loads(path.read_text(encoding="utf-8"))}


def icon_exists(name: str) -> bool:
    return name in _index()


def search_icons(keyword: str, limit: int = 20) -> list[dict]:
    """Semantic search over the index (name/category/tags) — the model-facing
    way to pick icons without opening files."""
    keyword = keyword.lower().strip()
    if not keyword:
        return []
    spaced = keyword.replace("-", " ")
    hits: list[tuple[int, dict]] = []
    for entry in _index().values():
        name = entry["name"]
        haystack = " ".join([name.replace("-", " "), entry["category"], *entry["tags"]])
        if keyword not in haystack and spaced not in haystack:
            continue
        if name == keyword:
            rank = 0
        elif name.startswith(keyword):
            rank = 1
        elif keyword in name:
            rank = 2
        else:
            rank = 3
        hits.append((rank, entry))
    hits.sort(key=lambda pair: pair[0])
    return [entry for _rank, entry in hits[:limit]]


def _normalize_color(color) -> str:
    return f"#{color}" if isinstance(color, str) and not str(color).startswith("#") else str(color)


def icon_svg(name: str, color) -> str:
    """Recolored inline SVG (stroke -> accent); raises KeyError for unknown
    names — callers validate first."""
    path = ICON_DIR / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"unknown icon '{name}'")
    svg = path.read_text(encoding="utf-8")
    return svg.replace('stroke="currentColor"', f'stroke="{_normalize_color(color)}"')


def _chrome() -> str | None:
    import os

    configured = os.environ.get("COMH_CHROME")
    if configured and Path(configured).exists():
        return configured
    for candidate in _installed_browser_candidates():
        if candidate.is_file():
            return str(candidate)
    return next(
        (
            found
            for command in (
                "chromium",
                "google-chrome",
                "chrome",
                "chromium.exe",
                "chrome.exe",
                "msedge",
                "msedge.exe",
            )
            if (found := shutil.which(command))
        ),
        None,
    )


def icon_png(name: str, *, color, background, px: int, run_root: Path) -> Path:
    """Rasterized icon cached under build/icons/. The PNG's background is the
    card fill color baked in (PowerPoint-safe; visually identical to alpha
    over that fill)."""
    fg = _normalize_color(color).lstrip("#").upper()
    bg = _normalize_color(background).lstrip("#").upper()
    digest = hashlib.sha256(f"{name}:{fg}:{bg}:{px}".encode()).hexdigest()[:12]
    cache_dir = run_root / "build" / "icons"
    png = cache_dir / f"{name}-{digest}.png"
    if png.is_file():
        return png

    chrome = _chrome()
    if chrome is None:
        raise RuntimeError(
            "icon rasterization needs a Chromium-based browser (set COMH_CHROME); "
            "icons otherwise render on the HTML surface only"
        )
    svg = icon_svg(name, f"#{fg}")
    svg = svg.replace('width="24"', f'width="{px}"').replace('height="24"', f'height="{px}"')
    page = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        f"html,body{{margin:0;padding:0;background:#{bg};}}"
        "svg{display:block;}"
        "</style></head><body>"
        f"<div style='width:{px}px;height:{px}px;display:flex;"
        f"align-items:center;justify-content:center;background:#{bg}'>"
        f"{svg}"
        "</div></body></html>"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    html_path = cache_dir / f".{name}-{digest}.html"
    html_path.write_text(page, encoding="utf-8")
    try:
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--screenshot={png}",
                f"--window-size={px},{px}",
                "--default-background-color=00000000",
                html_path.as_uri(),
            ],
            capture_output=True,
            check=True,
            timeout=60,
        )
    finally:
        html_path.unlink(missing_ok=True)
    if not png.is_file():
        raise RuntimeError(f"Chrome did not rasterize icon '{name}' (see stderr above)")
    return png


def html_safe(svg: str) -> str:
    """SVG string escaped for inline embedding in attributes-free contexts."""
    return html_module.escape(svg, quote=False)
