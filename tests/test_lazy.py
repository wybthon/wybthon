import asyncio
import sys
import types

import pytest
from conftest import collect_texts

from wybthon import html
from wybthon.component import component
from wybthon.error_boundary import Errored
from wybthon.lazy import LazyComponent, LazyModule, lazy, lazy_module
from wybthon.loading import Loading
from wybthon.reactivity import ParentProps, Props, create_signal, flush, prop


def texts(node):
    return [t for t in collect_texts(node) if t and t.strip()]


class PageProps(Props):
    title: str = prop(default="T")


@component
def Page(props: PageProps):
    return html(t"<h2>{props.title}</h2>")


@component
def Other():
    return html(t"<span>other</span>")


@pytest.fixture()
def fake_module():
    name = "_wyb_test_lazy_page_mod"
    mod = types.ModuleType(name)
    mod.Page = Page
    mod.Other = Other
    mod.answer = 42
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
    root = wyb["reconciler"].render(html(t"<div>{Lazy(title='hello')}</div>"), root_element)
    flush()
    assert texts(root_element.element) == ["hello"]
    assert calls == [1]
    root.dispose()

    # The resolved component is cached: mounting again doesn't rerun the loader.
    root = wyb["reconciler"].render(html(t"<div>{Lazy(title='again')}</div>"), root_element)
    flush()
    assert texts(root_element.element) == ["again"]
    assert calls == [1]
    root.dispose()


def test_loader_returning_module_path_string(wyb, root_element, fake_module):
    Lazy = lazy(lambda: fake_module)
    root = wyb["reconciler"].render(html(t"<div>{Lazy(title='from-path')}</div>"), root_element)
    flush()
    assert texts(root_element.element) == ["from-path"]
    root.dispose()


def test_loader_returning_module_and_attr_tuple(wyb, root_element, fake_module):
    Lazy = lazy(lambda: (fake_module, "Other"))
    root = wyb["reconciler"].render(html(t"<div><{Lazy} /></div>"), root_element)
    flush()
    assert texts(root_element.element) == ["other"]
    root.dispose()


def test_loader_returning_module_object(wyb, root_element, fake_module):
    Lazy = lazy(lambda: sys.modules[fake_module])
    root = wyb["reconciler"].render(html(t"<div>{Lazy(title='mod')}</div>"), root_element)
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
        view = html(t"<div>{Loading(lambda: Lazy(title='lazy!'), fallback=html(t'<p>...</p>'))}</div>")
        root = wyb["reconciler"].render(view, root_element)
        await asyncio.sleep(0)
        flush()
        assert texts(container) == ["..."]
        gate.set()
        await asyncio.sleep(0.01)
        flush()
        assert texts(container) == ["lazy!"]
        root.dispose()

    asyncio.run(main())


def test_lazy_component_call_in_a_template_receives_getters(wyb, root_element):
    # A lazy component is a component for the compiler: `title={label()}`
    # arrives as a getter and the loaded component's text follows it.
    label, set_label = create_signal("one")
    Lazy = lazy(lambda: Page)
    root = wyb["reconciler"].render(html(t"<div>{Lazy(title=label().upper())}</div>"), root_element)
    flush()
    assert texts(root_element.element) == ["ONE"]
    set_label("two")
    flush()
    assert texts(root_element.element) == ["TWO"]
    root.dispose()


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
    root = wyb["reconciler"].render(html(t"<div>{Lazy(title='pre')}</div>"), root_element)
    flush()
    assert texts(root_element.element) == ["pre"]
    assert calls == [1]
    root.dispose()


def test_failing_loader_routes_to_errored_fallback(wyb, root_element):
    container = root_element.element

    async def main():
        Bad = lazy(lambda: ("__wyb_no_such_module__", "X"))
        seen = []

        def fallback(e):
            seen.append(e())
            return html(t"<p>failed</p>")

        root = wyb["reconciler"].render(
            html(t"<div>{Errored(lambda: Bad(), fallback=fallback)}</div>"),
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
    view = html(t"<div>{Errored(lambda: Bad(), fallback=lambda e: html(t'<p>err: {str(e())}</p>'))}</div>")
    root = wyb["reconciler"].render(view, root_element)
    flush()
    assert texts(root_element.element) == ["err: ", "boom"]
    root.dispose()


def test_props_and_children_pass_through_to_loaded_component(wyb, root_element):
    class CardProps(ParentProps):
        title: str = prop(default="")
        class_: str | None = prop(default=None)

    @component
    def Card(props: CardProps):
        return html(t"<section class={props.class_}><h2>{props.title}</h2><div>{props.children}</div></section>")

    Lazy = lazy(lambda: Card)
    label, set_label = create_signal("one")
    view = html(t'<{Lazy} title={label()} class="card"><p>kid-a</p><p>kid-b</p></{Lazy}>')
    root = wyb["reconciler"].render(view, root_element)
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
            Errored(
                lambda: Loading(lambda: panel(), fallback="loading"),
                fallback=lambda error: html(t"<p>{str(error())}</p>"),
            ),
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


# ---------------------------------------------------------------------------
# lazy_module
# ---------------------------------------------------------------------------


def test_lazy_module_with_a_sync_loader_and_module_path(fake_module):
    calls: list[int] = []

    def loader() -> str:
        calls.append(1)
        return fake_module

    async def main() -> None:
        mod = lazy_module(loader)
        assert isinstance(mod, LazyModule)
        # Nothing runs until the module is asked for.
        assert calls == []
        assert mod.peek() is None
        loaded = await mod()
        assert loaded is sys.modules[fake_module]
        assert loaded.answer == 42
        assert mod.peek() is loaded
        # Cached: the loader runs once.
        assert await mod() is loaded
        assert calls == [1]

    asyncio.run(main())


def test_lazy_module_with_an_async_loader(fake_module):
    async def main() -> None:
        gate = asyncio.Event()

        async def loader():
            await gate.wait()
            return sys.modules[fake_module]

        mod = lazy_module(loader)
        pending = mod()
        await asyncio.sleep(0)
        # Still loading.
        assert mod.peek() is None
        assert not pending.done()
        gate.set()
        loaded = await pending
        assert loaded is sys.modules[fake_module]
        assert mod.peek() is loaded

    asyncio.run(main())


def test_lazy_module_preload_returns_the_same_awaitable(fake_module):
    calls: list[int] = []

    async def loader():
        calls.append(1)
        return fake_module

    async def main() -> None:
        mod = lazy_module(loader)
        first = mod.preload()
        assert mod.preload() is first
        assert mod() is first
        assert mod.peek() is None
        loaded = await first
        assert loaded is sys.modules[fake_module]
        assert mod.peek() is loaded
        assert calls == [1]

    asyncio.run(main())


def test_lazy_module_loader_error_propagates(fake_module):
    async def main() -> None:
        mod = lazy_module(lambda: "__wyb_no_such_module__")
        with pytest.raises(ModuleNotFoundError):
            await mod()
        assert mod.peek() is None

    asyncio.run(main())
