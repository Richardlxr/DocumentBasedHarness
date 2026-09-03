"""Bounded arithmetic for explicitly declared evidence derivations."""

from __future__ import annotations

import ast
import math
import operator

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def calculate(formula: str, values: dict[str, float]) -> float:
    if len(formula) > 1000:
        raise ValueError("derived formula exceeds 1000 characters")
    tree = ast.parse(formula, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("derived formula is too complex")

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Name) and node.id in values:
            return float(values[node.id])
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return (-1 if isinstance(node.op, ast.USub) else 1) * evaluate(node.operand)
        raise ValueError("derived formula permits only operands, numeric constants and + - * /")

    result = evaluate(tree)
    if not math.isfinite(result):
        raise ValueError("derived result must be finite")
    return result
