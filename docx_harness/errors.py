from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceLocation:
    source: str
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.source}:{self.line}" if self.line else self.source


class DocumentError(Exception):
    """A source-oriented parse, validation, or rendering error."""

    def __init__(self, message: str, location: SourceLocation | None = None) -> None:
        self.message = message
        self.location = location
        prefix = f"{location}: " if location else ""
        super().__init__(f"{prefix}{message}")
