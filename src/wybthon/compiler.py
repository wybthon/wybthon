"""The Wybthon compiler: Solid's compile step, done on Python's syntax tree.

Solid's compiler does two things with JSX. It turns static markup into
templates, and it turns every dynamic expression in the markup into a
getter, so `{count() * 2}` stays reactive without being wrapped. This
module does both for `html(t"...")`, and two more things Solid can't do
for JavaScript: it makes a component's parameters its props, and it
makes the branches of flow controls lazy.

```python
@component
def Counter(label: str = "Count"):
    count, set_count = create_signal(0)
    return html(t"<p>{label}: {count()} doubled is {count() * 2}</p>")
```

compiles to (roughly):

```python
def Counter(__wybthon_props0__, /):
    count, set_count = create_signal(0)
    # `__wybthon_t0__` holds the literal's parse tree and mount function, built at compile time.
    return __wybthon_t0__.render(
        (lambda: __wybthon_props0__.label, lambda: count(), lambda: count() * 2)
    )


@component
@__wybthon__.props(Counter)
def Counter(label: str = "Count"): ...
```

**Component parameters are props.** Inside an `@component` function,
every read of a parameter becomes a read of the component's props
object, which returns the parent's current value and tracks it. So
`{label}` in markup is dynamic and updates when the parent passes an
expression that changes, a handler reads the latest value when it runs,
and a parameter passed on to a child (`<{Child} title={label}>`) stays
reactive. A `**rest` parameter is a reactive view of the props the
component doesn't declare, which spreads onto an element
(`<div {rest}>`). Parameters are read-only: assigning, deleting, or
declaring one `nonlocal` is a `SyntaxError`. The original function is
kept, with its body removed, so its signature (names, defaults, and
annotations) describes the props, to type checkers and at run time.

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

**Lazy branches.** The content and fallback of `Show`, `Match`,
`Switch`, `Loading`, `Errored`, and `client_only`, when written as markup
or a component call, become zero-argument functions, so a branch's
markup is built only when the branch shows, as JSX children are.

**Captured names.** A getter runs later, so the names its expression reads
from enclosing function scopes are captured by value when the template is
created (as keyword-only defaults of the getter's lambda). A template made
in a loop sees that iteration's values.

**Precompiled templates.** Each literal is parsed and validated here, so
a malformed template is a `SyntaxError` with its file and line. Its parse
tree and the mount function for each of its elements are written into
the module, and the `html(t"...")` call becomes `entry.render((...))`
with one value per interpolation, so a compiled template never builds a
t-string, parses markup, or generates code at run time.

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


# The public Wybthon names the compiler recognizes, by what it does with them.
_RECOGNIZED = frozenset(
    {"html", "component", "is_static", "Show", "Match", "Switch", "Loading", "Errored", "client_only"}
)

# The arguments of each flow control that hold content (positions, keywords):
# markup and component calls passed there become zero-argument functions.
_LAZY_ARGS: dict[str, tuple[tuple[int, ...], frozenset[str]]] = {
    "Show": ((1, 2), frozenset({"children", "fallback"})),
    "Match": ((1,), frozenset({"children"})),
    "Switch": ((), frozenset({"fallback"})),
    "Loading": ((0,), frozenset({"children", "fallback"})),
    "Errored": ((0,), frozenset({"children", "fallback"})),
    "client_only": ((0,), frozenset({"children", "fallback"})),
}


def _is_wybthon(module: str | None) -> bool:
    return module is not None and (module == "wybthon" or module.startswith("wybthon."))


def _wybthon_imports(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    """The local names bound to the Wybthon names the compiler recognizes, and the names bound to the package.

    Returns `({local name: Wybthon name}, {package names})`, so
    `from wybthon import Show as S` maps `S` to `Show`, and `import
    wybthon as w` makes `w.Show` recognized.
    """
    names: dict[str, str] = {}
    packages: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and _is_wybthon(node.module):
            for alias in node.names:
                if alias.name in _RECOGNIZED:
                    names[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_wybthon(alias.name):
                    if alias.asname is None:
                        packages.add("wybthon")
                    elif alias.name == "wybthon":
                        packages.add(alias.asname)
    return names, packages


def _html_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """The names that refer to Wybthon's `html`, and the names bound to the `wybthon` package."""
    names, packages = _wybthon_imports(tree)
    return {local for local, name in names.items() if name == "html"}, packages


