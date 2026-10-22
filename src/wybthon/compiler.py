"""The Wybthon compiler: Solid's compile step, done on Python's syntax tree.

Solid's compiler does two things with JSX. It turns static markup into
templates, and it turns every dynamic expression in the markup into a
getter, so `{count() * 2}` stays reactive without being wrapped. This
module does both for `html(t"...")`:

```python
@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)
    return html(t"<p>{count()} doubled is {count() * 2}, step {props.step}</p>")
```

compiles to (roughly):

```python
return html(
    t"<p>{getter(lambda: count())} doubled is {getter(lambda: count() * 2)}, step {getter(lambda: props.step)}</p>",
    __wybthon_t0__,  # the literal's parse tree and mount function, built at compile time
)
```

**The rule.** An interpolation is *dynamic* when its expression contains
a call, an attribute access, or a subscript (not counting the bodies of
lambdas inside it). A dynamic interpolation becomes a getter: a hole in a
child position, a binding in an attribute, a getter prop on a component
tag. Event handlers, refs, spreads, the component in a component tag, and
nested `html(t"...")` markup are never wrapped. Anything that isn't
dynamic (a name, a constant, a lambda) is passed as is.

**Calls in child position** are dispatched when the template is created
(see `wybthon._compiled.call`): a component (`Card(title=user().name)`,
`Show(...)`, `For(...)`) is built with each dynamic argument as a getter,
the way a JSX component receives its props; any other callable
(`badge(user())`, `str(n())`) becomes one reactive expression.

**Captured names.** A getter runs later, so the names its expression reads
from enclosing function scopes are captured by value when the template is
created (as keyword-only defaults of the getter's lambda). A template made
in a loop sees that iteration's values.

**Precompiled templates.** Each literal is parsed and validated here, so
a malformed template is a `SyntaxError` with its file and line. Its parse
tree and the mount function for each of its elements are written into
the module, so `html()` never parses a template or generates code at run
time.

The compiler runs from the import hook that `import wybthon` installs,
from `wyb build` and `wyb dev`, from the pytest plugin, and from `wyb run`.
"""

from __future__ import annotations

import ast
import copy
from functools import lru_cache
from types import CodeType
from typing import Any

from . import templates
from ._hook import COMPILER_TAG, install, is_candidate, uninstall
from .templates import TemplateError

__all__ = [
    "COMPILER_TAG",
    "compile_source",
    "defers",
    "install",
    "is_candidate",
    "is_dynamic",
    "transform",
    "uninstall",
]

_RUNTIME = "__wybthon__"

# Positions whose interpolations are always passed as they are.
_VERBATIM = frozenset({"event", "ref", "spread", "tag", "prop_event"})


def is_dynamic(node: ast.AST) -> bool:
    """Whether an expression may read reactive state: it contains a call, attribute access, or subscript.

    The bodies of lambdas inside the expression don't count; they run
    whenever their caller decides.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, (ast.Call, ast.Attribute, ast.Subscript)):
            return True
        if isinstance(current, ast.Lambda):
            continue
        stack.extend(ast.iter_child_nodes(current))
    return False


def _calls(node: ast.AST) -> bool:
    """Whether an expression makes a call (outside the lambdas inside it)."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Call):
            return True
        if isinstance(current, ast.Lambda):
            continue
        stack.extend(ast.iter_child_nodes(current))
    return False


def _unmovable(node: ast.AST) -> bool:
    """Whether moving the expression into a lambda would change what it means."""
    for current in ast.walk(node):
        if isinstance(current, (ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr)):
            return True
    return False


def _handler_name(name: str | None) -> bool:
    return name is not None and (
        name == "ref" or name.startswith("on_") or (len(name) > 2 and name.startswith("on") and name[2].isupper())
    )


def _dispatchable(call: ast.Call) -> bool:
    """Whether a call in a child position might build a component, and so is dispatched at run time.

    The callee must be a plain reference whose evaluation can't read
    state: a name (`Card`, `Show`, `badge`) or a dotted name ending in a
    capitalized attribute (`ui.Card`). A method call (`item.upper()`)
    isn't a component, and a call with no arguments has no props to pass,
    so both are ordinary dynamic expressions.
    """
    if not call.args and not call.keywords:
        return False
    func = call.func
    if isinstance(func, ast.Name):
        return True
    if not isinstance(func, ast.Attribute) or not func.attr[:1].isupper():
        return False
    while isinstance(func, ast.Attribute):
        func = func.value
    return isinstance(func, ast.Name)


