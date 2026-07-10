from __future__ import annotations

from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR, GrammarDefinition
from src.alpha_foundry.dsl.model import ASTNode, NumberLiteral

MAX_FORMULA_CHARS = DEFAULT_GRAMMAR.max_formula_chars


class FormulaParser:
    def __init__(self, grammar: GrammarDefinition = DEFAULT_GRAMMAR) -> None:
        self.grammar = grammar

    def parse(self, text: str) -> ASTNode:
        if len(text) > self.grammar.max_formula_chars:
            raise ValueError("formula exceeds maximum length")
        parser = _Parser(text, self.grammar)
        parsed = parser.parse_expr()
        parser.skip_ws()
        if parser.pos != len(parser.text):
            raise ValueError("unsupported formula syntax")
        if not isinstance(parsed, ASTNode):
            raise ValueError("unsupported formula syntax")
        node = parsed
        if node.op == "field":
            raise ValueError("unsupported formula syntax")
        return node


class _Parser:
    def __init__(self, text: str, grammar: GrammarDefinition) -> None:
        self.text = text
        self.grammar = grammar
        self.pos = 0

    def skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def parse_expr(self) -> ASTNode | NumberLiteral:
        self.skip_ws()
        if self.pos >= len(self.text):
            raise ValueError("unexpected end of formula")
        char = self.text[self.pos]
        if char == "-" or char.isdigit():
            return self.parse_number()
        ident = self.parse_ident()
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] == "(":
            self.pos += 1
            args = self.parse_args()
            return ASTNode(op=self.grammar.canonical_operator(ident), args=tuple(args))
        return ASTNode(op="field", value=self.grammar.canonical_field(ident))

    def parse_args(self) -> list[ASTNode | NumberLiteral]:
        args: list[ASTNode | NumberLiteral] = []
        self.skip_ws()
        if self.pos < len(self.text) and self.text[self.pos] == ")":
            self.pos += 1
            return args
        while True:
            args.append(self.parse_expr())
            self.skip_ws()
            if self.pos >= len(self.text):
                raise ValueError("unclosed function call")
            char = self.text[self.pos]
            if char == ",":
                self.pos += 1
                continue
            if char == ")":
                self.pos += 1
                return args
            raise ValueError("unsupported formula syntax")

    def parse_ident(self) -> str:
        self.skip_ws()
        start = self.pos
        if start >= len(self.text) or not (
            self.text[start].isalpha() or self.text[start] == "_"
        ):
            raise ValueError("unsupported formula syntax")
        self.pos += 1
        while self.pos < len(self.text) and (
            self.text[self.pos].isalnum() or self.text[self.pos] == "_"
        ):
            self.pos += 1
        return self.text[start:self.pos]

    def parse_number(self) -> NumberLiteral:
        start = self.pos
        if self.text[self.pos] == "-":
            self.pos += 1
        while self.pos < len(self.text) and self.text[self.pos].isdigit():
            self.pos += 1
        if self.pos < len(self.text) and self.text[self.pos] == ".":
            self.pos += 1
            while self.pos < len(self.text) and self.text[self.pos].isdigit():
                self.pos += 1
        return NumberLiteral.from_token(self.text[start:self.pos])
