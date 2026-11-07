"""Split a module into what the browser gets and what stays on the server.

`wyb build` and `wyb dev` run every application module through
[`client_source`][wybthon._split.client_source] before it goes into a
browser archive:

- The body of every top-level function decorated with
  [`server_function`][wybthon.server_function] becomes `...`. In the
  browser the decorator returns a stub that calls the server, so the body
  would never run there; removing it keeps its code, its SQL, and its
  error messages off the page.
- In a file route module (under the routes directory), the bodies of the
  module's HTTP handlers (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`) are
  removed the same way.
- A top-level import whose names only those bodies used is removed, so
  `from app.server.db import database` inside a server function's module
  is never imported in the browser.

The edit is textual and keeps every line where it was, so tracebacks in
the browser still point at the right lines of the original file.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

__all__ = ["client_source", "server_functions", "Split", "split", "HTTP_METHODS"]

HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True, slots=True)
class Split:
    """What [`split`][wybthon._split.split] found in a module.

    Attributes:
        source: The browser's source.
        functions: Names of the server functions it defines.
        handlers: Names of the HTTP handlers it defines.
    """

    source: str
    functions: tuple[str, ...]
    handlers: tuple[str, ...]


def _decorator_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Names bound to `server_function`, and names bound to the `wybthon` modules that export it."""
    names: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("wybthon", "wybthon.server_functions"):
            for alias in node.names:
                if alias.name == "server_function":
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("wybthon", "wybthon.server_functions"):
                    modules.add(alias.asname or alias.name.split(".")[0])
    return names, modules


def _is_server_decorator(node: ast.expr, names: set[str], modules: set[str]) -> bool:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id in names
    if isinstance(node, ast.Attribute) and node.attr == "server_function":
        root: ast.expr = node.value
        while isinstance(root, ast.Attribute):
            root = root.value
        return isinstance(root, ast.Name) and root.id in modules
    return False


def _bound_by(alias: ast.alias, node: ast.Import | ast.ImportFrom) -> str:
    if alias.asname:
        return alias.asname
    if isinstance(node, ast.Import):
        return alias.name.split(".")[0]
    return alias.name


def _used_names(tree: ast.Module, stripped: set[int]) -> set[str]:
    """Every name read or bound outside the stripped bodies (and named in `__all__`)."""
    used: set[str] = set()

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and id(node) in stripped:
            # The signature, decorators, and annotations stay in the browser.
            for decorator in node.decorator_list:
                visit(decorator)
            visit(node.args)
            if node.returns is not None:
                visit(node.returns)
            for param in node.type_params:
                visit(param)
            return
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # String annotations (`"User"`) and `__all__` entries name things too.
            text = node.value.strip()
            if text.isidentifier():
                used.add(text)
            elif text and len(text) < 200:
                try:
                    expression = ast.parse(text, mode="eval")
                except SyntaxError:
                    pass
                else:
                    used.update(name.id for name in ast.walk(expression) if isinstance(name, ast.Name))
        for child in ast.iter_child_nodes(node):
            visit(child)

    for statement in tree.body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            continue
        visit(statement)
    return used


def _offsets(source: str) -> list[int]:
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def split(source: str, *, handlers: bool = False) -> Split:
    """Find a module's server-only code and return the browser's version of it.

    Args:
        source: The module's source text.
        handlers: Whether the module is a file route, whose HTTP
            handlers (`GET`, `POST`, ...) are server-only too.
    """
    if "server_function" not in source and not (handlers and any(name in source for name in HTTP_METHODS)):
        return Split(source, (), ())
    tree = ast.parse(source)
    names, modules = _decorator_names(tree)
    targets: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    functions: list[str] = []
    handler_names: list[str] = []
    for statement in tree.body:
        if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if any(_is_server_decorator(decorator, names, modules) for decorator in statement.decorator_list):
            targets.append(statement)
            functions.append(statement.name)
        elif handlers and statement.name in HTTP_METHODS:
            targets.append(statement)
            handler_names.append(statement.name)
    if not targets:
        return Split(source, (), ())
    stripped = {id(node) for node in targets}
    used = _used_names(tree, stripped)
    lines = source.splitlines(keepends=True)
    starts = _offsets(source)
    edits: list[tuple[int, int, str]] = []
    for node in targets:
        begin, end = _span_text(lines, starts, node, body=True)
        edits.append((begin, end, _padded("...", source[begin:end])))
    for statement in tree.body:
        if not isinstance(statement, ast.Import | ast.ImportFrom):
            continue
        if isinstance(statement, ast.ImportFrom) and (
            statement.module == "__future__" or any(a.name == "*" for a in statement.names)
        ):
            continue
        kept = [alias for alias in statement.names if _bound_by(alias, statement) in used]
        if len(kept) == len(statement.names):
            continue
        begin, end = _span_text(lines, starts, statement)
        if kept:
            replacement = ast.unparse(
                ast.ImportFrom(module=statement.module, names=kept, level=statement.level)
                if isinstance(statement, ast.ImportFrom)
                else ast.Import(names=kept)
            )
        else:
            replacement = "pass"
        edits.append((begin, end, _padded(replacement, source[begin:end])))
    edits.sort()
    out: list[str] = []
    position = 0
    for begin, end, text in edits:
        out.append(source[position:begin])
        out.append(text)
        position = end
    out.append(source[position:])
    return Split("".join(out), tuple(functions), tuple(handler_names))


def _span_text(lines: list[str], starts: list[int], node: ast.AST, *, body: bool = False) -> tuple[int, int]:
    first: ast.AST = node.body[0] if body else node  # type: ignore[attr-defined]
    begin = starts[first.lineno - 1] + _col(lines[first.lineno - 1], first.col_offset)  # type: ignore[attr-defined]
    end_line = node.end_lineno  # type: ignore[attr-defined]
    end = starts[end_line - 1] + _col(lines[end_line - 1], node.end_col_offset)  # type: ignore[attr-defined]
    return begin, end


def _col(line: str, byte_offset: int) -> int:
    """Convert a UTF-8 byte column to a character column."""
    return len(line.encode("utf-8")[:byte_offset].decode("utf-8", "replace"))


def _padded(text: str, original: str) -> str:
    """`text`, followed by as many newlines as `original` spans, so later lines don't move."""
    return text + "\n" * original.count("\n")


def client_source(source: str, *, handlers: bool = False) -> str:
    """The browser's version of a module's source (see the module docs)."""
    return split(source, handlers=handlers).source


def server_functions(source: str) -> tuple[str, ...]:
    """Names of the server functions a module's source defines."""
    return split(source).functions