# ---------------------------------------------------------------------------
# Scope analysis: which names an expression reads from function scopes
# ---------------------------------------------------------------------------


def _target_names(target: ast.AST, out: set[str]) -> None:
    for node in ast.walk(target):
        if isinstance(node, ast.Name):
            out.add(node.id)


def _arguments(args: ast.arguments, out: set[str]) -> None:
    for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
        out.add(arg.arg)
    if args.vararg is not None:
        out.add(args.vararg.arg)
    if args.kwarg is not None:
        out.add(args.kwarg.arg)


class _Scope:
    """The names a function, class, or comprehension scope binds, and which of them can change.

    A name is *unstable* when its binding can change after a template
    that reads it was created: it's bound more than once, in a loop, by
    an augmented assignment or an assignment expression, or declared
    `nonlocal`. Getters capture unstable names by value; a name bound once
    is read through its closure cell like any other closure variable.
    """

    __slots__ = ("kind", "names", "unstable")

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.names: set[str] = set()
        self.unstable: set[str] = set()

    def bind(self, name: str, unstable: bool) -> None:
        if name in self.names or unstable:
            self.unstable.add(name)
        self.names.add(name)


def _bind_targets(scope: _Scope, target: ast.AST, unstable: bool) -> None:
    for node in ast.walk(target):
        if isinstance(node, ast.Name):
            scope.bind(node.id, unstable)


def _collect(scope: _Scope, nodes: list[Any], loop: bool) -> None:
    """Record the bindings of statements and expressions in `scope` (not in nested scopes)."""
    declared_global: set[str] = set()
    for node in nodes:
        _collect_node(scope, node, loop, declared_global)
    scope.names -= declared_global
    scope.unstable -= declared_global


def _collect_node(scope: _Scope, node: ast.AST, loop: bool, declared_global: set[str]) -> None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        scope.bind(node.name, loop)
        children: list[ast.AST] = list(node.decorator_list)
        if not isinstance(node, ast.ClassDef):
            children += node.args.defaults
            children += [d for d in node.args.kw_defaults if d is not None]
        for child in children:
            _collect_node(scope, child, loop, declared_global)
        return
    if isinstance(node, ast.Lambda):
        for child in (*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)):
            _collect_node(scope, child, loop, declared_global)
        return
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        # Comprehension targets are their own scope; an assignment
        # expression inside one binds in the enclosing function.
        for inner in ast.walk(node):
            if isinstance(inner, ast.NamedExpr):
                _bind_targets(scope, inner.target, True)
        return
    if isinstance(node, ast.Global):
        declared_global.update(node.names)
        return
    if isinstance(node, ast.Nonlocal):
        for name in node.names:
            scope.bind(name, True)
        return
    if isinstance(node, (ast.For, ast.AsyncFor)):
        _bind_targets(scope, node.target, True)
        _collect_node(scope, node.iter, loop, declared_global)
        for child in (*node.body, *node.orelse):
            _collect_node(scope, child, True, declared_global)
        return
    if isinstance(node, ast.While):
        _collect_node(scope, node.test, True, declared_global)
        for child in (*node.body, *node.orelse):
            _collect_node(scope, child, True, declared_global)
        return
    if isinstance(node, ast.AugAssign):
        _bind_targets(scope, node.target, True)
        _collect_node(scope, node.value, loop, declared_global)
        return
    if isinstance(node, ast.NamedExpr):
        _bind_targets(scope, node.target, True)
        _collect_node(scope, node.value, loop, declared_global)
        return
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        scope.bind(node.id, loop)
        return
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            if alias.name != "*":
                scope.bind((alias.asname or alias.name).split(".")[0], loop)
        return
    if isinstance(node, ast.ExceptHandler) and node.name:
        scope.bind(node.name, loop)
    elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
        scope.bind(node.name, loop)
    elif isinstance(node, ast.MatchMapping) and node.rest:
        scope.bind(node.rest, loop)
    for child in ast.iter_child_nodes(node):
        _collect_node(scope, child, loop, declared_global)


