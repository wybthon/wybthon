"""`wyb check`: type-check a project, including the props of component tags.

A component called inside an interpolation, `{Card(title=name())}`, is an
ordinary call, so mypy and pyright check its keywords against the
component's props class. A component tag, `<{Card} title={name()}/>`,
keeps its props in the template's static text, where no checker looks.

`wyb check` closes that gap. It writes a shadow copy of every Python file
in which each `html(t"...")` call also evaluates one equivalent call per
component tag, `(html(t"..."), Card(title=(name())))[0]`, runs the checker
on the shadow tree, and maps each diagnostic back to the original file.
The shadow edits only insert text on the call's last line, so every line
number stays the same, and an error inside an inserted call is reported
at the line of its tag, as `in <{Card}>: ...`.
"""

import ast
import io
import json
import keyword
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from . import templates
from .compiler import _html_names, _strings
from .templates import TemplateError

__all__ = ["Diagnostic", "check", "run", "shadow_source"]

CHECKERS = ("mypy", "pyright")

# Directories never searched for sources (besides hidden ones).
_SKIPPED_DIRS = frozenset({".venv", "venv", "dist", "build", "__pycache__", "node_modules"})
# Configuration files copied into the shadow tree, so the checker reads them.
_CONFIG_FILES = ("mypy.ini", ".mypy.ini", "setup.cfg", "pyproject.toml", "pyrightconfig.json")
_NEWLINE = re.compile(r"\r\n|\r|\n")
_MYPY_LINE = re.compile(
    r"^(?P<path>.+?):(?:(?P<line>\d+):(?:(?P<col>\d+):)?)? (?P<severity>error|note): (?P<message>.*)$"
)


@dataclass(frozen=True)
class Diagnostic:
    """One checker diagnostic, located in an original source file."""

    path: str
    line: int
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.severity}: {self.message}"


@dataclass
class _Tag:
    """The check call for one component tag."""

    label: str  # "<{Card}>"
    line: int  # the line of the tag's component expression
    source: str  # "Card(title=(name()))"
    value_lines: frozenset[int]  # lines of the expressions the call copies


@dataclass
class _Span:
    """Where a tag's check call sits in a shadow file (0-based character columns, end exclusive)."""

    line: int
    start: int
    end: int
    tag: _Tag


@dataclass
class _Shadow:
    original: Path
    text: str
    lines: list[str]
    spans: list[_Span] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shadow sources
# ---------------------------------------------------------------------------


def _is_html(node: ast.AST) -> bool:
    """Whether `node` is an `html(t"...")` call."""
    if not isinstance(node, ast.Call) or node.keywords or len(node.args) != 1:
        return False
    if not isinstance(node.args[0], ast.TemplateStr):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "html") or (
        isinstance(func, ast.Attribute) and func.attr == "html"
    )


def _is_wybthon(module: str | None) -> bool:
    return module is not None and (module == "wybthon" or module.startswith("wybthon."))


def _is_create_context(node: ast.expr | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "create_context") or (
        isinstance(func, ast.Attribute) and func.attr == "create_context"
    )


def _skipped_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Names whose tags aren't checked, and the names bound to `wybthon` packages.

    Built-ins imported from Wybthon (flow controls, boundaries, `Link`,
    contexts) and contexts made with `create_context` take children
    positionally or by their own rules. An undecorated function that takes
    neither `children` nor `**kwargs` gets the props dictionary (or its
    children positionally), so a keyword call doesn't describe it either.
    """
    names: set[str] = set()
    packages: set[str] = set()
    plain: set[str] = set()
    decorated: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and _is_wybthon(node.module):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_wybthon(alias.name):
                    packages.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Assign) and _is_create_context(node.value):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and _is_create_context(node.value):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.decorator_list:
                decorated.add(node.name)
                continue
            args = node.args
            params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
            if args.vararg is not None or (args.kwarg is None and all(p.arg != "children" for p in params)):
                plain.add(node.name)
    return names | (plain - decorated), packages


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _expr_source(source: str, node: ast.expr) -> str:
    """The expression's source text on one line."""
    text = ast.get_source_segment(source, node)
    if text is None or "\n" in text or "\r" in text:
        text = ast.unparse(node)
    return text


def _components(nodes: list[Any]) -> Iterator[templates._Component]:
    for node in nodes:
        if isinstance(node, templates._Component):
            yield node
            yield from _components(node.children)
        elif isinstance(node, templates._Element):
            yield from _components(node.children)


