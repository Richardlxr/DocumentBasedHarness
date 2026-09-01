from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Literal
from unicodedata import east_asian_width

from docx.oxml.ns import qn

from .renderers.ooxml import set_table_column_widths, set_table_row_min_height


@dataclass(frozen=True, slots=True)
class TableCellMeasurement:
    row: int
    column: int
    text: str
    row_span: int = 1
    column_span: int = 1


@dataclass(frozen=True, slots=True)
class TableLayoutPolicy:
    font_size_pt: float = 12
    line_height_factor: float = 1.25
    horizontal_margin_twips: int = 60
    vertical_margin_twips: int = 40
    minimum_column_twips: int = 240
    column_strategy: Literal["content", "equal"] = "content"
    content_weight_exponent: float = 0.5
    column_weights: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class TableLayoutPlan:
    column_widths_twips: tuple[int, ...]
    row_min_heights_twips: tuple[int, ...]
    cells: tuple[TableCellMeasurement, ...]


@dataclass(slots=True)
class _MutableMeasurement:
    row: int
    column: int
    text: str
    row_span: int
    column_span: int


def _cell_text(tc) -> str:
    paragraphs = []
    text_tags = {qn("w:t"), qn("m:t")}
    for paragraph in tc.findall(f".//{qn('w:p')}"):
        paragraphs.append(
            "".join(node.text or "" for node in paragraph.iter() if node.tag in text_tags)
        )
    return "\n".join(paragraphs)


def measure_table_cells(table) -> tuple[TableCellMeasurement, ...]:
    """Read horizontal and vertical merge spans from the final Word table."""
    measured: list[_MutableMeasurement] = []
    active_vertical: dict[tuple[int, int], _MutableMeasurement] = {}

    for row_index, tr in enumerate(table._tbl.tr_lst):
        column_index = 0
        continued: set[tuple[int, int]] = set()
        for tc in tr.tc_lst:
            tc_pr = tc.get_or_add_tcPr()
            grid_span = tc_pr.find(qn("w:gridSpan"))
            column_span = int(grid_span.get(qn("w:val"))) if grid_span is not None else 1
            vertical_merge = tc_pr.find(qn("w:vMerge"))
            merge_value = (
                vertical_merge.get(qn("w:val"), "continue") if vertical_merge is not None else None
            )
            key = (column_index, column_span)

            if merge_value == "continue" and key in active_vertical:
                active_vertical[key].row_span += 1
                continued.add(key)
            else:
                cell = _MutableMeasurement(
                    row=row_index,
                    column=column_index,
                    text=_cell_text(tc),
                    row_span=1,
                    column_span=column_span,
                )
                measured.append(cell)
                if merge_value == "restart":
                    active_vertical[key] = cell
                    continued.add(key)

            column_index += column_span

        for key in tuple(active_vertical):
            if key not in continued:
                del active_vertical[key]

    return tuple(
        TableCellMeasurement(
            row=cell.row,
            column=cell.column,
            text=cell.text,
            row_span=cell.row_span,
            column_span=cell.column_span,
        )
        for cell in measured
    )


