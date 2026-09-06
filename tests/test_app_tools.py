"""Production build, form workflows, and virtualization contracts."""

import asyncio
import json
import zipfile
from types import SimpleNamespace

import pytest

from wybthon import bind_multiselect, bind_number, create_signal, create_virtualizer, flush, form_state
from wybthon.build import build_app, init_app
from wybthon.router_core import RouteSpec, resolve


def test_build_is_deterministic_and_chunks_are_separate(tmp_path):
    app = tmp_path / "project"
    init_app(app)
    (app / "app" / "charts").mkdir()
    (app / "app" / "charts" / "__init__.py").write_text("VALUE = 1\n")
    config = app / "wybthon.toml"
    config.write_text(config.read_text().replace('# charts = ["app/charts/**"]', 'charts = ["app/charts/**"]'))
    first = build_app(app, base="/demo/")
    files = {path.relative_to(app / "dist"): path.read_bytes() for path in (app / "dist").rglob("*") if path.is_file()}
    second = build_app(app, base="/demo/")
    assert first == second
    assert all((app / "dist" / path).read_bytes() == data for path, data in files.items())
    assert first["pyodide_url"].endswith("/v314.0.6/full/")
    with zipfile.ZipFile(app / "dist" / first["application"]) as archive:
        assert "app/main.py" in archive.namelist()
        assert "app/charts/__init__.py" not in archive.namelist()
    with zipfile.ZipFile(app / "dist" / first["chunks"]["charts"]) as archive:
        assert "app/charts/__init__.py" in archive.namelist()
    assert 'src="/demo/assets/bootstrap.' in (app / "dist" / "index.html").read_text()
    assert json.loads((app / "dist" / "manifest.json").read_text()) == first


def test_init_and_build_preserve_existing_files(tmp_path):
    (tmp_path / "important.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        init_app(tmp_path)
    app = tmp_path / "app-project"
    init_app(app)
    with pytest.raises(ValueError):
        build_app(app, output=tmp_path)
    assert (tmp_path / "important.txt").read_text() == "keep"


def test_form_dirty_reset_and_numeric_conversion(wyb):
    state = form_state({"amount": 1.0})
    field = state["amount"]
    binding = bind_number(field)
    binding["on_input"](SimpleNamespace(target=SimpleNamespace(value="2.5")))
    flush()
    assert state.data() == {"amount": 2.5}
    assert state.dirty()
    binding["on_input"](SimpleNamespace(target=SimpleNamespace(value="bad")))
    flush()
    assert field.error() is not None
    assert field.validate([]) is not None
    state.reset()
    flush()
    assert state.data() == {"amount": 1.0}
    assert not state.dirty()
    assert not field.touched()
    assert field.error() is None


def test_async_validation_ignores_stale_results(wyb):
    async def main():
        state = form_state({"name": "old"})
        field = state["name"]
        gate = asyncio.Event()

        async def check(value):
            await gate.wait()
            return "taken" if value == "old" else None

        pending = asyncio.create_task(field.validate_async([check]))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        flush()
        assert field.validating()
        field.set_value("new")
        gate.set()
        await pending
        await field.validate_async([check])
        flush()
        assert field.value() == "new" and field.error() is None
        assert not field.validating()

    asyncio.run(main())


def test_form_submission_validates_and_exposes_pending(wyb):
    async def main():
        state = form_state({"name": "Ada"})
        gate = asyncio.Event()
        values = []

        async def save(data):
            values.append(data)
            await gate.wait()
            return 42

        task = asyncio.create_task(state.submit(save))
        for _ in range(8):
            await asyncio.sleep(0)
        flush()
        assert state.submitting()
        assert values == [{"name": "Ada"}]
        gate.set()
        assert await task == 42
        flush()
        assert not state.submitting()

    asyncio.run(main())


def test_multiselect_reads_all_selected_values(wyb):
    field = form_state({"tags": []})["tags"]
    binding = bind_multiselect(field)
    binding["on_change"](SimpleNamespace(target=SimpleNamespace(selected_values=["a", "c"])))
    flush()
    assert field.value() == ["a", "c"]
    assert binding["multiple"] is True


def test_virtual_range_is_bounded_and_clamps_after_shrink(wyb):
    count, set_count = create_signal(10000)
    offset, set_offset = create_signal(2000)
    view = create_virtualizer(count, item_size=20, viewport_size=200, scroll_offset=offset, overscan=2)
    assert (view.start(), view.stop(), view.offset(), view.total()) == (98, 112, 1960, 200000)
    set_count(5)
    flush()
    assert (view.start(), view.stop(), view.total()) == (0, 5, 100)
    set_offset(-50)
    flush()
    assert view.start() == 0


def test_route_specificity_and_base_boundaries():
    routes = [RouteSpec("/users/:really_long_parameter"), RouteSpec("/users/new"), RouteSpec("/users/*")]
    assert resolve(routes, "/users/new")[0] is routes[1]
    assert resolve(routes, "/users/other")[0] is routes[0]
    assert resolve(routes, "/application/users/new", "/app") is None
    assert resolve(routes, "/app/users/new/", "/app")[0] is routes[1]


def test_build_validation_failure_preserves_previous_output(tmp_path):
    init_app(tmp_path)
    build_app(tmp_path)
    previous = (tmp_path / "dist" / "index.html").read_bytes()
    (tmp_path / "index.html").write_text("Invalid template")
    with pytest.raises(ValueError, match="marker"):
        build_app(tmp_path)
    assert (tmp_path / "dist" / "index.html").read_bytes() == previous


def test_cooperative_work_yields_and_cancels(wyb):
    from wybthon import map_cooperative

    async def main():
        completed = []
        task = asyncio.create_task(
            map_cooperative(range(100000), lambda value: completed.append(value), budget_ms=0.001)
        )
        await asyncio.sleep(0)
        assert 0 < len(completed) < 100000
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await map_cooperative([1, 2, 3], lambda value: value * 2) == [2, 4, 6]

    asyncio.run(main())


def test_testing_scope_disposes_computations(wyb):
    from wybthon import create_effect
    from wybthon.testing import reactive_scope

    value, write = create_signal(1)
    seen = []
    with reactive_scope():
        create_effect(value, seen.append)
        flush()
    write(2)
    flush()
    assert seen == [1]
    assert not value._observers


def test_render_test_and_graph_inspection_release_resources(wyb):
    from wybthon import p
    from wybthon.diagnostics import inspect_graph, runtime_stats
    from wybthon.testing import render_test

    value, _ = create_signal(1)
    before = runtime_stats()
    with render_test(p(value)) as root:
        graph = inspect_graph(root._owner)
        assert any(edge["kind"] == "dependency" for edge in graph["edges"])
        json.dumps(graph)
        assert runtime_stats()["nodes"] > before["nodes"]
    assert runtime_stats()["nodes"] == before["nodes"]
    assert not value._observers


def test_build_rejects_invalid_python_before_replacing_output(tmp_path):
    init_app(tmp_path)
    build_app(tmp_path)
    previous = (tmp_path / "dist" / "manifest.json").read_bytes()
    (tmp_path / "app" / "main.py").write_text("def broken(:\n")
    with pytest.raises(ValueError, match="Invalid Python source"):
        build_app(tmp_path)
    assert (tmp_path / "dist" / "manifest.json").read_bytes() == previous
