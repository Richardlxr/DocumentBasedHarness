from __future__ import annotations

import heapq
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from statistics import median
from typing import Literal

from ..errors import DocumentError
from .metrics import FontMetrics

Side = Literal["N", "E", "S", "W"]
Lane = tuple[Literal["x", "y"], float]
_EPSILON = 1e-6


@dataclass(frozen=True, slots=True, order=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2, self.y + self.height / 2)

    def expanded(self, amount: float) -> Rect:
        return Rect(
            self.x - amount,
            self.y - amount,
            self.width + amount * 2,
            self.height + amount * 2,
        )

    def contains_interior(self, point: Point) -> bool:
        return (
            self.left + _EPSILON < point.x < self.right - _EPSILON
            and self.top + _EPSILON < point.y < self.bottom - _EPSILON
        )

    def intersects(self, other: Rect, *, padding: float = 0) -> bool:
        return not (
            self.right + padding <= other.left
            or other.right + padding <= self.left
            or self.bottom + padding <= other.top
            or other.bottom + padding <= self.top
        )


@dataclass(frozen=True, slots=True)
class LayoutNodeInput:
    key: str
    label: str
    shape: str
    order: int


@dataclass(frozen=True, slots=True)
class LayoutEdgeInput:
    key: str
    source: str
    target: str
    label: str
    order: int


@dataclass(frozen=True, slots=True)
class PlacedNode:
    source: LayoutNodeInput
    label: str
    rank: int
    rect: Rect


@dataclass(frozen=True, slots=True)
class Port:
    side: Side
    point: Point
    stub: Point


@dataclass(frozen=True, slots=True)
class RoutedEdge:
    source: LayoutEdgeInput
    points: tuple[Point, ...]
    source_port: Port
    target_port: Port
    label_box: Rect | None
    label_fraction: float
    label_offset: Point

    @property
    def segments(self) -> tuple[tuple[Point, Point], ...]:
        return tuple(zip(self.points, self.points[1:], strict=False))


@dataclass(frozen=True, slots=True)
class LayoutResult:
    direction: str
    nodes: dict[str, PlacedNode]
    edges: dict[str, RoutedEdge]
    width: float
    height: float
    scaled_font_size: float

    def validate(self, policy: DiagramLayoutPolicy) -> None:
        node_rects = [node.rect for node in self.nodes.values()]
        for index, rect in enumerate(node_rects):
            for other in node_rects[index + 1 :]:
                if rect.intersects(other, padding=policy.node_gap / 4):
                    raise DocumentError("diagram layout contains overlapping nodes")
        labels = [edge.label_box for edge in self.edges.values() if edge.label_box is not None]
        for index, label in enumerate(labels):
            if any(label.intersects(rect, padding=policy.label_clearance) for rect in node_rects):
                raise DocumentError("diagram edge label overlaps a node")
            for other in labels[index + 1 :]:
                if label.intersects(other, padding=policy.label_clearance):
                    raise DocumentError("diagram edge labels overlap")
        for edge in self.edges.values():
            for start, end in edge.segments:
                for key, node in self.nodes.items():
                    if key in {edge.source.source, edge.source.target}:
                        continue
                    if _segment_hits_rect(start, end, node.rect.expanded(policy.node_clearance)):
                        raise DocumentError("diagram edge crosses an unrelated node")
        edge_items = list(self.edges.values())
        for index, edge in enumerate(edge_items):
            for other in edge_items[index + 1 :]:
                if any(
                    _segments_cross(segment, other_segment)
                    or _overlap_length(segment, other_segment) > 0
                    for segment in edge.segments
                    for other_segment in other.segments
                ):
                    raise DocumentError("diagram edges cross or share an ambiguous route")
                if edge.label_box and any(
                    _segment_hits_rect(*segment, edge.label_box.expanded(policy.label_clearance))
                    for segment in other.segments
                ):
                    raise DocumentError("diagram edge label overlaps an unrelated line")
                if other.label_box and any(
                    _segment_hits_rect(*segment, other.label_box.expanded(policy.label_clearance))
                    for segment in edge.segments
                ):
                    raise DocumentError("diagram edge label overlaps an unrelated line")
        if self.scaled_font_size < policy.min_scaled_font_size:
            raise DocumentError(
                "diagram would shrink below the minimum readable font size "
                f"({self.scaled_font_size:.1f}px < {policy.min_scaled_font_size:.1f}px); "
                "split the diagram or choose a less horizontal layout"
            )


