"""Tests for the scrim solver and image downsampling."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx.dml.color import RGBColor

from comh.render.scrim import downsample_image, solve_scrim


def test_scrim_solver_steps_up_alpha_for_contrast(tmp_path: Path):
    # A pure white image with white text (dark theme) requires dark scrim to reach >= 4.5:1
    white_img_path = tmp_path / "white.jpg"
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    img.save(white_img_path)

    white_text = RGBColor(255, 255, 255)
    dark_bg = RGBColor(15, 23, 42)  # slate-900

    result = solve_scrim(white_img_path, white_text, dark_bg, base_alpha=0.0)
    assert result.passed is True
    assert result.alpha > 0.5  # stepped up alpha to cover white image with dark scrim
    assert result.contrast >= 4.5
    assert len(result.image_bytes) > 0


def test_scrim_solver_downsamples_large_image(tmp_path: Path):
    huge_path = tmp_path / "huge.jpg"
    img = Image.new("RGB", (3840, 2160), color=(100, 100, 100))
    img.save(huge_path)

    text = RGBColor(255, 255, 255)
    bg = RGBColor(0, 0, 0)

    result = solve_scrim(huge_path, text, bg)
    assert result.passed is True
    assert result.mime_type == "image/jpeg"

    # Verify downsampled image bytes dimension <= 1920
    with Image.open(huge_path) as raw:
        downsampled, _, _ = downsample_image(raw, max_dim=1920)
        assert max(downsampled.size) <= 1920
