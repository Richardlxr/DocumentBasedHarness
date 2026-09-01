from __future__ import annotations

from dataclasses import dataclass, field

from .table_layout import TableLayoutPolicy


@dataclass(frozen=True, slots=True)
class TableCellMargins:
    top_pt: float = 2
    bottom_pt: float = 2
    start_pt: float = 3
    end_pt: float = 3

    def __post_init__(self) -> None:
        if min(self.top_pt, self.bottom_pt, self.start_pt, self.end_pt) < 0:
            raise ValueError("table cell margins cannot be negative")

    @property
    def top_twips(self) -> int:
        return round(self.top_pt * 20)

    @property
    def bottom_twips(self) -> int:
        return round(self.bottom_pt * 20)

    @property
    def start_twips(self) -> int:
        return round(self.start_pt * 20)

    @property
    def end_twips(self) -> int:
        return round(self.end_pt * 20)


@dataclass(frozen=True, slots=True)
class TableBorderProfile:
    color: str = "000000"
    outer_width_pt: float = 1.5
    inner_width_pt: float = 0.5

    def __post_init__(self) -> None:
        if self.outer_width_pt < 0 or self.inner_width_pt < 0:
            raise ValueError("table border widths cannot be negative")

    @property
    def outer_width_eighth_points(self) -> int:
        return round(self.outer_width_pt * 8)

    @property
    def inner_width_eighth_points(self) -> int:
        return round(self.inner_width_pt * 8)


@dataclass(frozen=True, slots=True)
class TableFormatProfile:
    """Composable table mechanics; semantic paragraph styles stay with cell writers."""

    borders: TableBorderProfile | None = field(default_factory=TableBorderProfile)
    cell_margins: TableCellMargins | None = field(default_factory=TableCellMargins)
    layout: TableLayoutPolicy | None = field(default_factory=TableLayoutPolicy)
    fixed_layout: bool = True
    prevent_row_split: bool = True


PLAIN_COMPACT_TABLE_PROFILE = TableFormatProfile()
