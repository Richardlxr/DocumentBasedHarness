"""Rendering entry points: deck (pptx) and report (md → docx)."""

from .deck import render_deck
from .report import render_report

__all__ = ["render_deck", "render_report"]