def _tag(
    node: templates._Component,
    items: list[ast.Interpolation],
    source: str,
    html_source: str,
    skipped: set[str],
    packages: set[str],
) -> _Tag | None:
    expr = items[node.index].value
    if isinstance(expr, ast.Name) and expr.id in skipped:
        return None
    if isinstance(expr, ast.Attribute) and _root_name(expr) in packages:
        return None
    callee = _expr_source(source, expr)
    if not isinstance(expr, (ast.Name, ast.Attribute, ast.Call, ast.Subscript)):
        callee = f"({callee})"
    args: list[tuple[str | None, str]] = []
    lines: set[int] = set()

    def put(name: str, value: str) -> None:
        args[:] = [arg for arg in args if arg[0] != name]
        args.append((name, f"{name}={value}"))

    for attr in node.attrs:
        kind = attr[0]
        if kind == templates._A_SPREAD:
            value = items[attr[1]].value
            lines.update(range(value.lineno, (value.end_lineno or value.lineno) + 1))
            args.append((None, f"**({_expr_source(source, value)})"))
            continue
        name = templates._prop_name(attr[1])
        if not name.isidentifier() or keyword.iskeyword(name):
            continue  # not a valid prop name; the compiler reports it
        if kind == templates._A_STATIC:
            put(name, "True" if attr[2] is True else repr(attr[2]))
        elif kind == templates._A_VALUE:
            item = items[attr[2]]
            value = item.value
            lines.update(range(value.lineno, (value.end_lineno or value.lineno) + 1))
            if item.conversion != -1 or item.format_spec is not None:
                put(name, '""')  # a formatted value is a string
            else:
                put(name, f"({_expr_source(source, value)})")
        else:
            put(name, '""')  # an attribute with text and interpolations is a string
    if node.children and all(arg[0] != "children" for arg in args):
        args.append(("children", f'children={html_source}(t"")'))
    label = ast.get_source_segment(source, expr) or ast.unparse(expr)
    return _Tag(
        label=f"<{{{' '.join(label.split())}}}>",
        line=expr.lineno,
        source=f"{callee}({', '.join(arg[1] for arg in args)})",
        value_lines=frozenset(lines),
    )


def shadow_source(source: str, filename: str = "<unknown>") -> tuple[str, list[tuple[int, int, int, str]]]:
    """Return `source` with a check call inserted for each component tag.

    Returns the shadow text and, for each check call, its 1-based line,
    0-based start and end character columns, and source. Mainly for tests
    and debugging; [`check`][wybthon._check.check] uses `_shadow`.
    """
    text, spans, _ = _shadow(source, filename)
    return text, [(span.line, span.start, span.end, span.tag.source) for span in spans]


def _shadow(source: str, filename: str) -> tuple[str, list[_Span], list[Diagnostic]]:
    """Insert the check calls; also returns the templates that failed to parse."""
    try:
        tree = ast.parse(source, filename)
    except SyntaxError, ValueError:
        return source, [], []  # the checker reports it
    skipped, packages = _skipped_names(tree)
    html_functions, html_packages = _html_names(tree)
    lines = _NEWLINE.split(source)
    starts = [0]
    for match in _NEWLINE.finditer(source):
        starts.append(match.end())

    def offset(line: int, col: int) -> int:
        """Character offset of a 1-based line and an ast (UTF-8 byte) column."""
        return starts[line - 1] + len(lines[line - 1].encode()[:col].decode())

    statements = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr)}
    # (offset, text, [(tag, start within text, end within text)])
    insertions: list[tuple[int, str, list[tuple[_Tag, int, int]]]] = []
    errors: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not _is_html(node):
            continue
        assert isinstance(node, ast.Call)
        literal = node.args[0]
        assert isinstance(literal, ast.TemplateStr)
        try:
            nodes = templates.parse(_strings(literal))
        except TemplateError as exc:
            # Only Wybthon's own `html` is known to take this markup.
            func = node.func
            if (isinstance(func, ast.Name) and func.id in html_functions) or (
                isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in html_packages
            ):
                errors.append(Diagnostic(filename, node.lineno, str(exc).splitlines()[0]))
            continue
        items = [value for value in literal.values if isinstance(value, ast.Interpolation)]
        html_source = _expr_source(source, node.func)
        tags = [
            tag
            for component in _components(nodes)
            if (tag := _tag(component, items, source, html_source, skipped, packages)) is not None
        ]
        if not tags:
            continue
        assert node.end_lineno is not None and node.end_col_offset is not None
        end = offset(node.end_lineno, node.end_col_offset)
        statement = id(node) in statements
        # An expression statement gets `; Card(...)`, since a bare
        # subscript would be an unused expression for pyright.
        text = "" if statement else ","
        placed: list[tuple[_Tag, int, int]] = []
        for tag in tags:
            text += "; " if statement else " "
            placed.append((tag, len(text), len(text) + len(tag.source)))
            text += tag.source
            if not statement:
                text += ","
        if not statement:
            text = text[:-1] + ")[0]"
            insertions.append((offset(node.lineno, node.col_offset), "(", []))
        insertions.append((end, text, placed))

    if not insertions:
        return source, [], errors
    insertions.sort(key=lambda insertion: insertion[0])
    pieces: list[str] = []
    located: list[tuple[int, _Tag, int, int]] = []  # (shadow offset, tag, start, end)
    last = 0
    size = 0
    for at, text, placed in insertions:
        pieces.append(source[last:at])
        size += at - last
        located.extend((size, tag, start, end) for tag, start, end in placed)
        pieces.append(text)
        size += len(text)
        last = at
    pieces.append(source[last:])
    shadow = "".join(pieces)
    shadow_starts = [0] + [match.end() for match in _NEWLINE.finditer(shadow)]
    spans: list[_Span] = []
    line = 0
    for base, tag, start, end in located:
        while line + 1 < len(shadow_starts) and shadow_starts[line + 1] <= base:
            line += 1
        col = base - shadow_starts[line]
        spans.append(_Span(line + 1, col + start, col + end, tag))
    return shadow, spans, errors


