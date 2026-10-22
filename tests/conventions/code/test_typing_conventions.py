from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, Optional, Set, Tuple

import pytest

PROJECT_ROOT = Path(__file__).parents[3]
PYTHON_FILES = sorted(path for folder in ("src", "scripts", "tests") for path in (PROJECT_ROOT / folder).rglob("*.py"))
BUILTIN_GENERICS = {"dict": "Dict", "list": "List"}
ANY_MESSAGE = "`Any` is only allowed for `*args` / `**kwargs`"
OBJECT_MESSAGE = "`object` is too generic for typing, use a precise type"
UNION_MESSAGE = "use `Union[...]` (`Optional[...]` with `None`) instead of the `|` operator"
OPTIONAL_MESSAGE = "use `Optional[...]` instead of `Union[..., None]`"


def union_operator_roots(node: ast.AST) -> List[ast.BinOp]:
    """Get the `A | B | ...` chains of an expression, once per chain."""
    unions = [child for child in ast.walk(node) if isinstance(child, ast.BinOp) and isinstance(child.op, ast.BitOr)]
    nested = {id(operand) for union in unions for operand in (union.left, union.right)}
    return [union for union in unions if id(union) not in nested]


class TypingConventionChecker(ast.NodeVisitor):
    """Report typing convention violations of a module.

    - `typing.Any` is only allowed to annotate `*args` and `**kwargs`.
    - `object` is never used for typing.
    - `typing.Dict` / `typing.List` are used instead of the builtin `dict` / `list` generics.
    - `typing.Union` / `typing.Optional` are used instead of the `|` operator, and `Optional[...]` instead of
      `Union[..., None]`.
    """

    def __init__(self) -> None:
        self.violations: List[str] = []
        self._star_arg_nodes: Set[int] = set()
        self._reported: Set[Tuple[int, str]] = set()

    def check(self, source: str) -> List[str]:
        self.visit(ast.parse(source))
        return self.violations

    def visit_arguments(self, node: ast.arguments) -> None:
        for star_arg in (node.vararg, node.kwarg):
            if star_arg is not None and star_arg.annotation is not None:
                self._star_arg_nodes.update(id(child) for child in ast.walk(star_arg.annotation))
        for arg in [*node.posonlyargs, *node.args, *node.kwonlyargs, node.vararg, node.kwarg]:
            if arg is not None:
                self._check_annotation(arg.annotation)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_annotation(node.returns)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_annotation(node.returns)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_annotation(node.annotation)
        self.generic_visit(node)

    def visit_TypeVar(self, node: ast.TypeVar) -> None:
        self._check_annotation(node.bound)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "Any" and id(node) not in self._star_arg_nodes:
            self._report(node, ANY_MESSAGE)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "Any" and id(node) not in self._star_arg_nodes:
            self._report(node, ANY_MESSAGE)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in BUILTIN_GENERICS:
            replacement = BUILTIN_GENERICS[node.value.id]
            self._report(node, f"use `{replacement}[...]` instead of `{node.value.id}[...]`")
        for child in ast.walk(node.slice):
            if isinstance(child, ast.Name) and child.id == "object":
                self._report(child, OBJECT_MESSAGE)
        for union in union_operator_roots(node.slice):
            self._report(union, UNION_MESSAGE)
        members = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        is_union = ast.unparse(node.value).rsplit(".", 1)[-1] == "Union"
        if is_union and any(isinstance(member, ast.Constant) and member.value is None for member in members):
            self._report(node, OPTIONAL_MESSAGE)
        self.generic_visit(node)

    def _report(self, node: ast.expr, message: str) -> None:
        """Record a violation, once per node."""
        if (id(node), message) not in self._reported:
            self._reported.add((id(node), message))
            self.violations.append(f"line {node.lineno}: {message}")

    def _check_annotation(self, annotation: Optional[ast.expr]) -> None:
        """Check what the generic visit misses in annotations: bare names and quoted annotations."""
        if annotation is None:
            return
        subscripted = {id(node.value) for node in ast.walk(annotation) if isinstance(node, ast.Subscript)}
        literal_values = {
            id(child)
            for node in ast.walk(annotation)
            if isinstance(node, ast.Subscript) and ast.unparse(node.value).rsplit(".", 1)[-1] == "Literal"
            for child in ast.walk(node.slice)
        }
        for union in union_operator_roots(annotation):
            self._report(union, UNION_MESSAGE)
        for node in ast.walk(annotation):
            if isinstance(node, ast.Name) and node.id == "object":
                self._report(node, OBJECT_MESSAGE)
            elif isinstance(node, ast.Name) and node.id in BUILTIN_GENERICS and id(node) not in subscripted:
                self._report(node, f"use `{BUILTIN_GENERICS[node.id]}[...]` instead of `{node.id}`")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in literal_values:
                self._check_quoted_annotation(node.value, node.lineno)

    def _check_quoted_annotation(self, annotation: str, lineno: int) -> None:
        try:
            violations = TypingConventionChecker().check(f"_: {annotation}")
        except SyntaxError:
            return
        self.violations.extend(f"line {lineno}: {violation.split(': ', 1)[1]}" for violation in violations)