def _free_names(node: ast.AST) -> list[str]:
    """Names an expression reads that it doesn't bind itself, in first-use order."""
    found: dict[str, None] = {}

    def visit(current: ast.AST, bound: frozenset[str]) -> None:
        if isinstance(current, ast.Name):
            if isinstance(current.ctx, ast.Load) and current.id not in bound:
                found[current.id] = None
            return
        if isinstance(current, ast.Lambda):
            inner: set[str] = set()
            _arguments(current.args, inner)
            for default in (*current.args.defaults, *(d for d in current.args.kw_defaults if d is not None)):
                visit(default, bound)
            visit(current.body, bound | inner)
            return
        if isinstance(current, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            inner = set()
            for generator in current.generators:
                _target_names(generator.target, inner)
            scope = bound | inner
            for index, generator in enumerate(current.generators):
                # The first iterable is evaluated in the enclosing scope.
                visit(generator.iter, bound if index == 0 else scope)
                for condition in generator.ifs:
                    visit(condition, scope)
            if isinstance(current, ast.DictComp):
                visit(current.key, scope)
                visit(current.value, scope)
            else:
                visit(current.elt, scope)
            return
        for child in ast.iter_child_nodes(current):
            visit(child, bound)

    visit(node, frozenset())
    return list(found)


# ---------------------------------------------------------------------------
# The transform
# ---------------------------------------------------------------------------


def _html_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """The names that refer to Wybthon's `html`, and the names bound to the `wybthon` package."""
    functions: set[str] = set()
    packages: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in ("wybthon", "wybthon.templates"):
            for alias in node.names:
                if alias.name == "html":
                    functions.add(alias.asname or "html")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "wybthon" or alias.name.startswith("wybthon."):
                    if alias.asname is None:
                        packages.add("wybthon")
                    elif alias.name == "wybthon":
                        packages.add(alias.asname)
    return functions, packages


def _strings(node: ast.TemplateStr) -> tuple[str, ...]:
    """The static strings of a t-string literal, as `Template.strings` will hold them."""
    out: list[str] = []
    current: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Interpolation):
            out.append("".join(current))
            current = []
        else:
            assert isinstance(value, ast.Constant) and isinstance(value.value, str)
            current.append(value.value)
    out.append("".join(current))
    return tuple(out)


def _runtime(attr: str) -> ast.Attribute:
    return ast.Attribute(value=ast.Name(id=_RUNTIME, ctx=ast.Load()), attr=attr, ctx=ast.Load())


