"""Rendering entry points: deck (pptx), deck-html (reveal.js), report (md → docx)."""

from .deck import render_deck
from .html_deck import render_html_deck
from .report import render_report

__all__ = ["render_deck", "render_html_deck", "render_report"]
