"""Typed props and public signatures, checked by mypy and pyright with no plugin.

`tests/typing/valid.py` must type-check cleanly. Every line of
`tests/typing/invalid.py` marked `# error: <kind>` must be reported, and no
other line may be.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "typing"
VALID = FIXTURES / "valid.py"
INVALID = FIXTURES / "invalid.py"

# What each checker says for each kind of mistake (a substring of its message).
EXPECTED = {
    "assign-prop": {"mypy": 'Property "name" defined in "StrictProps" is read-only', "pyright": "read-only"},
    "missing-prop": {"mypy": 'Missing named argument "name"', "pyright": 'Argument missing for parameter "name"'},
    "wrong-type": {"mypy": 'Argument "name" to "StrictProps" has incompatible type "int"', "pyright": "Literal[42]"},
    "unknown-prop": {"mypy": 'Unexpected keyword argument "typo"', "pyright": 'No parameter named "typo"'},
    "no-props": {"mypy": 'Unexpected keyword argument "title" for "Bare"', "pyright": 'No parameter named "title"'},
    "accessor-is-not-value": {"mypy": 'expression has type "Accessor[str]"', "pyright": '"Accessor[str]"'},
    "action-arg": {"mypy": 'incompatible type "str"; expected "int"', "pyright": "Literal['wrong']"},
    "store-append": {"mypy": 'TypedDict item "age" has type "int"', "pyright": '"Person"'},
    "for-row": {"mypy": 'TypedDict "Todo" has no key "titel"', "pyright": '"titel"'},
    "html-arg": {"mypy": 'Argument 1 to "html" has incompatible type "str"', "pyright": '"Template"'},
}


def expected_errors() -> dict[int, str]:
    """Map each marked line of the invalid fixture to its error kind."""
    marked = {}
    for number, line in enumerate(INVALID.read_text().splitlines(), start=1):
        match = re.search(r"# error: ([\w-]+)$", line)
        if match:
            marked[number] = match.group(1)
    return marked


def test_invalid_fixture_marks_every_expected_kind():
    assert sorted(set(expected_errors().values())) == sorted(EXPECTED)


def test_no_mypy_plugin_is_configured():
    assert "plugins" not in (ROOT / "mypy.ini").read_text()
    with pytest.raises(ModuleNotFoundError):
        __import__("wybthon.mypy_plugin")


# ---------------------------------------------------------------------------
# mypy
# ---------------------------------------------------------------------------


def run_mypy(path: Path) -> tuple[int, dict[int, list[str]]]:
    command = [sys.executable, "-m", "mypy", "--strict", "--no-pretty", "--follow-imports=silent", str(path)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    errors: dict[int, list[str]] = {}
    for line in result.stdout.splitlines():
        match = re.match(rf"{re.escape(str(path.relative_to(ROOT)))}:(\d+): error: (.*)", line) or re.match(
            rf"{re.escape(str(path))}:(\d+): error: (.*)", line
        )
        if match:
            errors.setdefault(int(match.group(1)), []).append(match.group(2))
    assert result.returncode in (0, 1), result.stdout + result.stderr
    return result.returncode, errors


def test_mypy_accepts_valid_fixture():
    code, errors = run_mypy(VALID)
    assert errors == {}
    assert code == 0


def test_mypy_reports_invalid_fixture():
    code, errors = run_mypy(INVALID)
    assert code == 1
    marked = expected_errors()
    assert sorted(errors) == sorted(marked), errors
    for line, kind in marked.items():
        assert any(EXPECTED[kind]["mypy"] in message for message in errors[line]), (kind, errors[line])


# ---------------------------------------------------------------------------
# pyright
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pyright(tmp_path_factory):
    npx = shutil.which("npx")
    if npx is None:
        pytest.skip("npx isn't installed, so pyright can't run")
    config_dir = tmp_path_factory.mktemp("pyright")
    config = config_dir / "pyrightconfig.json"
    config.write_text(
        json.dumps({"pythonVersion": "3.14", "extraPaths": [str(ROOT / "src")], "typeCheckingMode": "standard"})
    )

    def run(path: Path) -> dict[int, list[str]]:
        try:
            result = subprocess.run(
                [npx, "-y", "pyright@latest", "--outputjson", "-p", str(config), str(path)],
                cwd=config_dir,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pytest.skip("pyright timed out (is the npm registry reachable?)")
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            pytest.skip(f"pyright is unavailable offline: {result.stderr.strip()[:300]}")
        errors: dict[int, list[str]] = {}
        for diagnostic in report["generalDiagnostics"]:
            if diagnostic["severity"] == "error":
                line = diagnostic["range"]["start"]["line"] + 1
                errors.setdefault(line, []).append(diagnostic["message"])
        return errors

    return run


def test_pyright_accepts_valid_fixture(pyright):
    assert pyright(VALID) == {}


def test_pyright_reports_invalid_fixture(pyright):
    errors = pyright(INVALID)
    marked = expected_errors()
    assert sorted(errors) == sorted(marked), errors
    for line, kind in marked.items():
        assert any(EXPECTED[kind]["pyright"] in message for message in errors[line]), (kind, errors[line])


# ---------------------------------------------------------------------------
# The valid fixture also runs
# ---------------------------------------------------------------------------


def test_typed_component_fixture_executes_in_renderer(wyb, root_element):
    import runpy

    from conftest import collect_texts

    from wybthon import create_signal, flush

    fixture = runpy.run_path(str(VALID))
    name, rename = create_signal("Ada")
    count, set_count = create_signal(2)
    root = wyb["reconciler"].render(fixture["Greeting"](name=name, count=count), root_element)
    assert "AdaAda" in collect_texts(root_element.element)
    rename("Grace")
    set_count(1)
    flush()
    assert "Grace" in collect_texts(root_element.element)
    root.dispose()

    root = wyb["reconciler"].render(fixture["Card"](title="Hi")[fixture["App"]()], root_element)
    assert [text for text in collect_texts(root_element.element) if text.strip()] == ["Hi", "Ada", "GraceGrace"]
    root.dispose()