@dataclass(frozen=True, slots=True)
class DiagramLayoutPolicy:
    max_node_text_width: float = 220
    node_padding_x: float = 24
    node_padding_y: float = 16
    min_node_width: float = 104
    min_node_height: float = 48
    margin: float = 40
    rank_gap: float = 74
    node_gap: float = 74
    node_clearance: float = 14
    line_clearance: float = 10
    label_padding_x: float = 7
    label_padding_y: float = 4
    label_clearance: float = 5
    label_segment_padding: float = 14
    arrow_clearance: float = 16
    outer_lane: float = 46
    bend_penalty: float = 42
    crossing_penalty: float = 260
    overlap_penalty: float = 12
    proximity_penalty: float = 2.5
    max_route_candidates: int = 7
    reroute_passes: int = 5
    align_rank_channels: bool = True
    target_width: float = 590
    min_scaled_font_size: float = 7.5


def _segment_length(start: Point, end: Point) -> float:
    return abs(end.x - start.x) + abs(end.y - start.y)


def _segment_hits_rect(start: Point, end: Point, rect: Rect) -> bool:
    if math.isclose(start.y, end.y):
        return rect.top + _EPSILON < start.y < rect.bottom - _EPSILON and max(
            min(start.x, end.x), rect.left
        ) + _EPSILON < min(max(start.x, end.x), rect.right)
    if math.isclose(start.x, end.x):
        return rect.left + _EPSILON < start.x < rect.right - _EPSILON and max(
            min(start.y, end.y), rect.top
        ) + _EPSILON < min(max(start.y, end.y), rect.bottom)
    return True


def _segments_cross(first: tuple[Point, Point], second: tuple[Point, Point]) -> bool:
    a, b = first
    c, d = second
    first_horizontal = math.isclose(a.y, b.y)
    second_horizontal = math.isclose(c.y, d.y)
    if first_horizontal != second_horizontal:
        horizontal = first if first_horizontal else second
        vertical = second if first_horizontal else first
        h1, h2 = horizontal
        v1, v2 = vertical
        return min(h1.x, h2.x) < v1.x < max(h1.x, h2.x) and min(v1.y, v2.y) < h1.y < max(v1.y, v2.y)
    return False


def _overlap_length(first: tuple[Point, Point], second: tuple[Point, Point]) -> float:
    a, b = first
    c, d = second
    if math.isclose(a.y, b.y) and math.isclose(c.y, d.y) and math.isclose(a.y, c.y):
        return max(0.0, min(max(a.x, b.x), max(c.x, d.x)) - max(min(a.x, b.x), min(c.x, d.x)))
    if math.isclose(a.x, b.x) and math.isclose(c.x, d.x) and math.isclose(a.x, c.x):
        return max(0.0, min(max(a.y, b.y), max(c.y, d.y)) - max(min(a.y, b.y), min(c.y, d.y)))
    return 0.0


def _parallel_distance(first: tuple[Point, Point], second: tuple[Point, Point]) -> float | None:
    a, b = first
    c, d = second
    if math.isclose(a.y, b.y) and math.isclose(c.y, d.y):
        overlap = min(max(a.x, b.x), max(c.x, d.x)) - max(min(a.x, b.x), min(c.x, d.x))
        return abs(a.y - c.y) if overlap > 0 else None
    if math.isclose(a.x, b.x) and math.isclose(c.x, d.x):
        overlap = min(max(a.y, b.y), max(c.y, d.y)) - max(min(a.y, b.y), min(c.y, d.y))
        return abs(a.x - c.x) if overlap > 0 else None
    return None


def _simplify(points: list[Point]) -> tuple[Point, ...]:
    compact: list[Point] = []
    for point in points:
        if compact and point == compact[-1]:
            continue
        compact.append(point)
        while len(compact) >= 3:
            a, b, c = compact[-3:]
            if (math.isclose(a.x, b.x) and math.isclose(b.x, c.x)) or (
                math.isclose(a.y, b.y) and math.isclose(b.y, c.y)
            ):
                compact.pop(-2)
            else:
                break
    return tuple(compact)