# ---------------------------------------------------------------------------
# Running a checker
# ---------------------------------------------------------------------------


def _sources(paths: Sequence[Path]) -> list[Path]:
    found: set[Path] = set()
    for path in paths:
        if path.is_file():
            if path.suffix in (".py", ".pyi"):
                found.add(path)
            continue
        for directory, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d not in _SKIPPED_DIRS and not d.startswith("."))
            found.update(Path(directory) / name for name in files if name.endswith((".py", ".pyi")))
    return sorted(found)


def _read(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding), encoding


def _char_col(line: str, col: int, unit: str) -> int:
    """Convert a checker's 0-based column (`unit`: utf-8 bytes or utf-16 code units) to characters."""
    if unit == "utf-8":
        return len(line.encode()[:col].decode(errors="ignore"))
    units = 0
    for index, char in enumerate(line):
        if units >= col:
            return index
        units += 2 if ord(char) > 0xFFFF else 1
    return len(line)


def _display(path: Path) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:  # another drive on Windows
        return str(path)


class _Mapper:
    """Maps diagnostics from the shadow tree back to the original files."""

    def __init__(self, tree: Path, root: Path, shadows: dict[str, _Shadow]) -> None:
        self.tree = tree
        self.root = root
        self.shadows = shadows
        self.plain: list[Diagnostic] = []
        self.tagged: list[tuple[Diagnostic, _Tag, str]] = []

    def add(self, path: str, line: int, col: int | None, unit: str, message: str, severity: str = "error") -> None:
        location = Path(path)
        if not location.is_absolute():
            location = self.tree / location
        try:
            relative = location.resolve().relative_to(self.tree).as_posix()
        except ValueError:
            self.plain.append(Diagnostic(_display(location), line, message, severity))
            return
        shadow = self.shadows.get(relative)
        if shadow is None:
            self.plain.append(Diagnostic(_display(self.root / relative), line, message, severity))
            return
        display = _display(shadow.original)
        if col is not None and 0 < line <= len(shadow.lines):
            char = _char_col(shadow.lines[line - 1], col, unit)
            for span in shadow.spans:
                if span.line == line and span.start <= char < span.end:
                    tagged = Diagnostic(display, span.tag.line, f"in {span.tag.label}: {message}", severity)
                    self.tagged.append((tagged, span.tag, message))
                    return
        self.plain.append(Diagnostic(display, line, message, severity))

    def results(self) -> list[Diagnostic]:
        """All diagnostics, without a tag's copy of an error already reported in the expression it copied."""
        out = set(self.plain)
        for diagnostic, tag, message in self.tagged:
            if not any(
                plain.path == diagnostic.path and plain.message == message and plain.line in tag.value_lines
                for plain in self.plain
            ):
                out.add(diagnostic)
        return sorted(out, key=lambda d: (d.path, d.line, d.message))


def _run_mypy(tree: Path, cache: Path, targets: list[str], root: Path, mapper: _Mapper) -> int:
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--no-pretty",
        "--no-color-output",
        "--show-column-numbers",
        "--show-error-codes",
        "--no-error-summary",
        "--hide-error-context",
        "--cache-dir",
        str(cache),
        *targets,
    ]
    env = dict(os.environ)
    # Modules outside the checked paths resolve from the original tree.
    env["MYPYPATH"] = os.pathsep.join(filter(None, [env.get("MYPYPATH"), str(root)]))
    result = subprocess.run(command, cwd=tree, env=env, capture_output=True, text=True, check=False)
    parsed = 0
    for text in result.stdout.splitlines():
        match = _MYPY_LINE.match(text)
        if match is None:
            continue
        parsed += 1
        if match["severity"] != "error":
            continue
        col = int(match["col"]) - 1 if match["col"] else None
        mapper.add(match["path"], int(match["line"] or 0), col, "utf-8", match["message"])
    if result.returncode not in (0, 1) and not parsed:
        sys.stderr.write(result.stdout + result.stderr)
        return 2
    return 0


