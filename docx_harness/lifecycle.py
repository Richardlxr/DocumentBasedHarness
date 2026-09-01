from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docx.document import Document as DocumentObject


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Stable context passed to project-owned document lifecycle hooks."""

    source: str
    source_dir: Path
    output: Path
    project_root: Path | None = None


DocumentHook = Callable[["DocumentObject", RenderContext], None]


@dataclass(frozen=True, slots=True)
class RenderHooks:
    """Project-owned hooks around IR rendering, all executed before the DOCX is saved."""

    configure_document: DocumentHook | None = None
    finalize_document: DocumentHook | None = None
    validate_document: DocumentHook | None = None

    def configure(self, document: DocumentObject, context: RenderContext) -> None:
        if self.configure_document is not None:
            self.configure_document(document, context)

    def finalize(self, document: DocumentObject, context: RenderContext) -> None:
        if self.finalize_document is not None:
            self.finalize_document(document, context)

    def validate(self, document: DocumentObject, context: RenderContext) -> None:
        if self.validate_document is not None:
            self.validate_document(document, context)
