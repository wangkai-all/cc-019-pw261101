"""Minimal safe formula parser.

Grammar (only metric references and four arithmetic operations are allowed):

    expr   := term (('+' | '-') term)*
    term   := factor (('*' | '/') factor)*
    factor := NUMBER | NAME | '(' expr ')' | '-' factor

A NAME must match an existing metric key. No function calls, attribute
access, or any other syntax is accepted, so expressions can never reach
Python's eval machinery.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Set


class FormulaError(ValueError):
    """Raised when a formula string is syntactically invalid."""


@dataclass(frozen=True)
class Node:
    kind: str  # 'num' | 'ref' | 'op'
    value: object = None
    left: "Node | None" = None
    right: "Node | None" = None


_TOKEN_NUM = "NUM"
_TOKEN_NAME = "NAME"
_TOKEN_OP = "OP"
_TOKEN_LP = "LP"
_TOKEN_RP = "RP"
_TOKEN_END = "END"


def _tokenize(expr: str) -> List[tuple]:
    tokens: List[tuple] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and expr[i + 1].isdigit()):
            j = i
            dot_seen = False
            while j < n and (expr[j].isdigit() or (expr[j] == "." and not dot_seen)):
                if expr[j] == ".":
                    dot_seen = True
                j += 1
            tokens.append((_TOKEN_NUM, expr[i:j]))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append((_TOKEN_NAME, expr[i:j]))
            i = j
            continue
        if ch in "+-*/":
            tokens.append((_TOKEN_OP, ch))
            i += 1
            continue
        if ch == "(":
            tokens.append((_TOKEN_LP, ch))
            i += 1
            continue
        if ch == ")":
            tokens.append((_TOKEN_RP, ch))
            i += 1
            continue
        raise FormulaError(f"非法字符: {ch!r}")
    tokens.append((_TOKEN_END, ""))
    return tokens


class _Parser:
    def __init__(self, expr: str):
        self.tokens = _tokenize(expr)
        self.pos = 0

    def _peek(self) -> tuple:
        return self.tokens[self.pos]

    def _advance(self) -> tuple:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self) -> Node:
        node = self._expr()
        if self._peek()[0] != _TOKEN_END:
            raise FormulaError("表达式存在无法解析的多余部分")
        return node

    def _expr(self) -> Node:
        node = self._term()
        while self._peek() == (_TOKEN_OP, "+") or self._peek() == (_TOKEN_OP, "-"):
            op = self._advance()[1]
            right = self._term()
            node = Node(kind="op", value=op, left=node, right=right)
        return node

    def _term(self) -> Node:
        node = self._factor()
        while self._peek() == (_TOKEN_OP, "*") or self._peek() == (_TOKEN_OP, "/"):
            op = self._advance()[1]
            right = self._factor()
            node = Node(kind="op", value=op, left=node, right=right)
        return node

    def _factor(self) -> Node:
        tok = self._peek()
        if tok == (_TOKEN_OP, "-"):
            self._advance()
            return Node(kind="op", value="-", left=Node(kind="num", value=Decimal("0")),
                        right=self._factor())
        if tok == (_TOKEN_OP, "+"):
            self._advance()
            return self._factor()
        if tok[0] == _TOKEN_NUM:
            self._advance()
            return Node(kind="num", value=Decimal(tok[1]))
        if tok[0] == _TOKEN_NAME:
            self._advance()
            return Node(kind="ref", value=tok[1])
        if tok[0] == _TOKEN_LP:
            self._advance()
            node = self._expr()
            if self._peek()[0] != _TOKEN_RP:
                raise FormulaError("括号不匹配: 缺少 ')'")
            self._advance()
            return node
        raise FormulaError(f"此处不应出现: {tok[1]!r}")


def parse(expr: str) -> Node:
    if not expr or not expr.strip():
        raise FormulaError("公式不能为空")
    return _Parser(expr).parse()


def references(node: Node) -> Set[str]:
    """Return the set of metric keys referenced by an AST."""
    if node.kind == "ref":
        return {node.value}
    if node.kind == "op":
        return references(node.left) | references(node.right)
    return set()


def validate(expr: str, known_keys: Set[str]) -> Node:
    """Parse and ensure every reference points at an existing metric."""
    node = parse(expr)
    unknown = references(node) - known_keys
    if unknown:
        raise FormulaError(f"引用了不存在的指标: {', '.join(sorted(unknown))}")
    return node


def evaluate(node: Node, values: Dict[str, Decimal | None]) -> Decimal | None:
    """Evaluate an AST against a {metric_key: value} map.

    Any referenced value that is None propagates as None. Division by zero
    (or by null) also yields None, which is how the refund-rate blank rule
    is implemented.
    """
    if node.kind == "num":
        return node.value
    if node.kind == "ref":
        return values.get(node.value)
    left = evaluate(node.left, values)
    right = evaluate(node.right, values)
    if left is None or right is None:
        return None
    if node.value == "+":
        return left + right
    if node.value == "-":
        return left - right
    if node.value == "*":
        return left * right
    if node.value == "/":
        if right == 0:
            return None
        return left / right
    raise FormulaError(f"未知运算符: {node.value}")