def _run_pyright(executable: str, tree: Path, targets: list[str], mapper: _Mapper) -> int:
    command = [executable, "--outputjson", "--pythonpath", sys.executable, *targets]
    result = subprocess.run(command, cwd=tree, capture_output=True, text=True, check=False)
    try:
        report = json.loads(result.stdout)
    except ValueError:
        sys.stderr.write(result.stdout + result.stderr)
        return 2
    for item in report.get("generalDiagnostics", []):
        if item.get("severity") != "error":
            continue
        start = item.get("range", {}).get("start", {})
        message = " ".join(part.strip() for part in item.get("message", "").splitlines() if part.strip())
        if item.get("rule"):
            message += f"  [{item['rule']}]"
        mapper.add(item["file"], int(start.get("line", -1)) + 1, start.get("character"), "utf-16", message)
    return 0


def check(paths: Sequence[str | Path] = (".",), checker: str = "mypy") -> list[Diagnostic]:
    """Type-check `paths` with `checker`, including component tag props.

    Args:
        paths: Files and directories to check.
        checker: `"mypy"` or `"pyright"`.

    Returns:
        The checker's errors, located in the original files.

    Raises:
        FileNotFoundError: A path doesn't exist.
        RuntimeError: The checker isn't installed or failed to run.
    """
    if checker not in CHECKERS:
        raise ValueError(f"Unknown checker {checker!r}; use one of {', '.join(CHECKERS)}")
    resolved = [Path(path).resolve() for path in paths]
    for path in resolved:
        if not path.exists():
            raise FileNotFoundError(f"No such file or directory: {path}")
    executable: str | None = None
    if checker == "mypy":
        if find_spec("mypy") is None:
            raise RuntimeError("mypy isn't installed in this environment; install it with `pip install mypy`")
    else:
        executable = shutil.which("pyright")
        if executable is None:
            raise RuntimeError(
                "pyright isn't on PATH; install it with `pip install pyright` or `npm install -g pyright`"
            )

    cwd = Path.cwd().resolve()
    if all(path.is_relative_to(cwd) for path in resolved):
        root = cwd
    else:
        root = Path(os.path.commonpath([path if path.is_dir() else path.parent for path in resolved]))
    files = set(_sources(resolved))
    # Package markers above a checked path keep its module name the same.
    for path in resolved:
        for parent in path.parents:
            if not parent.is_relative_to(root):
                break
            if (parent / "__init__.py").is_file():
                files.add(parent / "__init__.py")

    with tempfile.TemporaryDirectory(prefix="wyb-check-") as temp:
        tree = Path(temp).resolve() / "tree"
        cache = Path(temp).resolve() / "cache"
        tree.mkdir()
        for name in _CONFIG_FILES:
            if (root / name).is_file():
                shutil.copyfile(root / name, tree / name)
        shadows: dict[str, _Shadow] = {}
        errors: list[Diagnostic] = []
        for path in sorted(files):
            relative = path.relative_to(root).as_posix()
            target = tree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                source, encoding = _read(path)
            except UnicodeDecodeError, SyntaxError:
                shutil.copyfile(path, target)
                continue
            text, spans, template_errors = _shadow(source, _display(path))
            errors.extend(template_errors)
            with open(target, "w", encoding=encoding, newline="") as out:
                out.write(text)
            shadows[relative] = _Shadow(path, text, _NEWLINE.split(text), spans)
        targets = [path.relative_to(root).as_posix() or "." for path in resolved]
        mapper = _Mapper(tree, root, shadows)
        if executable is None:
            status = _run_mypy(tree, cache, targets, root, mapper)
        else:
            status = _run_pyright(executable, tree, targets, mapper)
        if status:
            raise RuntimeError(f"{checker} failed to run")
    return sorted(set(errors) | set(mapper.results()), key=lambda d: (d.path, d.line, d.message))


def run(paths: Sequence[str | Path] = (".",), checker: str = "mypy") -> int:
    """What `wyb check` does: print each error as `path:line: error: message`.

    Returns:
        `0` when there are no errors, `1` when there are, and `2` when the
        checker isn't installed or couldn't run.
    """
    try:
        diagnostics = check(paths or (".",), checker)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"wyb check: {exc}", file=sys.stderr)
        return 2
    for diagnostic in diagnostics:
        print(diagnostic)
    errors = sum(1 for d in diagnostics if d.severity == "error")
    if errors:
        print(f"Found {errors} error{'s' if errors != 1 else ''}", file=sys.stderr)
        return 1
    return 0
