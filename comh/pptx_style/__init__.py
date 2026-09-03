"""PPTX appearance assets; content structure remains owned by the deck renderer."""

from .inspect import inspect_pptx
from .profile import StyleError, import_style, load_style

__all__ = ["StyleError", "import_style", "inspect_pptx", "load_style"]
