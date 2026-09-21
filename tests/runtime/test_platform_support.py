from __future__ import annotations

from pathlib import Path

from comh.render import icons, metrics
from docx_harness.diagrams import metrics as diagram_metrics


class _NarrowMissingGlyphFont:
    def getlength(self, text: str) -> float:
        return float(len(text))

    def getbbox(self, text: str) -> tuple[int, int, int, int]:
        return (0, 0, len(text), 10)


def test_browser_discovery_finds_standard_windows_chrome(tmp_path: Path, monkeypatch) -> None:
    program_files = tmp_path / "Program Files"
    chrome = program_files / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.touch()
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setenv("PROGRAMFILES", str(program_files))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("COMH_CHROME", raising=False)
    monkeypatch.setattr(icons.shutil, "which", lambda command: None)

    assert icons._chrome() == str(chrome)


def test_browser_discovery_accepts_edge_from_path(monkeypatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("COMH_CHROME", raising=False)
    monkeypatch.setattr(
        icons.shutil,
        "which",
        lambda command: r"C:\Browsers\msedge.exe" if command == "msedge.exe" else None,
    )

    assert icons._chrome() == r"C:\Browsers\msedge.exe"


def test_deck_metrics_resolve_registered_windows_font(tmp_path: Path, monkeypatch) -> None:
    fonts = tmp_path / "Windows" / "Fonts"
    regular = fonts / "msyh.ttc"
    bold = fonts / "msyhbd.ttc"
    fonts.mkdir(parents=True)
    regular.touch()
    bold.touch()
    monkeypatch.setenv("WINDIR", str(tmp_path / "Windows"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(
        metrics,
        "_windows_registry_fonts",
        lambda: (
            ("Microsoft YaHei (TrueType)", "msyh.ttc"),
            ("Microsoft YaHei Bold (TrueType)", "msyhbd.ttc"),
        ),
    )

    assert metrics._windows_font_path("Microsoft YaHei", False, False) == str(regular)
    assert metrics._windows_font_path("Microsoft YaHei", True, False) == str(bold)


def test_diagram_metrics_resolve_registered_windows_font(tmp_path: Path, monkeypatch) -> None:
    fonts = tmp_path / "Windows" / "Fonts"
    regular = fonts / "simhei.ttf"
    fonts.mkdir(parents=True)
    regular.touch()
    monkeypatch.setattr(diagram_metrics.platform, "system", lambda: "Windows")
    monkeypatch.setenv("WINDIR", str(tmp_path / "Windows"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(
        diagram_metrics,
        "_windows_registry_fonts",
        lambda: (("SimHei (TrueType)", "simhei.ttf"),),
    )

    assert diagram_metrics.FontMetrics("SimHei")._resolve(13, False) == regular


def test_diagram_metrics_fall_back_to_available_windows_font(tmp_path: Path, monkeypatch) -> None:
    fonts = tmp_path / "Windows" / "Fonts"
    fallback = fonts / "segoeui.ttf"
    fonts.mkdir(parents=True)
    fallback.touch()
    monkeypatch.setattr(diagram_metrics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagram_metrics, "_windows_registry_fonts", lambda: ())
    monkeypatch.setenv("WINDIR", str(tmp_path / "Windows"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert diagram_metrics.FontMetrics("SimHei")._resolve(13, False) == fallback


def test_deck_metrics_do_not_trust_a_narrow_missing_cjk_glyph(monkeypatch) -> None:
    metrics.text_width.cache_clear()
    monkeypatch.setattr(metrics, "_font", lambda *args, **kwargs: _NarrowMissingGlyphFont())

    assert metrics.text_width("中国", 20) >= 40 * 1.08
    metrics.text_width.cache_clear()


def test_diagram_metrics_keep_cjk_width_conservative(monkeypatch) -> None:
    font_metrics = diagram_metrics.FontMetrics("missing-cjk-font")
    monkeypatch.setattr(
        diagram_metrics.FontMetrics,
        "_font",
        lambda *args, **kwargs: _NarrowMissingGlyphFont(),
    )

    width, _height = font_metrics.measure("中国", 20)

    assert width >= 40 * 1.06


def _stub_browser(tmp_path: Path, script: str) -> Path:
    fake = tmp_path / "chrome"
    fake.write_text(script, encoding="utf-8")
    fake.chmod(0o755)
    return fake


def test_unusable_browser_is_a_missing_icon_not_a_failed_render(tmp_path, monkeypatch) -> None:
    """The deck renderer downgrades RuntimeError to a finding. A browser that
    exists but exits nonzero must arrive as one, or the whole render aborts and
    loses its build receipt."""
    import pytest

    monkeypatch.setattr(icons, "_chrome", lambda: _stub_browser(tmp_path, "#!/bin/sh\nexit 3\n"))
    with pytest.raises(RuntimeError, match="exit 3"):
        icons.icon_png("bolt", color="#000000", background="#ffffff", px=64, run_root=tmp_path)


def test_hanging_browser_is_a_missing_icon_not_a_hang(tmp_path, monkeypatch) -> None:
    import subprocess

    import pytest

    monkeypatch.setattr(icons, "_chrome", lambda: _stub_browser(tmp_path, "#!/bin/sh\nsleep 5\n"))
    monkeypatch.setattr(
        icons.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("chrome", 60)),
    )
    with pytest.raises(RuntimeError, match="timed out"):
        icons.icon_png("bolt", color="#000000", background="#ffffff", px=64, run_root=tmp_path)
