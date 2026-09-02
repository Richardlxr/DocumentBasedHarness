"""Scrim solver & image downsampling for background visuals.

Single source of truth for contrast assurance across validators, HTML, and
PPTX surfaces:
- Downsamples background images (max dimension <= 1920px, JPEG quality 80)
  to keep single-file HTML lightweight.
- Synthesizes background scrim (theme.background color at alpha) over image
  pixels and computes worst-case WCAG contrast against theme.text.
- Steps up alpha dynamically (up to 0.90) until contrast >= 4.5:1 is achieved.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pptx.dml.color import RGBColor

from .theme import relative_luminance


@dataclass(frozen=True, slots=True)
class ScrimResult:
    alpha: float
    contrast: float
    passed: bool
    image_bytes: bytes
    mime_type: str


def _linear_channel(val_255: float) -> float:
    c = val_255 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _pixel_luminance(r: float, g: float, b: float) -> float:
    return 0.2126 * _linear_channel(r) + 0.7152 * _linear_channel(g) + 0.0722 * _linear_channel(b)


def _contrast(l1: float, l2: float) -> float:
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def downsample_image(
    img: Image.Image, max_dim: int = 1920, quality: int = 80
) -> tuple[Image.Image, bytes, str]:
    """Downsample an image so its largest dimension <= max_dim and compress to JPEG/PNG bytes."""
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img.save(buf, format="PNG", optimize=True)
        return img, buf.getvalue(), "image/png"

    rgb_img = img.convert("RGB")
    rgb_img.save(buf, format="JPEG", quality=quality, optimize=True)
    return rgb_img, buf.getvalue(), "image/jpeg"


def solve_scrim(
    image_path: Path,
    text_color: RGBColor,
    bg_color: RGBColor,
    *,
    base_alpha: float = 0.0,
    target_contrast: float = 4.5,
    max_alpha: float = 0.90,
) -> ScrimResult:
    """Evaluate worst-case contrast between text_color and the image composited with bg_color.

    Steps alpha from base_alpha to max_alpha in 0.05 increments until worst-case
    contrast >= target_contrast. Returns ScrimResult with the final alpha and
    downsampled image bytes.
    """
    if not image_path.is_file():
        return ScrimResult(
            alpha=base_alpha,
            contrast=1.0,
            passed=False,
            image_bytes=b"",
            mime_type="image/jpeg",
        )

    with Image.open(image_path) as raw:
        img, img_bytes, mime_type = downsample_image(raw, max_dim=1920, quality=80)

    # For fast and robust worst-case sampling, sample a thumbnail grid (e.g. 240x135)
    sample_img = img.copy()
    sample_img.thumbnail((240, 135), Image.Resampling.BOX)
    rgb_sample = sample_img.convert("RGB")
    raw_bytes = rgb_sample.tobytes()
    pixels = [
        (raw_bytes[i], raw_bytes[i + 1], raw_bytes[i + 2]) for i in range(0, len(raw_bytes), 3)
    ]

    bg_r = int(str(bg_color)[0:2], 16)
    bg_g = int(str(bg_color)[2:4], 16)
    bg_b = int(str(bg_color)[4:6], 16)

    text_lum = relative_luminance(text_color)

    current_alpha = max(0.0, min(base_alpha, max_alpha))
    best_alpha = current_alpha
    best_contrast = 0.0

    while current_alpha <= max_alpha + 1e-6:
        inv_a = 1.0 - current_alpha
        min_contrast = float("inf")
        for r, g, b in pixels:
            comp_r = inv_a * r + current_alpha * bg_r
            comp_g = inv_a * g + current_alpha * bg_g
            comp_b = inv_a * b + current_alpha * bg_b
            pix_lum = _pixel_luminance(comp_r, comp_g, comp_b)
            c = _contrast(pix_lum, text_lum)
            if c < min_contrast:
                min_contrast = c

        best_alpha = current_alpha
        best_contrast = min_contrast
        if min_contrast >= target_contrast:
            return ScrimResult(
                alpha=round(current_alpha, 2),
                contrast=round(min_contrast, 2),
                passed=True,
                image_bytes=img_bytes,
                mime_type=mime_type,
            )
        current_alpha += 0.05

    return ScrimResult(
        alpha=round(best_alpha, 2),
        contrast=round(best_contrast, 2),
        passed=(best_contrast >= target_contrast),
        image_bytes=img_bytes,
        mime_type=mime_type,
    )
