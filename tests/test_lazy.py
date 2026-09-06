import asyncio
import sys
import types

import pytest
from conftest import collect_texts

from wybthon.component import component
from wybthon.error_boundary import Errored
from wybthon.html import div, h2, p, section, span
from wybthon.lazy import LazyComponent, lazy
from wybthon.loading import Loading
from wybthon.reactivity import Prop, create_signal, flush, prop


def texts(node):
    return [t for t in collect_texts(node) if t]


@component
def Page(title: Prop[str] = prop("T")):
    return h2(title)


@pytest.fixture()
def fake_module():
    name = "_wyb_test_lazy_page_mod"
    mod = types.ModuleType(name)
    mod.Page = Page
    mod.Other = lambda _props: span("other")
    sys.modules[name] = mod
    try:
        yield name
    finally:
        sys.modules.pop(name, None)


def test_sync_loader_returning_component(wyb, root_element):
    calls = []

    def loader():
        calls.append(1)
        return Page

    Lazy = lazy(loader)
    assert isinstance(Lazy, LazyComponent)
    root = wyb["reconciler"].render(div(Lazy(title="hello")), root_element)
    flush()
    assert texts(root_element.element) == ["hello"]
    assert calls == [1]
    root.dispose()

    # The resolved component is cached: mounting again doesn't rerun the loader.
    root = wyb["reconciler"].render(div(Lazy(title="again")), root_element)
    flush()
    assert texts(root_element.element) == ["again"]
    assert calls == [1]
    root.dispose()


def test_loader_returning_module_path_string(wyb, root_element, fake_module):
    Lazy = lazy(lambda: fake_module)
    root = wyb["reconciler"].render(div(Lazy(title="from-path")), root_element)
    flush()
    assert texts(root_element.element) == ["from-path"]
    root.dispose()


def test_loader_returning_module_and_attr_tuple(wyb, root_element, fake_module):
    Lazy = lazy(lambda: (fake_module, "Other"))
    root = wyb["reconciler"].render(div(Lazy()), root_element)
    flush()
    assert texts(root_element.element) == ["other"]
    root.dispose()


def test_loader_returning_module_object(wyb, root_element, fake_module):
    Lazy = lazy(lambda: sys.modules[fake_module])
    root = wyb["reconciler"].render(div(Lazy(title="mod")), root_element)
    flush()
    assert texts(root_element.element) == ["mod"]
    root.dispose()


def test_async_loader_shows_loading_fallback_then_content(wyb, root_element):
    container = root_element.element

    async def main():
        gate = asyncio.Event()

        async def loader():
            await gate.wait()
            return Page

        Lazy = lazy(loader)
        root = wyb["reconciler"].render(div(Loading(lambda: Lazy(title="lazy!"), fallback=p("..."))), root_element)
        await asyncio.sleep(0)
        flush()
        assert texts(container) == ["..."]
        gate.set()
        await asyncio.sleep(0.01)
        flush()
        assert texts(container) == ["lazy!"]
        root.dispose()

    asyncio.run(main())


def test_preload_starts_loading_before_mount(wyb, root_element):
    calls = []

    def loader():
        calls.append(1)
        return Page

    Lazy = lazy(loader)
    assert calls == []
    Lazy.preload()
    assert calls == [1]
    Lazy.preload()
    assert calls == [1]
    root = wyb["reconciler"].render(div(Lazy(title="pre")), root_element)
    flush()
    assert texts(root_element.element) == ["pre"]
    assert calls == [1]
    root.dispose()


def test_failing_loader_routes_to_errored_fallback(wyb, root_element):
    container = root_element.element

    async def main():
        Bad = lazy(lambda: ("__wyb_no_such_module__", "X"))
        seen = []
        root = wyb["reconciler"].render(
            div(Errored(lambda: Bad(), fallback=lambda e: (seen.append(e), p("failed"))[1])),
            root_element,
        )
        await asyncio.sleep(0.01)
        flush()
        assert texts(container) == ["failed"]
        assert isinstance(seen[0], ModuleNotFoundError)
        root.dispose()

    asyncio.run(main())


def test_loader_raising_synchronously_routes_to_errored(wyb, root_element):
    def loader():
        raise RuntimeError("boom")

    Bad = lazy(loader)
    root = wyb["reconciler"].render(
        div(Errored(lambda: Bad(), fallback=lambda e: p("err: ", str(e)))),
        root_element,
    )
    flush()
    assert texts(root_element.element) == ["err: ", "boom"]
    root.dispose()


def test_props_and_children_pass_through_to_loaded_component(wyb, root_element):
    @component
    def Card(title: Prop[str] = prop(""), children=None, **rest):
        return section(h2(title), div(children), **rest)

    Lazy = lazy(lambda: Card)
    label, set_label = create_signal("one")
    root = wyb["reconciler"].render(Lazy(p("kid-a"), p("kid-b"), title=label, class_="card"), root_element)
    flush()
    container = root_element.element
    assert texts(container) == ["one", "kid-a", "kid-b"]
    section_node = [n for n in container.childNodes if n.tag][0]
    assert section_node.tag == "section"
    assert section_node.attributes.get("class") == "card"
    set_label("two")
    flush()
    assert texts(container) == ["two", "kid-a", "kid-b"]
    root.dispose()


def test_failed_lazy_load_can_retry_and_recover(wyb, root_element):
    async def main():
        attempts = []

        async def load():
            attempts.append(1)
            await asyncio.sleep(0)
            if len(attempts) == 1:
                raise ValueError("temporary")
            return Page

        panel = lazy(load)
        root = wyb["reconciler"].render(
            Errored(lambda: Loading(lambda: panel(), fallback="loading"), fallback=lambda error: p(str(error))),
            root_element,
        )
        for _ in range(5):
            await asyncio.sleep(0)
            flush()
        assert texts(root_element.element) == ["temporary"]
        panel.retry()
        for _ in range(5):
            await asyncio.sleep(0)
            flush()
        assert "temporary" not in texts(root_element.element)
        assert len(attempts) == 2
        root.dispose()

    asyncio.run(main())