class _Compiler(ast.NodeTransformer):
    def __init__(self, filename: str, source_lines: list[str]) -> None:
        self.filename = filename
        self.lines = source_lines
        self.functions: set[str] = set()
        self.packages: set[str] = set()
        # The enclosing function, class, and comprehension scopes, innermost
        # last; the module scope isn't tracked (its names are globals).
        self.scopes: list[_Scope] = []
        self.header: list[ast.stmt] = []
        self.count = 0
        self.mounts = 0

    # -- scopes ---------------------------------------------------------------

    def _visit_scope(self, node: ast.AST, scope: _Scope) -> ast.AST:
        self.scopes.append(scope)
        try:
            return self.generic_visit(node)
        finally:
            self.scopes.pop()

    def _function_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> _Scope:
        scope = _Scope("function")
        params: set[str] = set()
        _arguments(node.args, params)
        for name in params:
            scope.bind(name, False)
        _collect(scope, node.body if isinstance(node.body, list) else [node.body], False)
        return scope

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_scope(node, self._function_scope(node))

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_scope(node, self._function_scope(node))

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        return self._visit_scope(node, self._function_scope(node))

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        scope = _Scope("class")
        _collect(scope, node.body, False)
        return self._visit_scope(node, scope)

    def _visit_comprehension(self, node: ast.AST) -> ast.AST:
        scope = _Scope("comprehension")
        for generator in node.generators:  # type: ignore[attr-defined]
            _bind_targets(scope, generator.target, True)
        return self._visit_scope(node, scope)

    visit_ListComp = _visit_comprehension
    visit_SetComp = _visit_comprehension
    visit_DictComp = _visit_comprehension
    visit_GeneratorExp = _visit_comprehension

    def _captured(self, node: ast.AST) -> list[str]:
        """The names `node` reads that a getter must capture by value.

        A name resolves in the innermost enclosing scope that binds it.
        It's captured when its binding there can change after the
        template is created, and when that scope is a class body the
        template sits directly in (a lambda can't see class names).
        """
        out: list[str] = []
        for name in _free_names(node):
            if name == _RUNTIME:
                continue
            innermost = True
            for scope in reversed(self.scopes):
                if scope.kind == "class" and not innermost:
                    continue
                innermost = False
                if name in scope.names:
                    if scope.kind == "class" or name in scope.unstable:
                        out.append(name)
                    break
        return out

    # -- html() calls -----------------------------------------------------------

    def _is_html(self, node: ast.AST, compiled: bool = True) -> bool:
        """Whether `node` is a call of Wybthon's `html` on a t-string literal (or one already compiled)."""
        if not isinstance(node, ast.Call) or node.keywords or not node.args:
            return False
        if not isinstance(node.args[0], ast.TemplateStr):
            return False
        if len(node.args) == 2:
            entry = node.args[1]
            if not (compiled and isinstance(entry, ast.Name) and entry.id.startswith("__wybthon_t")):
                return False
        elif len(node.args) != 1:
            return False
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in self.functions
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "html"
            and isinstance(func.value, ast.Name)
            and func.value.id in self.packages
        )

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if not self._is_html(node, compiled=False):
            return self.generic_visit(node)
        literal = node.args[0]
        assert isinstance(literal, ast.TemplateStr)
        strings = _strings(literal)
        try:
            nodes = templates.parse(strings)
        except TemplateError as exc:
            line = node.lineno
            raise SyntaxError(
                str(exc),
                (self.filename, line, node.col_offset + 1, self.lines[line - 1] if line <= len(self.lines) else ""),
            ) from None
        positions = templates.slot_positions(nodes)
        probes: list[int] = []
        index = 0
        for value in literal.values:
            if isinstance(value, ast.Interpolation):
                value.value = self.visit(value.value)
                if self._interpolation(value, positions.get(index, "child")):
                    probes.append(index)
                index += 1
        node.args.append(ast.Name(id=self._precompile(strings, nodes, node, frozenset(probes)), ctx=ast.Load()))
        return node

    def _interpolation(self, item: ast.Interpolation, position: str) -> bool:
        """Compile one interpolation; returns whether its binding should be probed first.

        In an element's child or attribute the deferred expression is a
        plain lambda: the precompiled template records which slots it
        made, and which of them make no calls (see `_core._probe`). A
        component tag attribute gets a getter, which its props read.
        """
        expr = item.value
        if position in _VERBATIM or self._is_html(expr) or _unmovable(expr):
            return False
        formatted = item.conversion != -1 or item.format_spec is not None
        if position == "child" and not formatted and isinstance(expr, ast.Call) and _dispatchable(expr):
            item.value = self._dispatch(expr)
            return False
        if not is_dynamic(expr):
            return False
        body = expr
        if formatted:
            conversion = chr(item.conversion) if item.conversion != -1 else None
            spec: ast.expr = item.format_spec if item.format_spec is not None else ast.Constant(value="")
            body = ast.Call(func=_runtime("fmt"), args=[expr, ast.Constant(value=conversion), spec], keywords=[])
            item.conversion = -1
            item.format_spec = None
        if position == "prop":
            item.value = self._getter(body, expr)
            return False
        item.value = ast.copy_location(self._lambda(body, capture=True), expr)
        return not _calls(expr)

    def _argument(self, expr: ast.expr) -> ast.expr:
        """Prepare an argument of a component call: dynamic expressions become getters."""
        if isinstance(expr, ast.Starred) or self._is_html(expr) or _unmovable(expr):
            return expr
        if isinstance(expr, ast.Call) and _dispatchable(expr):
            return self._dispatch(expr)
        if is_dynamic(expr):
            return self._getter(expr, expr)
        return expr

    def _dispatch(self, call: ast.Call) -> ast.expr:
        """`__wybthon__.call(f, lambda: f(...), lambda: f(<getters>...))` for a call in child position."""
        deferred = self._lambda(copy.deepcopy(call), capture=True)
        prepared_call = ast.Call(
            func=copy.deepcopy(call.func),
            args=[self._argument(arg) for arg in call.args],
            keywords=[
                ast.keyword(
                    arg=kw.arg,
                    value=kw.value if kw.arg is None or _handler_name(kw.arg) else self._argument(kw.value),
                )
                for kw in call.keywords
            ],
        )
        prepared = self._lambda(prepared_call, capture=False)
        result = ast.Call(func=_runtime("call"), args=[copy.deepcopy(call.func), deferred, prepared], keywords=[])
        return ast.copy_location(result, call)

    def _getter(self, body: ast.expr, origin: ast.expr) -> ast.expr:
        args: list[ast.expr] = [self._lambda(body, capture=True)]
        if not _calls(origin):
            # No calls: probably reads nothing reactive (see `_core._probe`).
            args.append(ast.Constant(value=True))
        result = ast.Call(func=_runtime("getter"), args=args, keywords=[])
        return ast.copy_location(result, origin)

    def _lambda(self, body: ast.expr, *, capture: bool) -> ast.Lambda:
        names = self._captured(body) if capture else []
        node = ast.Lambda(
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                vararg=None,
                kwonlyargs=[ast.arg(arg=name) for name in names],
                kw_defaults=[ast.Name(id=name, ctx=ast.Load()) for name in names],
                kwarg=None,
                defaults=[],
            ),
            body=body,
        )
        return ast.copy_location(node, body)

    # -- precompiled entries ----------------------------------------------------

    def _precompile(self, strings: tuple[str, ...], nodes: list[Any], call: ast.Call, probes: frozenset[int]) -> str:
        data = templates.dump(nodes)
        program = templates._program(nodes, strings)
        factories: list[ast.expr] = []
        for compiled in templates.compiled_elements(program):
            compiled.probes = probes
            name = f"__wybthon_m{self.mounts}__"
            self.mounts += 1
            function = ast.parse(templates.mount_source(compiled, name)).body[0]
            for inner in ast.walk(function):
                if hasattr(inner, "lineno"):
                    inner.lineno = inner.end_lineno = call.lineno  # type: ignore[attr-defined]
                    inner.col_offset = inner.end_col_offset = call.col_offset  # type: ignore[attr-defined]
            self.header.append(function)
            factories.append(ast.Name(id=name, ctx=ast.Load()))
        entry = f"__wybthon_t{self.count}__"
        self.count += 1
        assign = ast.Assign(
            targets=[ast.Name(id=entry, ctx=ast.Store())],
            value=ast.Call(
                func=_runtime("template"),
                args=[
                    # Tuples of constants are valid constants; typeshed doesn't say so.
                    ast.Constant(value=strings),  # type: ignore[arg-type]
                    ast.Constant(value=data),  # type: ignore[arg-type]
                    ast.Tuple(elts=factories, ctx=ast.Load()),
                    ast.Constant(value=tuple(sorted(probes))),  # type: ignore[arg-type]
                ],
                keywords=[],
            ),
        )
        self.header.append(ast.copy_location(assign, call))
        return entry