def _allocate_widths(
    total_width_twips: int,
    column_count: int,
    policy: TableLayoutPolicy,
    weights: tuple[float, ...],
) -> tuple[int, ...]:
    if column_count <= 0:
        return ()
    if len(weights) != column_count:
        raise ValueError("column weight count must match table column count")
    if any(weight <= 0 for weight in weights):
        raise ValueError("column weights must be positive")

    total_width_twips = max(total_width_twips, column_count)
    minimum = min(policy.minimum_column_twips, total_width_twips // column_count)
    remaining = total_width_twips - minimum * column_count
    weight_total = sum(weights)
    exact_shares = [remaining * weight / weight_total for weight in weights]
    shares = [floor(share) for share in exact_shares]
    remainder = remaining - sum(shares)
    order = sorted(
        range(column_count),
        key=lambda index: (exact_shares[index] - shares[index], -index),
        reverse=True,
    )
    for index in order[:remainder]:
        shares[index] += 1
    return tuple(minimum + share for share in shares)


def _display_units(text: str) -> float:
    units = 0.0
    for character in text:
        if character == "\t":
            units += 2.0
        elif character.isspace():
            units += 0.5
        elif east_asian_width(character) in {"W", "F", "A"}:
            units += 1.0
        else:
            units += 0.55
    return units


def _content_column_weights(
    column_count: int,
    cells: tuple[TableCellMeasurement, ...],
    policy: TableLayoutPolicy,
) -> tuple[float, ...]:
    if policy.column_weights is not None:
        return policy.column_weights
    if policy.column_strategy == "equal":
        return (1.0,) * column_count
    if policy.column_strategy != "content":
        raise ValueError(f"unsupported column strategy: {policy.column_strategy}")
    if policy.content_weight_exponent <= 0:
        raise ValueError("content weight exponent must be positive")

    demand = [1.0 for _ in range(column_count)]
    for cell in cells:
        # A title or body spanning the complete table contains no evidence about
        # how the individual columns should relate to one another.
        if cell.column_span >= column_count:
            continue
        paragraphs = cell.text.splitlines() or [""]
        units = sum(max(1.0, _display_units(paragraph)) for paragraph in paragraphs)
        share = units / cell.column_span
        for column in range(cell.column, cell.column + cell.column_span):
            if 0 <= column < column_count:
                demand[column] += share
    return tuple(value**policy.content_weight_exponent for value in demand)


def _estimated_line_count(text: str, inner_width_twips: int, font_size_pt: float) -> int:
    em_width_twips = max(1.0, font_size_pt * 20)
    capacity = max(0.5, inner_width_twips / em_width_twips)
    paragraphs = text.splitlines() or [""]
    return sum(max(1, ceil(_display_units(paragraph) / capacity)) for paragraph in paragraphs)


def compute_table_layout(
    *,
    total_width_twips: int,
    column_count: int,
    row_count: int,
    cells: tuple[TableCellMeasurement, ...],
    policy: TableLayoutPolicy | None = None,
) -> TableLayoutPlan:
    policy = policy or TableLayoutPolicy()
    weights = _content_column_weights(column_count, cells, policy)
    widths = _allocate_widths(total_width_twips, column_count, policy, weights)
    line_height = max(1, round(policy.font_size_pt * 20 * policy.line_height_factor))
    base_height = line_height + policy.vertical_margin_twips * 2
    heights = [base_height for _ in range(row_count)]
    spanning_constraints: list[tuple[TableCellMeasurement, int]] = []

    for cell in cells:
        if not 0 <= cell.row < row_count:
            raise ValueError("cell row is outside table bounds")
        if not 0 <= cell.column < column_count:
            raise ValueError("cell column is outside table bounds")
        if cell.row + cell.row_span > row_count or cell.column + cell.column_span > column_count:
            raise ValueError("merged cell span is outside table bounds")

        cell_width = sum(widths[cell.column : cell.column + cell.column_span])
        inner_width = max(1, cell_width - policy.horizontal_margin_twips * 2)
        lines = _estimated_line_count(cell.text, inner_width, policy.font_size_pt)
        required_height = lines * line_height + policy.vertical_margin_twips * 2
        if cell.row_span == 1:
            heights[cell.row] = max(heights[cell.row], required_height)
        else:
            spanning_constraints.append((cell, required_height))

    for cell, required_height in spanning_constraints:
        current = sum(heights[cell.row : cell.row + cell.row_span])
        deficit = max(0, required_height - current)
        share, remainder = divmod(deficit, cell.row_span)
        for offset in range(cell.row_span):
            heights[cell.row + offset] += share + (1 if offset < remainder else 0)

    return TableLayoutPlan(
        column_widths_twips=widths,
        row_min_heights_twips=tuple(heights),
        cells=cells,
    )


def apply_table_layout(
    table,
    total_width_twips: int,
    *,
    policy: TableLayoutPolicy | None = None,
) -> TableLayoutPlan:
    cells = measure_table_cells(table)
    plan = compute_table_layout(
        total_width_twips=total_width_twips,
        column_count=len(table.columns),
        row_count=len(table.rows),
        cells=cells,
        policy=policy,
    )
    set_table_column_widths(table, plan.column_widths_twips)
    for row, height in zip(table.rows, plan.row_min_heights_twips, strict=True):
        set_table_row_min_height(row, height)
    return plan
