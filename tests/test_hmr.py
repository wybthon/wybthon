"""Hot module replacement for `wyb dev` (RFC 0006): modules are replaced in place and their components remounted."""

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

from wybthon import _hmr, flush, reconciler
from wybthon.dev import _hot_update
from wybthon.testing import fire, render

STATE = """from wybthon import create_signal

clicks, set_clicks = create_signal(0)
"""

CARD = """from wybthon import component, html


@component
def Card(title: str):
    return html(t"<h2>{title}</h2>")
"""

APP = """from wybthon import component, create_signal, html

from hotapp.card import Card
from hotapp.state import clicks, set_clicks


def label(n):
    return f"clicked {n}"


@component
def Counter():
    local, set_local = create_signal(0)

    def bump():
        set_local(lambda n: n + 1)
        set_clicks(lambda n: n + 1)

    return html(t"<button onclick={bump}>{label(clicks())} / {local()}</button>")


@component
def App():
    return html(t"<main><{Card} title='Hello' /><{Counter} /><p>footer</p></main>")
"""


@pytest.fixture
def hotapp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    package = tmp_path / "hotapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "state.py").write_text(STATE)
    (package / "card.py").write_text(CARD)
    (package / "app.py").write_text(APP)
    monkeypatch.syspath_prepend(str(tmp_path))
    previous = reconciler._hot_track
    _hmr.enable()
    try:
        yield package
    finally:
        reconciler._hot_track = previous
        _hmr._live.clear()
        for name in [name for name in sys.modules if name == "hotapp" or name.startswith("hotapp.")]:
            del sys.modules[name]


def _edit(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text().replace(old, new))


def test_a_changed_component_remounts_in_place_and_shared_state_survives(wyb, hotapp: Path):
    app = importlib.import_module("hotapp.app")
    with render(app.App()) as screen:
        fire.click(screen.get_by_role("button"))
        fire.click(screen.get_by_role("button"))
        assert screen.get_by_role("button").text_content == "clicked 2 / 2"
        _edit(hotapp / "app.py", 'f"clicked {n}"', 'f"pressed {n}"')
        assert _hmr.apply(["hotapp.app"]) is True
        flush()
        # The module's components ran again: their local state starts over,
        # and state in a module that didn't change is kept.
        assert screen.get_by_role("button").text_content == "pressed 2 / 0"
        assert screen.get_by_text("Hello") and screen.get_by_text("footer")
        # Handlers in the remounted component work.
        fire.click(screen.get_by_role("button"))
        assert screen.get_by_role("button").text_content == "pressed 3 / 1"


def test_a_component_keeps_its_identity_for_modules_that_imported_it(wyb, hotapp: Path):
    app = importlib.import_module("hotapp.app")
    card = importlib.import_module("hotapp.card")
    original = card.Card
    with render(app.App()) as screen:
        _edit(hotapp / "card.py", "<h2>{title}</h2>", "<h3>{title}!</h3>")
        assert _hmr.apply(["hotapp.card"]) is True
        flush()
        assert card.Card is original and app.Card is original
        assert "<h3>Hello!</h3>" in screen.html()
        assert screen.get_by_role("button")


def test_a_module_that_renders_on_import_falls_back_to_a_reload(wyb, hotapp: Path, capsys):
    app = importlib.import_module("hotapp.app")
    with render(app.App(), strict=False):
        _edit(hotapp / "app.py", "def label(n):", "from wybthon import render\nrender(App(), 1)\n\n\ndef label(n):")
        assert _hmr.apply(["hotapp.app"]) is False
    assert "Hot update failed, reloading" in capsys.readouterr().err


def test_a_change_that_fails_falls_back_to_a_reload(wyb, hotapp: Path):
    app = importlib.import_module("hotapp.app")
    with render(app.App(), strict=False):
        _edit(hotapp / "app.py", "def label(n):", "def label(n:")
        assert _hmr.apply(["hotapp.app"]) is False


def test_modules_that_were_never_imported_need_nothing(wyb):
    assert _hmr.apply(["hotapp.never_imported"]) is True


def test_tracking_is_off_unless_wyb_dev_enables_it():
    assert reconciler._hot_track is None or reconciler._hot_track is _hmr._track


def test_the_dev_server_replaces_only_edited_application_modules(tmp_path: Path):
    project = tmp_path
    app = project / "app"
    (app / "pages").mkdir(parents=True)
    main, page, init = app / "main.py", app / "pages" / "home.py", app / "pages" / "__init__.py"
    for path in (main, page, init):
        path.write_text("x = 1\n")
    index = project / "index.html"
    index.write_text("<html></html>")
    before = {main: 1, page: 1, init: 1, index: 1}
    update = _hot_update(project, app, before, {**before, main: 2, init: 2})
    assert update is not None
    files, modules = update
    assert modules == ["app.main", "app.pages"]
    assert files == [
        {"path": "app/main.py", "source": "x = 1\n"},
        {"path": "app/pages/__init__.py", "source": "x = 1\n"},
    ]
    # Markup, new files, and removed files reload the page.
    assert _hot_update(project, app, before, {**before, index: 2}) is None
    assert _hot_update(project, app, before, {**before, app / "new.py": 1}) is None
    assert _hot_update(project, app, before, {main: 1, page: 1, index: 1}) is None
    assert _hot_update(project, app, before, dict(before)) is None


def test_an_edited_module_that_was_never_imported_loads_its_new_code(wyb, hotapp: Path):
    import py_compile

    # `wyb build` ships unchecked-hash bytecode, which imports use as is.
    late = hotapp / "late.py"
    late.write_text("VALUE = 'old'\n")
    py_compile.compile(str(late), invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
    late.write_text("VALUE = 'new'\n")
    assert _hmr.apply(["hotapp.late"], [str(late)]) is True
    importlib.invalidate_caches()
    assert importlib.import_module("hotapp.late").VALUE == "new"


def test_a_change_to_a_chunk_module_reloads_the_page(tmp_path: Path):
    # The rebuild gives the chunk a new archive, which the page's manifest doesn't name.
    app = tmp_path / "app"
    (app / "charts").mkdir(parents=True)
    main, chart = app / "main.py", app / "charts" / "bar.py"
    for path in (main, chart):
        path.write_text("x = 1\n")
    before = {main: 1, chart: 1}
    chunks = {"charts": ["app/charts/**"]}
    assert _hot_update(tmp_path, app, before, {main: 1, chart: 2}, chunks) is None
    update = _hot_update(tmp_path, app, before, {main: 2, chart: 1}, chunks)
    assert update is not None and update[1] == ["app.main"]
