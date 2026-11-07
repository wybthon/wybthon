"""`wyb check`: type-checking component tag props with mypy and pyright."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from wybthon import _check
from wybthon.dev import main

# The sample apps are string literals, so the test plugin doesn't compile them.
# Their functions leave the return type to the checker, so they don't depend
# on what `html` is annotated to return.
COMPONENTS = """
from wybthon import ParentProps, Props, component, html


class CardProps(Props):
    title: str
    count: int = 0


class BoxProps(ParentProps):
    label: str


@component
def Card(props: CardProps):
    return html(t"<p>{props.title} {props.count}</p>")


@component
def Box(props: BoxProps):
    return html(t"<div>{props.children}</div>")
"""

INVALID = '''
from wybthon import For, Show, create_context, html

from app.components import Box, Card

Theme = create_context("light")


def page(names: list[str], counts: list[int]):
    return html(t"""<main>
      <{Card} title="a" bogus={1}/>
      <{Card}
        title="b" count={"x"}/>
      <{Card} count={2}/>
      <{Card} title="c"><p>no children field</p></{Card}>
      <{Box} label="ok"><p>children</p></{Box}>
      <{Show} when={True}><p>built-in</p></{Show}>
      <{Theme} value="dark"><p>provider</p></{Theme}>
      {For(names, lambda name, i: html(t"<{Card} title={name} count={name}/>"))}
      {For(counts, lambda n, i: html(t"<{Card} title={str(n)} count={n}/>"))}
    </main>""")


after: int = "not an int"
'''

VALID = '''
from wybthon import For, html

from app.components import Box, Card


def page(items: list[int]):
    return html(t"""<{Box} label="list">
      {For(items, lambda item, i: html(t"<{Card} title={str(item)} count={item}/>"))}
      <{Card} title="total" count={len(items)}/>
    </{Box}>""")
'''


def write_project(root: Path, pages: dict[str, str]) -> None:
    app = root / "app"
    app.mkdir(parents=True)
    (app / "__init__.py").write_text("")
    (app / "components.py").write_text(COMPONENTS)
    for name, source in pages.items():
        (app / name).write_text(source)


def line_of(source: str, needle: str) -> int:
    (number,) = [n for n, line in enumerate(source.splitlines(), start=1) if needle in line]
    return number


@pytest.fixture(scope="module")
def invalid_errors(tmp_path_factory: pytest.TempPathFactory) -> dict[int, list[str]]:
    root = tmp_path_factory.mktemp("invalid")
    write_project(root, {"pages.py": INVALID})
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(root)
        diagnostics = _check.check(["."])
    errors: dict[int, list[str]] = {}
    for diagnostic in diagnostics:
        assert diagnostic.path == "app/pages.py", diagnostic
        errors.setdefault(diagnostic.line, []).append(diagnostic.message)
    return errors


def test_unknown_prop_reports_at_the_tag_line(invalid_errors):
    messages = invalid_errors[line_of(INVALID, "bogus=")]
    assert messages == ['in <{Card}>: Unexpected keyword argument "bogus" for "CardProps"  [call-arg]']


def test_wrong_typed_prop_reports_at_the_tag_line(invalid_errors):
    # The tag spans two lines; the error is reported where `{Card}` is.
    line = line_of(INVALID, 'count={"x"}') - 1
    assert invalid_errors[line] == [
        'in <{Card}>: Argument "count" to "CardProps" has incompatible type "str"; expected "int"  [arg-type]'
    ]


def test_missing_required_prop(invalid_errors):
    messages = invalid_errors[line_of(INVALID, "<{Card} count={2}/>")]
    assert messages == ['in <{Card}>: Missing named argument "title" for "CardProps"  [call-arg]']


def test_children_on_a_component_without_children(invalid_errors):
    messages = invalid_errors[line_of(INVALID, "no children field")]
    assert messages == ['in <{Card}>: Unexpected keyword argument "children" for "CardProps"  [call-arg]']


def test_nested_template_checks_with_lambda_parameters_in_scope(invalid_errors):
    messages = invalid_errors[line_of(INVALID, "For(names")]
    assert messages == [
        'in <{Card}>: Argument "count" to "CardProps" has incompatible type "str"; expected "int"  [arg-type]'
    ]
    assert line_of(INVALID, "For(counts") not in invalid_errors


def test_builtins_and_children_props_are_not_reported(invalid_errors):
    for needle in ("<{Box}", "<{Show}", "<{Theme}"):
        assert line_of(INVALID, needle) not in invalid_errors


def test_ordinary_errors_keep_their_line(invalid_errors):
    line = line_of(INVALID, "after: int")
    assert invalid_errors[line] == [
        'Incompatible types in assignment (expression has type "str", variable has type "int")  [assignment]'
    ]
    assert len(invalid_errors) == 6


def test_valid_project_passes(tmp_path, monkeypatch, capsys):
    write_project(tmp_path, {"pages.py": VALID})
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 0
    assert capsys.readouterr().out == ""


def test_run_prints_errors_and_fails(tmp_path, monkeypatch, capsys):
    source = COMPONENTS + '\n\nview = html(t"<{Card} title={1}/>")\n'
    (tmp_path / "view.py").write_text(source)
    monkeypatch.chdir(tmp_path)
    assert main(["check", "view.py"]) == 1
    out = capsys.readouterr().out
    line = line_of(source, "view = ")
    assert out.startswith(f'view.py:{line}: error: in <{{Card}}>: Argument "title" to "CardProps"')


def test_shadow_source_keeps_line_numbers():
    source = 'from app import Card, html\n\nx = html(t"""<div>\n  <{Card} title="a"/>\n</div>""")  # end\ny = 1\n'
    shadow, spans = _check.shadow_source(source)
    assert shadow.splitlines()[:2] == source.splitlines()[:2]
    assert len(shadow.splitlines()) == len(source.splitlines())
    assert shadow.splitlines()[4] == '</div>"""), Card(title=\'a\'))[0]  # end'
    ((line, start, end, call),) = spans
    assert (line, call) == (5, "Card(title='a')")
    assert shadow.splitlines()[4][start:end] == call


def test_shadow_source_props():
    source = (
        "from app import Card, html\n"
        "html(t\"<{Card} class='a' for={b} data-x='p{c}' disabled {d} title={e!r} on_close={f}/>\")\n"
    )
    shadow, spans = _check.shadow_source(source)
    # An expression statement gets the checks as statements of their own.
    assert shadow.endswith(
        '; Card(class_=\'a\', html_for=(b), data_x="", disabled=True, **(d), title="", on_close=(f))\n'
    )
    assert len(spans) == 1


def test_missing_checker_exits_2(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert main(["check", "--checker", "pyright"]) == 2
    assert "pyright isn't on PATH" in capsys.readouterr().err


FAKE_PYRIGHT = """
import json, os, sys
from pathlib import Path

# Report an error at the inserted check call for every `bogus` prop.
diagnostics = []
for path in sorted(Path.cwd().rglob("*.py")):
    for number, line in enumerate(path.read_text().splitlines()):
        column = line.find("bogus=")
        if column != -1 and line.rfind("<{", 0, column) == -1:
            diagnostics.append({
                "file": str(path),
                "severity": "error",
                "message": 'No parameter named "bogus"',
                "rule": "reportCallIssue",
                "range": {"start": {"line": number, "character": column}},
            })
json.dump({"generalDiagnostics": diagnostics}, sys.stdout)
"""


def test_pyright_results_map_to_tags(tmp_path, monkeypatch):
    fake = tmp_path / "bin" / "pyright"
    fake.parent.mkdir()
    fake.write_text(f"#!{sys.executable}\n{FAKE_PYRIGHT}")
    fake.chmod(0o755)
    project = tmp_path / "project"
    write_project(project, {"pages.py": INVALID})
    monkeypatch.chdir(project)
    monkeypatch.setattr(shutil, "which", lambda name: str(fake))
    diagnostics = _check.check(["app"], checker="pyright")
    assert [(d.path, d.line, d.message) for d in diagnostics] == [
        ("app/pages.py", line_of(INVALID, "bogus="), 'in <{Card}>: No parameter named "bogus"  [reportCallIssue]')
    ]


@pytest.mark.skipif(shutil.which("pyright") is None, reason="pyright isn't on PATH")
def test_pyright_reports_tag_props(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project(tmp_path, {"pages.py": INVALID})
    (tmp_path / "pyrightconfig.json").write_text(json.dumps({"pythonVersion": "3.14"}))
    monkeypatch.chdir(tmp_path)
    errors: dict[int, list[str]] = {}
    for diagnostic in _check.check(["."], checker="pyright"):
        errors.setdefault(diagnostic.line, []).append(diagnostic.message)
    assert any('"bogus"' in message for message in errors[line_of(INVALID, "bogus=")])
    assert any('"title"' in message for message in errors[line_of(INVALID, "<{Card} count={2}/>")])
    assert line_of(INVALID, "<{Show}") not in errors


def test_malformed_template_is_reported():
    source = 'from wybthon import html\nfrom other import html as other\n\nx = html(t"<p>")\ny = other.html(t"<p>")\n'
    _, _, errors = _check._shadow(source, "view.py")
    assert [(e.path, e.line, e.message) for e in errors] == [("view.py", 4, "Unclosed tag <p>")]