def transform(tree: ast.Module, filename: str = "<unknown>", source: str = "") -> ast.Module:
    """Compile the `html(t"...")` calls in a module's syntax tree, in place.

    Returns the tree. A module that doesn't import Wybthon's `html` is
    returned unchanged. Raises `SyntaxError` for a malformed template.
    """
    compiler = _Compiler(filename, source.splitlines())
    compiler.functions, compiler.packages = _html_names(tree)
    if not compiler.functions and not compiler.packages:
        return tree
    compiler.visit(tree)
    if not compiler.header:
        return tree
    body = tree.body
    position = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        position = 1
    while position < len(body):
        statement = body[position]
        if not (isinstance(statement, ast.ImportFrom) and statement.module == "__future__"):
            break
        position += 1
    anchor = body[position] if position < len(body) else None
    runtime = ast.Import(names=[ast.alias(name="wybthon._compiled", asname=_RUNTIME)])
    inserted: list[ast.stmt] = [runtime, *compiler.header]
    for stmt in inserted:
        for node in ast.walk(stmt):
            if hasattr(node, "lineno") and getattr(node, "lineno", None) is None:
                node.lineno = node.end_lineno = anchor.lineno if anchor is not None else 1  # type: ignore[attr-defined]
    if anchor is not None:
        ast.copy_location(runtime, anchor)
    body[position:position] = inserted
    ast.fix_missing_locations(tree)
    return tree


def compile_source(source: str | bytes, filename: str) -> CodeType:
    """Compile a module's source with its templates compiled."""
    text = source if isinstance(source, str) else _decode(source)
    tree = ast.parse(text, filename=filename)
    if is_candidate(text.encode("utf-8", "surrogatepass") if isinstance(source, str) else source):
        transform(tree, filename, text)
    code: CodeType = compile(tree, filename, "exec", dont_inherit=True)
    return code


def _decode(source: bytes) -> str:
    from importlib.util import decode_source

    return decode_source(source)


@lru_cache(maxsize=4096)
def defers(expression: str, position: str) -> bool:
    """Whether the compiler would defer an interpolation's expression (dev-mode checks).

    `html()` asks this about templates that reach it uncompiled: their
    dynamic expressions have already been evaluated once.
    """
    if position in _VERBATIM:
        return False
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError:
        return False
    expr = tree.body
    if _unmovable(expr):
        return False
    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Name) and func.id == "html":
            return False
        if position == "child" and _dispatchable(expr):
            return any(
                is_dynamic(arg) and not (isinstance(arg, ast.Call) and _dispatchable(arg)) for arg in expr.args
            ) or any(not _handler_name(kw.arg) and is_dynamic(kw.value) for kw in expr.keywords)
    return is_dynamic(expr)
