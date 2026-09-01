from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .renderers.ooxml import (
    clear_cell,
    set_cell_margins,
    set_fixed_table_layout,
    set_repeat_table_header,
    set_table_borders,
    set_table_row_cant_split,
)
from .table_format import PLAIN_COMPACT_TABLE_PROFILE, TableFormatProfile
from .table_layout import TableLayoutPlan, apply_table_layout

TableCellWriter = Callable[[Any], None]


@dataclass(frozen=True, slots=True)
class TableCellSpec:
    column: int
    write: TableCellWriter
    column_span: int = 1
    row_span: int = 1


@dataclass(frozen=True, slots=True)
class TableRowSpec:
    cells: tuple[TableCellSpec, ...]
    repeat_header: bool = False
    prevent_split: bool | None = None


@dataclass(frozen=True, slots=True)
class TableSpec:
    columns: int
    rows: tuple[TableRowSpec, ...]
    style: str | None = None


@dataclass(frozen=True, slots=True)
class BuiltTable:
    table: Any
    layout: TableLayoutPlan | None


def _validate_table_spec(spec: TableSpec) -> None:
    if spec.columns <= 0:
        raise ValueError("table must have at least one column")
    if not spec.rows:
        raise ValueError("table must have at least one row")

    occupied: set[tuple[int, int]] = set()
    for row_index, row in enumerate(spec.rows):
        for cell in row.cells:
            if cell.column < 0 or cell.column >= spec.columns:
                raise ValueError(f"cell column is outside table bounds: row {row_index}")
            if cell.column_span <= 0 or cell.row_span <= 0:
                raise ValueError("cell spans must be positive")
            if cell.column + cell.column_span > spec.columns:
                raise ValueError(f"cell column span is outside table bounds: row {row_index}")
            if row_index + cell.row_span > len(spec.rows):
                raise ValueError(f"cell row span is outside table bounds: row {row_index}")
            for occupied_row in range(row_index, row_index + cell.row_span):
                for occupied_column in range(cell.column, cell.column + cell.column_span):
                    position = (occupied_row, occupied_column)
                    if position in occupied:
                        raise ValueError(
                            f"table cells overlap at row {occupied_row}, column {occupied_column}"
                        )
                    occupied.add(position)


def build_table(
    container,
    spec: TableSpec,
    *,
    available_width_twips: int,
    profile: TableFormatProfile = PLAIN_COMPACT_TABLE_PROFILE,
) -> BuiltTable:
    """Build, merge, populate, format, and optionally lay out a Word table."""
    _validate_table_spec(spec)
    table = container.add_table(rows=len(spec.rows), cols=spec.columns)
    if spec.style is not None:
        table.style = spec.style
    if profile.fixed_layout:
        set_fixed_table_layout(table)
    if profile.borders is not None:
        set_table_borders(
            table,
            color=profile.borders.color,
            outer_size=profile.borders.outer_width_eighth_points,
            inner_size=profile.borders.inner_width_eighth_points,
        )

    for row_index, row_spec in enumerate(spec.rows):
        row = table.rows[row_index]
        prevent_split = (
            profile.prevent_row_split if row_spec.prevent_split is None else row_spec.prevent_split
        )
        if prevent_split:
            set_table_row_cant_split(row)
        if row_spec.repeat_header:
            set_repeat_table_header(row)

        for cell_spec in row_spec.cells:
            cell = table.cell(row_index, cell_spec.column)
            if cell_spec.column_span > 1 or cell_spec.row_span > 1:
                cell = cell.merge(
                    table.cell(
                        row_index + cell_spec.row_span - 1,
                        cell_spec.column + cell_spec.column_span - 1,
                    )
                )
            clear_cell(cell)
            cell_spec.write(cell)

    for row in table.rows:
        for cell in row.cells:
            if profile.cell_margins is not None:
                set_cell_margins(
                    cell,
                    top=profile.cell_margins.top_twips,
                    bottom=profile.cell_margins.bottom_twips,
                    start=profile.cell_margins.start_twips,
                    end=profile.cell_margins.end_twips,
                )

    effective_layout = profile.layout
    if effective_layout is not None:
        margins = profile.cell_margins
        effective_layout = replace(
            effective_layout,
            horizontal_margin_twips=(
                max(margins.start_twips, margins.end_twips) if margins is not None else 0
            ),
            vertical_margin_twips=(
                max(margins.top_twips, margins.bottom_twips) if margins is not None else 0
            ),
        )
    layout = (
        apply_table_layout(table, available_width_twips, policy=effective_layout)
        if effective_layout is not None
        else None
    )
    return BuiltTable(table=table, layout=layout)