def iter_ids(paths: List[Path]) -> Iterator[str]:
    for path in paths:
        yield str(path.relative_to(PROJECT_ROOT))


@pytest.mark.parametrize("path", PYTHON_FILES, ids=list(iter_ids(PYTHON_FILES)))
def test_project_follows_typing_conventions(path: Path) -> None:
    assert TypingConventionChecker().check(path.read_text(encoding="utf-8")) == []


class TestChecker:
    """The checker itself must catch every violation, and only those."""

    @pytest.mark.parametrize(
        "source",
        [
            "def f(*args: Any, **kwargs: Any) -> None: ...",
            "def f(*args: Any) -> None: ...",
            "async def f(**kwargs: typing.Any) -> None: ...",
            "def f(*args: Tuple[Any, ...]) -> None: ...",
            "from typing import Any",
            "x: Dict[str, List[int]] = {}",
            "isinstance(value, dict)",
            "items = list(values)",
            "Field(default_factory=list)",
            "# Any comment mentioning Any or dict[str, int].",
            "x: Literal['%', 'Any', 'dict[str, int]', 'ext://sys.stdout'] = '%'",
            "x: typing.Literal['Any'] = 'Any'",
            "class Model(object): ...",
            "sentinel = object()",
            "isinstance(value, object)",
            "x: Literal['object'] = 'object'",
            "x: Optional[Union[int, str]] = None",
            "def f(value: Optional[int]) -> Union[int, str]: ...",
            "class Crawler[T: Union[int, List[int]]]: ...",
            "flags = READ | WRITE",
            "x: Literal['int | None'] = 'int | None'",
        ],
    )
    def test_allowed(self, source: str) -> None:
        assert TypingConventionChecker().check(source) == []

    @pytest.mark.parametrize(
        ("source", "violation"),
        [
            ("def f(value: Any) -> None: ...", "`Any` is only allowed"),
            ("def f(*, value: Any) -> None: ...", "`Any` is only allowed"),
            ("def f(value, /, other: Any) -> None: ...", "`Any` is only allowed"),
            ("def f() -> Any: ...", "`Any` is only allowed"),
            ("async def f() -> typing.Any: ...", "`Any` is only allowed"),
            ("x: Dict[str, Any] = {}", "`Any` is only allowed"),
            ("y = cast(Any, x)", "`Any` is only allowed"),
            ("Alias = List[Any]", "`Any` is only allowed"),
            ("def f(value: 'Dict[str, Any]') -> None: ...", "`Any` is only allowed"),
            ("x: dict[str, int] = {}", "use `Dict[...]` instead of `dict[...]`"),
            ("def f(values: list[int]) -> None: ...", "use `List[...]` instead of `list[...]`"),
            ("Alias = dict[str, int]", "use `Dict[...]` instead of `dict[...]`"),
            ("def f() -> list: ...", "use `List[...]` instead of `list`"),
            ("x: dict = {}", "use `Dict[...]` instead of `dict`"),
            ("def f(value: 'list[int]') -> None: ...", "use `List[...]` instead of `list[...]`"),
            ("def f(value: object) -> None: ...", "`object` is too generic"),
            ("def f(*, value: Optional[object]) -> None: ...", "`object` is too generic"),
            ("def f() -> object: ...", "`object` is too generic"),
            ("def f(*args: object) -> None: ...", "`object` is too generic"),
            ("def f(**kwargs: object) -> None: ...", "`object` is too generic"),
            ("x: Dict[str, object] = {}", "`object` is too generic"),
            ("Alias = List[object]", "`object` is too generic"),
            ("def f(value: 'object') -> None: ...", "`object` is too generic"),
            ("x: int | None = None", "instead of the `|` operator"),
            ("x: int | str | None = None", "instead of the `|` operator"),
            ("def f(value: int | str) -> None: ...", "instead of the `|` operator"),
            ("def f() -> List[int | str]: ...", "instead of the `|` operator"),
            ("def f(*args: int | str) -> None: ...", "instead of the `|` operator"),
            ("class Crawler[T: int | List[int]]: ...", "instead of the `|` operator"),
            ("Alias = Annotated[int | str, Field()]", "instead of the `|` operator"),
            ("def f(value: 'int | None') -> None: ...", "instead of the `|` operator"),
            ("x: Union[int, None] = None", "use `Optional[...]` instead of `Union[..., None]`"),
            ("def f() -> typing.Union[int, str, None]: ...", "use `Optional[...]` instead of `Union[..., None]`"),
            ("Alias = List[Union[None, int]]", "use `Optional[...]` instead of `Union[..., None]`"),
        ],
    )
    def test_rejected(self, source: str, violation: str) -> None:
        violations = TypingConventionChecker().check(source)

        assert len(violations) == 1
        assert violation in violations[0]
        assert violations[0].startswith("line 1: ")