def _assign_ranks(nodes: list[LayoutNodeInput], edges: list[LayoutEdgeInput]) -> dict[str, int]:
    incoming = {node.key: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    order = {node.key: node.order for node in nodes}
    for edge in edges:
        outgoing[edge.source].append(edge.target)
        incoming[edge.target] += 1
    queue = deque(sorted((key for key, count in incoming.items() if count == 0), key=order.get))
    ranks = {node.key: 0 for node in nodes}
    visited: set[str] = set()
    while queue:
        key = queue.popleft()
        visited.add(key)
        for target in sorted(outgoing[key], key=order.get):
            ranks[target] = max(ranks[target], ranks[key] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    next_rank = max(ranks.values(), default=0) + 1
    for key in sorted((key for key in ranks if key not in visited), key=order.get):
        ranks[key] = next_rank
        next_rank += 1
    return ranks


def _ordered_ranks(
    nodes: list[LayoutNodeInput], edges: list[LayoutEdgeInput], ranks: dict[str, int]
) -> dict[int, list[str]]:
    groups: dict[int, list[str]] = defaultdict(list)
    order = {node.key: node.order for node in nodes}
    for node in nodes:
        groups[ranks[node.key]].append(node.key)
    for keys in groups.values():
        keys.sort(key=order.get)
    predecessors: dict[str, list[str]] = defaultdict(list)
    successors: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        predecessors[edge.target].append(edge.source)
        successors[edge.source].append(edge.target)
    max_rank = max(groups, default=0)
    for _ in range(4):
        for rank in range(1, max_rank + 1):
            previous = {key: index for index, key in enumerate(groups.get(rank - 1, []))}
            groups[rank].sort(
                key=lambda key: (
                    median([previous[item] for item in predecessors[key] if item in previous])
                    if any(item in previous for item in predecessors[key])
                    else float("inf"),
                    order[key],
                )
            )
        for rank in range(max_rank - 1, -1, -1):
            following = {key: index for index, key in enumerate(groups.get(rank + 1, []))}
            groups[rank].sort(
                key=lambda key: (
                    median([following[item] for item in successors[key] if item in following])
                    if any(item in following for item in successors[key])
                    else float("inf"),
                    order[key],
                )
            )
    return groups


def _preferred_sides(direction: str, source_rank: int, target_rank: int) -> tuple[Side, Side]:
    forward = target_rank >= source_rank
    if direction in {"LR", "RL"}:
        if direction == "RL":
            forward = not forward
        return ("E", "W") if forward else ("W", "E")
    if direction == "BT":
        forward = not forward
    return ("S", "N") if forward else ("N", "S")


def _port_for(rect: Rect, side: Side, index: int, count: int, clearance: float) -> Port:
    fraction = (index + 1) / (count + 1)
    if side == "E":
        point = Point(rect.right, rect.top + rect.height * fraction)
        stub = Point(rect.right + clearance, point.y)
    elif side == "W":
        point = Point(rect.left, rect.top + rect.height * fraction)
        stub = Point(rect.left - clearance, point.y)
    elif side == "S":
        point = Point(rect.left + rect.width * fraction, rect.bottom)
        stub = Point(point.x, rect.bottom + clearance)
    else:
        point = Point(rect.left + rect.width * fraction, rect.top)
        stub = Point(point.x, rect.top - clearance)
    return Port(side, point, stub)


class DiagramLayoutEngine:
    def __init__(
        self,
        *,
        font_family: str,
        node_font_size: int,
        edge_font_size: int,
        policy: DiagramLayoutPolicy | None = None,
    ) -> None:
        self.fonts = FontMetrics(font_family)
        self.node_font_size = node_font_size
        self.edge_font_size = edge_font_size
        self.policy = policy or DiagramLayoutPolicy()

    def layout(
        self,
        direction: str,
        nodes: list[LayoutNodeInput],
        edges: list[LayoutEdgeInput],
    ) -> LayoutResult:
        ranks = _assign_ranks(nodes, edges)
        groups = _ordered_ranks(nodes, edges, ranks)
        placed = self._place_nodes(direction, nodes, edges, ranks, groups)
        ports = self._allocate_ports(direction, edges, ranks, placed)
        routed = self._route_all(direction, edges, placed, ports)
        routed = self._rip_up_and_reroute(direction, edges, placed, ports, routed)
        min_x = min(node.rect.left for node in placed.values())
        min_y = min(node.rect.top for node in placed.values())
        max_x = max(node.rect.right for node in placed.values())
        max_y = max(node.rect.bottom for node in placed.values())
        for edge in routed.values():
            min_x = min(min_x, *(point.x for point in edge.points))
            min_y = min(min_y, *(point.y for point in edge.points))
            max_x = max(max_x, *(point.x for point in edge.points))
            max_y = max(max_y, *(point.y for point in edge.points))
            if edge.label_box:
                min_x = min(min_x, edge.label_box.left)
                min_y = min(min_y, edge.label_box.top)
                max_x = max(max_x, edge.label_box.right)
                max_y = max(max_y, edge.label_box.bottom)
        width = max_x - min_x + self.policy.margin * 2
        height = max_y - min_y + self.policy.margin * 2
        scale = min(1.0, self.policy.target_width / width)
        result = LayoutResult(
            direction,
            placed,
            routed,
            width,
            height,
            self.node_font_size * scale,
        )
        result.validate(self.policy)
        return result

    def _measure_node(self, node: LayoutNodeInput) -> tuple[str, float, float]:
        bold = node.shape in {"rounded", "process", "rhombus"}
        label = self.fonts.wrap(
            node.label,
            self.node_font_size,
            self.policy.max_node_text_width,
            bold,
        )
        sizes = [self.fonts.measure(line, self.node_font_size, bold) for line in label.splitlines()]
        width = max((item[0] for item in sizes), default=1) + self.policy.node_padding_x * 2
        height = sum(item[1] for item in sizes) + self.policy.node_padding_y * 2
        return (
            label,
            max(self.policy.min_node_width, width),
            max(self.policy.min_node_height, height),
        )

    def _label_size(self, label: str) -> tuple[float, float]:
        width, height = self.fonts.measure(label, self.edge_font_size)
        return (
            width + self.policy.label_padding_x * 2,
            height + self.policy.label_padding_y * 2,
        )

    def _place_nodes(
        self,
        direction: str,
        nodes: list[LayoutNodeInput],
        edges: list[LayoutEdgeInput],
        ranks: dict[str, int],
        groups: dict[int, list[str]],
    ) -> dict[str, PlacedNode]:
        by_key = {node.key: node for node in nodes}
        measured = {node.key: self._measure_node(node) for node in nodes}
        max_rank = max(groups, default=0)
        horizontal = direction in {"LR", "RL"}
        rank_primary_size = {
            rank: max((measured[key][1 if horizontal else 2] for key in groups[rank]), default=1)
            for rank in groups
        }
        rank_gap = {rank: self.policy.rank_gap for rank in range(max_rank)}
        for edge in edges:
            if not edge.label or abs(ranks[edge.source] - ranks[edge.target]) != 1:
                continue
            width, height = self._label_size(edge.label)
            boundary = min(ranks[edge.source], ranks[edge.target])
            needed = (
                width
                + self.policy.label_segment_padding * 2
                + self.policy.arrow_clearance
                + self.policy.label_clearance * 2
                if horizontal
                else height + self.policy.label_segment_padding * 2
            )
            rank_gap[boundary] = max(rank_gap[boundary], needed)
        primary_positions: dict[int, float] = {}
        cursor = self.policy.margin
        rank_sequence = list(range(max_rank + 1))
        if direction in {"RL", "BT"}:
            rank_sequence.reverse()
        for rank in rank_sequence:
            primary_positions[rank] = cursor
            next_rank = rank - 1 if direction in {"RL", "BT"} else rank + 1
            cursor += rank_primary_size.get(rank, 1) + rank_gap.get(min(rank, next_rank), 0)
        cross_totals: dict[int, float] = {}
        for rank, keys in groups.items():
            sizes = [measured[key][2 if horizontal else 1] for key in keys]
            cross_totals[rank] = sum(sizes) + self.policy.node_gap * max(0, len(sizes) - 1)
        max_cross = max(cross_totals.values(), default=0)
        placed: dict[str, PlacedNode] = {}
        for rank, keys in groups.items():
            cross = self.policy.margin + (max_cross - cross_totals[rank]) / 2
            for key in keys:
                label, width, height = measured[key]
                if horizontal:
                    x = primary_positions[rank] + (rank_primary_size[rank] - width) / 2
                    y = cross
                    cross += height + self.policy.node_gap
                else:
                    x = cross
                    y = primary_positions[rank] + (rank_primary_size[rank] - height) / 2
                    cross += width + self.policy.node_gap
                placed[key] = PlacedNode(by_key[key], label, rank, Rect(x, y, width, height))
        return placed

    def _allocate_ports(
        self,
        direction: str,
        edges: list[LayoutEdgeInput],
        ranks: dict[str, int],
        nodes: dict[str, PlacedNode],
    ) -> dict[tuple[str, str], Port]:
        assignments: dict[tuple[str, Side], list[tuple[str, float, str]]] = defaultdict(list)
        sides: dict[tuple[str, str], Side] = {}
        for edge in edges:
            source_side, target_side = _preferred_sides(
                direction, ranks[edge.source], ranks[edge.target]
            )
            sides[(edge.key, "source")] = source_side
            sides[(edge.key, "target")] = target_side
            source_other = nodes[edge.target].rect.center
            target_other = nodes[edge.source].rect.center
            assignments[(edge.source, source_side)].append(
                (
                    edge.key,
                    source_other.y if source_side in {"E", "W"} else source_other.x,
                    "source",
                )
            )
            assignments[(edge.target, target_side)].append(
                (
                    edge.key,
                    target_other.y if target_side in {"E", "W"} else target_other.x,
                    "target",
                )
            )
        ports: dict[tuple[str, str], Port] = {}
        for (node_key, side), endpoints in assignments.items():
            endpoints.sort(key=lambda item: (item[1], item[0], item[2]))
            for index, (edge_key, _, endpoint) in enumerate(endpoints):
                ports[(edge_key, endpoint)] = _port_for(
                    nodes[node_key].rect,
                    side,
                    index,
                    len(endpoints),
                    self.policy.node_clearance + index * self.policy.line_clearance,
                )
        return ports

    def _route_all(
        self,
        direction: str,
        edges: list[LayoutEdgeInput],
        nodes: dict[str, PlacedNode],
        ports: dict[tuple[str, str], Port],
    ) -> dict[str, RoutedEdge]:
        routed: dict[str, RoutedEdge] = {}
        order = sorted(
            edges,
            key=lambda edge: (
                not bool(edge.label),
                -self._label_size(edge.label)[0] if edge.label else 0,
                edge.order,
            ),
        )
        for edge in order:
            routed[edge.key] = self._route_edge(direction, edge, nodes, ports, routed)
        return routed

    def _preferred_rank_lane(
        self,
        direction: str,
        edge: LayoutEdgeInput,
        nodes: dict[str, PlacedNode],
    ) -> Lane | None:
        if not self.policy.align_rank_channels:
            return None
        source_rank = nodes[edge.source].rank
        target_rank = nodes[edge.target].rank
        if source_rank == target_rank:
            return None
        boundary_rank = target_rank - 1 if target_rank > source_rank else target_rank
        first = [node.rect for node in nodes.values() if node.rank == boundary_rank]
        second = [node.rect for node in nodes.values() if node.rank == boundary_rank + 1]
        if direction in {"LR", "RL"}:
            left, right = sorted(
                (first, second),
                key=lambda rects: sum(rect.center.x for rect in rects) / len(rects),
            )
            return "x", (max(rect.right for rect in left) + min(rect.left for rect in right)) / 2
        top, bottom = sorted(
            (first, second),
            key=lambda rects: sum(rect.center.y for rect in rects) / len(rects),
        )
        return "y", (max(rect.bottom for rect in top) + min(rect.top for rect in bottom)) / 2

    def _route_edge(
        self,
        direction: str,
        edge: LayoutEdgeInput,
        nodes: dict[str, PlacedNode],
        ports: dict[tuple[str, str], Port],
        fixed: dict[str, RoutedEdge],
    ) -> RoutedEdge:
        source_port = ports[(edge.key, "source")]
        target_port = ports[(edge.key, "target")]
        fixed_segments = [segment for item in fixed.values() for segment in item.segments]
        fixed_labels = [item.label_box for item in fixed.values() if item.label_box is not None]
        reserved_segments = [
            (port.point, port.stub) for (edge_key, _), port in ports.items() if edge_key != edge.key
        ]
        routing_segments = [*fixed_segments, *reserved_segments]
        preferred_lane = self._preferred_rank_lane(direction, edge, nodes)
        candidates = self._route_candidates(
            source_port.stub,
            target_port.stub,
            [node.rect.expanded(self.policy.node_clearance) for node in nodes.values()],
            routing_segments,
            fixed_labels,
            preferred_lane,
        )
        scored: list[tuple[tuple[float, ...], tuple[Point, ...], Rect | None, float, Point]] = []
        for points in candidates:
            complete = _simplify(
                [source_port.point, source_port.stub, *points, target_port.stub, target_port.point]
            )
            label_box, fraction, offset, label_score = self._place_label(
                edge.label,
                complete,
                nodes,
                fixed,
                reserved_segments=reserved_segments,
            )
            route_score = self._route_score(complete, routing_segments, preferred_lane)
            hard_conflicts = (
                label_score[0] + label_score[1] + route_score[0] + float(route_score[1] > 0)
            )
            score = (
                hard_conflicts,
                label_score[0],
                label_score[1],
                route_score[0],
                route_score[1],
                float(label_score[2] > 0),
                route_score[2],
                route_score[3],
                route_score[4],
                label_score[2],
                label_score[3],
                *label_score[4:],
            )
            scored.append((score, complete, label_box, fraction, offset))
        if not scored:
            raise DocumentError(f"cannot route diagram edge {edge.source} -> {edge.target}")
        _, points, label_box, fraction, offset = min(scored, key=lambda item: item[0])
        return RoutedEdge(edge, points, source_port, target_port, label_box, fraction, offset)

    def _route_candidates(
        self,
        start: Point,
        end: Point,
        obstacles: list[Rect],
        fixed_segments: list[tuple[Point, Point]],
        fixed_labels: list[Rect],
        preferred_lane: Lane | None,
    ) -> list[tuple[Point, ...]]:
        blockers = [
            *obstacles,
            *(label.expanded(self.policy.label_clearance) for label in fixed_labels),
        ]
        candidates: list[tuple[Point, ...]] = []

        def remember(points: list[Point]) -> None:
            simplified = _simplify(points)
            if simplified in candidates:
                return
            if any(
                _segment_hits_rect(segment_start, segment_end, blocker)
                for segment_start, segment_end in zip(simplified, simplified[1:], strict=False)
                for blocker in blockers
            ):
                return
            candidates.append(simplified)

        if math.isclose(start.x, end.x) or math.isclose(start.y, end.y):
            remember([start, end])
        remember([start, Point(end.x, start.y), end])
        remember([start, Point(start.x, end.y), end])
        if preferred_lane is not None:
            axis, lane = preferred_lane
            if axis == "x":
                remember([start, Point(lane, start.y), Point(lane, end.y), end])
            else:
                remember([start, Point(start.x, lane), Point(end.x, lane), end])
        if blockers:
            x_lanes = {
                min(rect.left for rect in blockers) - self.policy.outer_lane,
                max(rect.right for rect in blockers) + self.policy.outer_lane,
            }
            y_lanes = {
                min(rect.top for rect in blockers) - self.policy.outer_lane,
                max(rect.bottom for rect in blockers) + self.policy.outer_lane,
            }
            for rect in blockers:
                x_lanes.update((rect.left, rect.right))
                y_lanes.update((rect.top, rect.bottom))
            lane_paths: list[tuple[float, list[Point]]] = []
            for lane in x_lanes:
                points = [start, Point(lane, start.y), Point(lane, end.y), end]
                lane_paths.append(
                    (
                        sum(
                            _segment_length(*segment)
                            for segment in zip(points, points[1:], strict=False)
                        ),
                        points,
                    )
                )
            for lane in y_lanes:
                points = [start, Point(start.x, lane), Point(end.x, lane), end]
                lane_paths.append(
                    (
                        sum(
                            _segment_length(*segment)
                            for segment in zip(points, points[1:], strict=False)
                        ),
                        points,
                    )
                )
            for _, points in sorted(lane_paths, key=lambda item: (item[0], item[1])):
                remember(points)
                if len(candidates) >= self.policy.max_route_candidates:
                    break
        first = self._a_star(start, end, blockers, fixed_segments, set())
        if first is None:
            return candidates
        if first not in candidates:
            candidates.append(first)
        discouraged: set[tuple[Point, Point]] = set()
        for segment in zip(first, first[1:], strict=False):
            discouraged.add(segment)
            candidate = self._a_star(start, end, blockers, fixed_segments, discouraged)
            if candidate is not None and candidate not in candidates:
                candidates.append(candidate)
            if len(candidates) >= self.policy.max_route_candidates:
                break
        return candidates

    def _a_star(
        self,
        start: Point,
        end: Point,
        obstacles: list[Rect],
        fixed_segments: list[tuple[Point, Point]],
        discouraged: set[tuple[Point, Point]],
    ) -> tuple[Point, ...] | None:
        xs = {start.x, end.x}
        ys = {start.y, end.y}
        if obstacles:
            xs.update({min(rect.left for rect in obstacles) - self.policy.outer_lane})
            xs.update({max(rect.right for rect in obstacles) + self.policy.outer_lane})
            ys.update({min(rect.top for rect in obstacles) - self.policy.outer_lane})
            ys.update({max(rect.bottom for rect in obstacles) + self.policy.outer_lane})
        for rect in obstacles:
            xs.update((rect.left, rect.right))
            ys.update((rect.top, rect.bottom))
        for start_point, end_point in fixed_segments:
            if math.isclose(start_point.x, end_point.x):
                xs.update(
                    (
                        start_point.x - self.policy.line_clearance,
                        start_point.x + self.policy.line_clearance,
                    )
                )
                ys.update((start_point.y, end_point.y))
            else:
                ys.update(
                    (
                        start_point.y - self.policy.line_clearance,
                        start_point.y + self.policy.line_clearance,
                    )
                )
                xs.update((start_point.x, end_point.x))
        sorted_x = sorted(xs)
        sorted_y = sorted(ys)
        xs.update((a + b) / 2 for a, b in zip(sorted_x, sorted_x[1:], strict=False))
        ys.update((a + b) / 2 for a, b in zip(sorted_y, sorted_y[1:], strict=False))
        points = sorted(
            (
                Point(x, y)
                for x in sorted(xs)
                for y in sorted(ys)
                if not any(rect.contains_interior(Point(x, y)) for rect in obstacles)
            ),
            key=lambda point: (point.x, point.y),
        )
        index = {point: position for position, point in enumerate(points)}
        if start not in index or end not in index:
            return None
        neighbors: dict[int, list[tuple[int, str]]] = defaultdict(list)
        by_x: dict[float, list[Point]] = defaultdict(list)
        by_y: dict[float, list[Point]] = defaultdict(list)
        for point in points:
            by_x[point.x].append(point)
            by_y[point.y].append(point)
        for line, axis in ((by_x, "V"), (by_y, "H")):
            for line_points in line.values():
                line_points.sort(key=lambda point: point.y if axis == "V" else point.x)
                for first, second in zip(line_points, line_points[1:], strict=False):
                    if any(_segment_hits_rect(first, second, rect) for rect in obstacles):
                        continue
                    neighbors[index[first]].append((index[second], axis))
                    neighbors[index[second]].append((index[first], axis))
        start_index = index[start]
        end_index = index[end]
        queue: list[tuple[float, float, int, str]] = [(0, 0, start_index, "")]
        distance: dict[tuple[int, str], float] = {(start_index, ""): 0}
        previous: dict[tuple[int, str], tuple[int, str] | None] = {(start_index, ""): None}
        final_state: tuple[int, str] | None = None
        while queue:
            _, current_cost, current, previous_axis = heapq.heappop(queue)
            state = (current, previous_axis)
            if current_cost != distance.get(state):
                continue
            if current == end_index:
                final_state = state
                break
            for neighbor, axis in neighbors[current]:
                segment = (points[current], points[neighbor])
                cost = _segment_length(*segment)
                if previous_axis and axis != previous_axis:
                    cost += self.policy.bend_penalty
                if segment in discouraged or (segment[1], segment[0]) in discouraged:
                    cost += self.policy.crossing_penalty * 4
                for fixed_segment in fixed_segments:
                    if _segments_cross(segment, fixed_segment):
                        cost += self.policy.crossing_penalty
                    cost += _overlap_length(segment, fixed_segment) * self.policy.overlap_penalty
                    proximity = _parallel_distance(segment, fixed_segment)
                    if proximity is not None and 0 < proximity < self.policy.line_clearance:
                        cost += (
                            self.policy.line_clearance - proximity
                        ) * self.policy.proximity_penalty
                next_state = (neighbor, axis)
                next_cost = current_cost + cost
                if next_cost < distance.get(next_state, math.inf):
                    distance[next_state] = next_cost
                    previous[next_state] = state
                    heuristic = abs(points[neighbor].x - end.x) + abs(points[neighbor].y - end.y)
                    heapq.heappush(queue, (next_cost + heuristic, next_cost, neighbor, axis))
        if final_state is None:
            return None
        path: list[Point] = []
        state: tuple[int, str] | None = final_state
        while state is not None:
            path.append(points[state[0]])
            state = previous[state]
        path.reverse()
        return _simplify(path)

    def _place_label(
        self,
        label: str,
        points: tuple[Point, ...],
        nodes: dict[str, PlacedNode],
        fixed: dict[str, RoutedEdge],
        *,
        reserved_segments: list[tuple[Point, Point]] | None = None,
    ) -> tuple[Rect | None, float, Point, tuple[float, ...]]:
        if not label:
            return None, 0.0, Point(0, 0), (0, 0, 0, 0, 0)
        width, height = self._label_size(label)
        total = sum(
            _segment_length(start, end) for start, end in zip(points, points[1:], strict=False)
        )
        traversed = 0.0
        candidates: list[tuple[tuple[float, ...], Rect, float, Point]] = []
        fixed_labels = [edge.label_box for edge in fixed.values() if edge.label_box]
        fixed_segments = [segment for edge in fixed.values() for segment in edge.segments]
        fixed_segments.extend(reserved_segments or [])
        own_segments = list(zip(points, points[1:], strict=False))
        for start, end in own_segments:
            length = _segment_length(start, end)
            horizontal = math.isclose(start.y, end.y)
            positions = (0.15, 0.3, 0.5, 0.7, 0.85) if length else (0.5,)
            if horizontal:
                clearance = height / 2 + self.policy.label_clearance + 1
                offsets = (Point(0, -clearance), Point(0, clearance), Point(0, 0))
            else:
                clearance = width / 2 + self.policy.label_clearance + 1
                offsets = (Point(-clearance, 0), Point(clearance, 0), Point(0, 0))
            for position in positions:
                anchor = Point(
                    start.x + (end.x - start.x) * position,
                    start.y + (end.y - start.y) * position,
                )
                for offset_index, offset in enumerate(offsets):
                    center = Point(anchor.x + offset.x, anchor.y + offset.y)
                    box = Rect(center.x - width / 2, center.y - height / 2, width, height)
                    node_collisions = sum(
                        box.intersects(node.rect, padding=self.policy.label_clearance)
                        for node in nodes.values()
                    )
                    label_collisions = sum(
                        box.intersects(other, padding=self.policy.label_clearance)
                        for other in fixed_labels
                    )
                    line_collisions = sum(
                        _segment_hits_rect(a, b, box.expanded(self.policy.label_clearance))
                        for a, b in fixed_segments
                    )
                    minimum = width + self.policy.label_segment_padding * 2
                    shortage = max(0.0, minimum - length) if horizontal else 0.0
                    route_midpoint_distance = abs((traversed + length * position) - total / 2)
                    score = (
                        float(node_collisions + label_collisions),
                        float(line_collisions),
                        shortage,
                        0.0 if horizontal else 1.0,
                        float(offset_index),
                        route_midpoint_distance,
                    )
                    fraction = (traversed + length * position) / total if total else 0.5
                    candidates.append((score, box, fraction, offset))
            traversed += length
        score, box, fraction, offset = min(candidates, key=lambda item: item[0])
        return box, 2 * fraction - 1, offset, score

    def _route_score(
        self,
        points: tuple[Point, ...],
        fixed_segments: list[tuple[Point, Point]],
        preferred_lane: Lane | None = None,
    ) -> tuple[float, ...]:
        segments = list(zip(points, points[1:], strict=False))
        crossings = sum(
            _segments_cross(segment, fixed) for segment in segments for fixed in fixed_segments
        )
        overlap = sum(
            _overlap_length(segment, fixed) for segment in segments for fixed in fixed_segments
        )
        bends = max(0, len(points) - 2)
        lane_deviation = 0.0
        if preferred_lane is not None:
            axis, lane = preferred_lane
            aligned_segments = [
                segment
                for segment in segments
                if (axis == "x" and math.isclose(segment[0].x, segment[1].x))
                or (axis == "y" and math.isclose(segment[0].y, segment[1].y))
            ]
            if aligned_segments:
                lane_deviation = min(
                    abs((segment[0].x if axis == "x" else segment[0].y) - lane)
                    for segment in aligned_segments
                )
        length = sum(_segment_length(*segment) for segment in segments)
        return float(crossings), overlap, float(bends), lane_deviation, length

    def _conflicts(self, routed: dict[str, RoutedEdge]) -> dict[str, int]:
        conflicts = {key: 0 for key in routed}
        items = list(routed.items())
        for index, (key, edge) in enumerate(items):
            for other_key, other in items[index + 1 :]:
                edge_conflict = 0
                for segment in edge.segments:
                    for other_segment in other.segments:
                        edge_conflict += int(_segments_cross(segment, other_segment))
                        edge_conflict += int(_overlap_length(segment, other_segment) > 0)
                if (
                    edge.label_box
                    and other.label_box
                    and edge.label_box.intersects(
                        other.label_box, padding=self.policy.label_clearance
                    )
                ):
                    edge_conflict += 3
                if edge.label_box:
                    edge_conflict += 2 * sum(
                        _segment_hits_rect(
                            *segment,
                            edge.label_box.expanded(self.policy.label_clearance),
                        )
                        for segment in other.segments
                    )
                if other.label_box:
                    edge_conflict += 2 * sum(
                        _segment_hits_rect(
                            *segment,
                            other.label_box.expanded(self.policy.label_clearance),
                        )
                        for segment in edge.segments
                    )
                conflicts[key] += edge_conflict
                conflicts[other_key] += edge_conflict
        return conflicts

    def _rip_up_and_reroute(
        self,
        direction: str,
        edges: list[LayoutEdgeInput],
        nodes: dict[str, PlacedNode],
        ports: dict[tuple[str, str], Port],
        routed: dict[str, RoutedEdge],
    ) -> dict[str, RoutedEdge]:
        edge_by_key = {edge.key: edge for edge in edges}
        for _ in range(self.policy.reroute_passes):
            conflicts = self._conflicts(routed)
            worst_key, count = max(conflicts.items(), key=lambda item: (item[1], item[0]))
            if count == 0:
                break
            fixed = {key: value for key, value in routed.items() if key != worst_key}
            routed[worst_key] = self._route_edge(
                direction, edge_by_key[worst_key], nodes, ports, fixed
            )
        return routed