def _recognized(node: ast.expr, names: dict[str, str], packages: set[str]) -> str | None:
    """The Wybthon name an expression refers to (`Show`, `w.Show`), or `None`."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute) and node.attr in _RECOGNIZED:
        root = node.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in packages:
            return node.attr
    return None


# ---------------------------------------------------------------------------
# Component parameters
# ---------------------------------------------------------------------------


def _declarations(body: list[ast.stmt]) -> tuple[set[str], set[str]]:
    """The names a function body declares `global` and `nonlocal` (not in nested scopes)."""
    globals_: set[str] = set()
    nonlocals: set[str] = set()
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Global):
            globals_.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            nonlocals.update(node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        else:
            stack.extend(ast.iter_child_nodes(node))
    return globals_, nonlocals


def _binding(body: list[ast.stmt], name: str) -> ast.AST | None:
    """The first node in a function body (not in nested scopes) that binds `name`, for error locations."""
    stack: list[ast.AST] = list(reversed(body))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name) and node.id == name and not isinstance(node.ctx, ast.Load):
            return node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return node
            continue
        if isinstance(node, ast.Lambda):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
            (alias.asname or alias.name).split(".")[0] == name for alias in node.names
        ):
            return node
        if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name == name:
            return node
        stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return None


class _PropsRewriter(ast.NodeTransformer):
    """Rewrites a component body's reads of its parameters into reads of its props object.

    `active` is the set of parameter names a scope still sees: a nested
    function, lambda, comprehension, or class that binds a name of its
    own shadows the parameter inside it.
    """

    def __init__(self, hidden: str, params: frozenset[str], static_names: set[str], fail: Any) -> None:
        self.hidden = hidden
        self.static_names = static_names
        self.fail = fail
        self.stack: list[tuple[str, frozenset[str]]] = [("function", params)]

    @property
    def active(self) -> frozenset[str]:
        return self.stack[-1][1]

    def _function_active(self) -> frozenset[str]:
        # Class bodies aren't visible to the functions defined in them.
        for kind, active in reversed(self.stack):
            if kind != "class":
                return active
        return frozenset()  # pragma: no cover - the component's own scope is a function

    def _read(self, name: str, origin: ast.AST) -> ast.expr:
        node = ast.Attribute(value=ast.Name(id=self.hidden, ctx=ast.Load()), attr=name, ctx=ast.Load())
        return ast.copy_location(node, origin)

    def _visit_list(self, nodes: list[Any]) -> list[Any]:
        out: list[Any] = []
        for node in nodes:
            result = self.visit(node)
            if result is None:
                continue
            if isinstance(result, list):
                out.extend(result)
            else:
                out.append(result)
        return out

    def _scoped(self, kind: str, active: frozenset[str], visit: Any) -> None:
        self.stack.append((kind, active))
        try:
            visit()
        finally:
            self.stack.pop()

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id not in self.active:
            return node
        if isinstance(node.ctx, ast.Load):
            return self._read(node.id, node)
        raise self.fail(node, f"{node.id!r} is a component parameter, which is a read-only prop; assign to a new name")

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # `is_static(title)` asks about the parameter, not its value.
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in self.static_names
            and len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in self.active
        ):
            name = node.args[0].id
            node.args = [
                ast.copy_location(ast.Name(id=self.hidden, ctx=ast.Load()), node.args[0]),
                ast.copy_location(ast.Constant(value=name), node.args[0]),
            ]
            return node
        return self.generic_visit(node)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
        # Decorators and defaults run in the enclosing scope; annotations are left alone.
        node.decorator_list = self._visit_list(node.decorator_list)
        node.args.defaults = self._visit_list(node.args.defaults)
        node.args.kw_defaults = [None if d is None else self.visit(d) for d in node.args.kw_defaults]
        enclosing = self._function_active()
        globals_, nonlocals = _declarations(node.body)
        for name in sorted(nonlocals & enclosing):
            raise self.fail(node, f"{name!r} is a component parameter, which is a read-only prop; it can't be nonlocal")
        scope = _Scope("function")
        _arguments(node.args, scope.names)
        _collect(scope, node.body, False)
        local = (scope.names - nonlocals) | globals_

        def body() -> None:
            node.body = self._visit_list(node.body)

        self._scoped("function", enclosing - local, body)
        return node

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        node.args.defaults = self._visit_list(node.args.defaults)
        node.args.kw_defaults = [None if d is None else self.visit(d) for d in node.args.kw_defaults]
        params: set[str] = set()
        _arguments(node.args, params)

        def body() -> None:
            node.body = self.visit(node.body)

        self._scoped("function", self._function_active() - params, body)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        node.decorator_list = self._visit_list(node.decorator_list)
        node.bases = self._visit_list(node.bases)
        node.keywords = self._visit_list(node.keywords)
        scope = _Scope("class")
        _collect(scope, node.body, False)

        def body() -> None:
            node.body = self._visit_list(node.body)

        self._scoped("class", self.active - scope.names, body)
        return node

    def _comprehension(self, node: Any) -> ast.AST:
        targets: set[str] = set()
        for generator in node.generators:
            _target_names(generator.target, targets)
        generators = node.generators
        generators[0].iter = self.visit(generators[0].iter)

        def inner() -> None:
            for index, generator in enumerate(generators):
                if index:
                    generator.iter = self.visit(generator.iter)
                generator.ifs = self._visit_list(generator.ifs)
            if isinstance(node, ast.DictComp):
                node.key = self.visit(node.key)
                node.value = self.visit(node.value)
            else:
                node.elt = self.visit(node.elt)

        self._scoped("comprehension", self.active - targets, inner)
        return node

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension


class _Components(ast.NodeTransformer):
    """Turns each `@component` function's parameters into props (see the module docstring)."""

    def __init__(self, filename: str, lines: list[str], names: dict[str, str], packages: set[str]) -> None:
        self.filename = filename
        self.lines = lines
        self.names = names
        self.packages = packages
        self.static_names = {local for local, name in names.items() if name == "is_static"}
        self.count = 0

    def fail(self, node: ast.AST, message: str) -> SyntaxError:
        line = getattr(node, "lineno", 1)
        text = self.lines[line - 1] if 0 < line <= len(self.lines) else ""
        return SyntaxError(message, (self.filename, line, getattr(node, "col_offset", 0) + 1, text))

    def _is_component(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        return any(_recognized(d, self.names, self.packages) == "component" for d in node.decorator_list)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> Any:
        if not self._is_component(node):
            return self.generic_visit(node)
        args = node.args
        if args.vararg is not None:
            raise self.fail(
                args.vararg,
                f"Component {node.name} can't take *{args.vararg.arg}; declare a `children` parameter for its content",
            )
        params = [arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
        if not params and args.kwarg is None:
            return self.generic_visit(node)
        names = frozenset(params)
        scope = _Scope("function")
        _collect(scope, node.body, False)
        for name in params:
            if name in scope.names:
                where = _binding(node.body, name) or node
                raise self.fail(
                    where, f"{name!r} is a component parameter, which is a read-only prop; assign to a new name"
                )
        hidden = f"__wybthon_props{self.count}__"
        self.count += 1
        body = copy.deepcopy(node.body)
        rewriter = _PropsRewriter(hidden, names, self.static_names, self.fail)
        body = rewriter._visit_list(body)
        prologue: list[ast.stmt] = []
        docstring = (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        )
        if docstring:
            prologue.append(body.pop(0))
        if args.kwarg is not None:
            rest = ast.Assign(
                targets=[ast.Name(id=args.kwarg.arg, ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id=hidden, ctx=ast.Load()), attr="_wyb_rest", ctx=ast.Load()),
                    args=[],
                    keywords=[],
                ),
            )
            prologue.append(ast.copy_location(rest, node))
        implementation = ast.FunctionDef(
            name=node.name,
            args=ast.arguments(
                posonlyargs=[ast.arg(arg=hidden)],
                args=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            body=prologue + body or [ast.Pass()],
            decorator_list=[],
            returns=None,
            type_params=copy.deepcopy(node.type_params),
        )
        if isinstance(node, ast.AsyncFunctionDef):
            implementation = ast.AsyncFunctionDef(**{f: getattr(implementation, f) for f in implementation._fields})  # type: ignore[assignment]
        ast.copy_location(implementation, node)
        signature_body: list[ast.stmt] = [node.body[0]] if docstring else []
        signature_body.append(ast.copy_location(ast.Expr(value=ast.Constant(value=...)), node))
        node.body = signature_body
        marker = ast.Call(func=_runtime("props"), args=[ast.Name(id=node.name, ctx=ast.Load())], keywords=[])
        node.decorator_list.append(ast.copy_location(marker, node))
        # Components defined inside this one are rewritten next, with their own props name.
        return [self.visit(implementation), node]

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function


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


def _is_render(node: ast.Call) -> bool:
    """Whether `node` is a compiled template instance: `__wybthon_tN__.render((...))`."""
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "render"
        and isinstance(func.value, ast.Name)
        and func.value.id.startswith("__wybthon_t")
    )


# What `_Compiler._interpolation` made of a slot's value: nothing, a getter
# (a lambda the slot binds), or a getter that makes no calls (probed first).
_DEFERRED = 1
_PROBED = 2


def _value(item: ast.Interpolation) -> ast.expr:
    """The value a compiled template passes for an interpolation, with any conversion or format spec applied."""
    if item.conversion == -1 and item.format_spec is None:
        return item.value
    conversion = chr(item.conversion) if item.conversion != -1 else None
    spec: ast.expr = item.format_spec if item.format_spec is not None else ast.Constant(value="")
    call = ast.Call(func=_runtime("formatted"), args=[item.value, ast.Constant(value=conversion), spec], keywords=[])
    return ast.copy_location(call, item.value)


class _Compiler(ast.NodeTransformer):
    def __init__(self, filename: str, source_lines: list[str]) -> None:
        self.filename = filename
        self.lines = source_lines
        self.functions: set[str] = set()
        self.packages: set[str] = set()
        self.names: dict[str, str] = {}
        # Positive while visiting a template interpolation's expression (and
        # not a function or lambda inside it): calls there are dispatched.
        self.template_depth = 0
        # The enclosing function, class, and comprehension scopes, innermost
        # last; the module scope isn't tracked (its names are globals).
        self.scopes: list[_Scope] = []
        self.header: list[ast.stmt] = []
        self.count = 0
        self.mounts = 0

    # -- scopes ---------------------------------------------------------------

    def _visit_scope(self, node: ast.AST, scope: _Scope) -> ast.AST:
        self.scopes.append(scope)
        depth = self.template_depth
        if scope.kind != "comprehension":
            self.template_depth = 0
        try:
            return self.generic_visit(node)
        finally:
            self.scopes.pop()
            self.template_depth = depth

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
        """Whether `node` calls Wybthon's `html` on a t-string literal (with `compiled`, or is one already compiled)."""
        if not isinstance(node, ast.Call) or node.keywords or not node.args:
            return False
        if compiled and _is_render(node):
            return True
        if len(node.args) != 1 or not isinstance(node.args[0], ast.TemplateStr):
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
            lazy = _LAZY_ARGS.get(_recognized(node.func, self.names, self.packages) or "")
            self.generic_visit(node)
            if lazy is not None:
                self._lazy(node, *lazy)
            return node
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
        deferred: list[int] = []
        values: list[ast.expr] = []
        index = 0
        for value in literal.values:
            if isinstance(value, ast.Interpolation):
                self.template_depth += 1
                try:
                    value.value = self.visit(value.value)
                finally:
                    self.template_depth -= 1
                made = self._interpolation(value, positions.get(index, "child"))
                if made:
                    deferred.append(index)
                    if made == _PROBED:
                        probes.append(index)
                values.append(_value(value))
                index += 1
        entry = self._precompile(strings, nodes, node, frozenset(probes), frozenset(deferred))
        render = ast.Attribute(value=ast.Name(id=entry, ctx=ast.Load()), attr="render", ctx=ast.Load())
        call = ast.Call(func=render, args=[ast.Tuple(elts=values, ctx=ast.Load())], keywords=[])
        return ast.copy_location(call, node)

    def _lazy(self, call: ast.Call, positions: tuple[int, ...], keywords: frozenset[str]) -> None:
        """Make a flow control's content arguments zero-argument functions, so a branch is built when it shows.

        The arguments have been compiled already. In a template, a
        component call in content is prepared as one in a child position
        is, so it still receives getters for its dynamic props.
        """
        for index in positions:
            if index < len(call.args) and self._content(call.args[index]):
                call.args[index] = self._thunk(call.args[index])
        for kw in call.keywords:
            if kw.arg in keywords and self._content(kw.value):
                kw.value = self._thunk(kw.value)

    def _thunk(self, expr: ast.expr) -> ast.Lambda:
        if self.template_depth and isinstance(expr, ast.Call) and not self._is_html(expr) and _dispatchable(expr):
            expr = self._dispatch(expr)
        return self._lambda(expr, capture=True)

    def _content(self, expr: ast.expr) -> bool:
        """Whether an argument builds content: markup, or a call of a component-like (capitalized) callee."""
        if not isinstance(expr, ast.Call) or _unmovable(expr):
            return False
        if self._is_html(expr):
            return True
        func = expr.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        return name[:1].isupper()

    def _interpolation(self, item: ast.Interpolation, position: str) -> int:
        """Compile one interpolation; returns whether it made the slot's value a getter, and of which kind.

        In an element's child or attribute the deferred expression is a
        plain lambda, and the precompiled template records which slots
        hold one (`_DEFERRED`) and which of those make no calls
        (`_PROBED`; see `_core._probe_target`). A component tag attribute
        gets a getter, which its props read.
        """
        expr = item.value
        if position in _VERBATIM or self._is_html(expr) or _unmovable(expr):
            return 0
        formatted = item.conversion != -1 or item.format_spec is not None
        if position == "child" and not formatted and isinstance(expr, ast.Call) and _dispatchable(expr):
            item.value = self._dispatch(expr)
            return 0
        if not is_dynamic(expr):
            return 0
        body = expr
        if formatted:
            conversion = chr(item.conversion) if item.conversion != -1 else None
            spec: ast.expr = item.format_spec if item.format_spec is not None else ast.Constant(value="")
            body = ast.Call(func=_runtime("fmt"), args=[expr, ast.Constant(value=conversion), spec], keywords=[])
            item.conversion = -1
            item.format_spec = None
        if position == "prop":
            item.value = self._getter(body, expr)
            return 0
        item.value = ast.copy_location(self._lambda(body, capture=True), expr)
        return _DEFERRED if _calls(expr) else _PROBED

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

    def _precompile(
        self,
        strings: tuple[str, ...],
        nodes: list[Any],
        call: ast.Call,
        probes: frozenset[int],
        deferred: frozenset[int],
    ) -> str:
        data = templates.dump(nodes)
        program = templates._program(nodes, strings)
        factories: list[ast.expr] = []
        for compiled in templates.compiled_elements(program):
            compiled.probes = probes
            compiled.deferred = deferred
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
                    ast.Constant(value=tuple(sorted(deferred))),  # type: ignore[arg-type]
                ],
                keywords=[],
            ),
        )
        self.header.append(ast.copy_location(assign, call))
        return entry


def transform(tree: ast.Module, filename: str = "<unknown>", source: str = "") -> ast.Module:
    """Compile a module's components, flow controls, and `html(t"...")` calls, in place.

    Returns the tree. A module that imports nothing the compiler
    recognizes from Wybthon is returned unchanged. Raises `SyntaxError`
    for a malformed template or a component that assigns a parameter.
    """
    names, packages = _wybthon_imports(tree)
    if not names and not packages:
        return tree
    lines = source.splitlines()
    components = _Components(filename, lines, names, packages)
    components.visit(tree)
    compiler = _Compiler(filename, lines)
    compiler.functions = {local for local, name in names.items() if name == "html"}
    compiler.packages = packages
    compiler.names = names
    compiler.visit(tree)
    if not compiler.header and not components.count:
        ast.fix_missing_locations(tree)
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
