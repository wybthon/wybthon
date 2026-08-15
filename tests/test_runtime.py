"""Tests for isolated runtimes and owned mount handles."""

from conftest import StubNode, collect_texts

from wybthon.vnode import h


def test_same_vnode_mounts_independently_in_two_containers(wyb, root_element):
    from wybthon.runtime import create_runtime

    runtime = create_runtime()
    other = wyb["dom"].Element(node=StubNode(tag="div"))
    shared = h("section", {}, h("p", {}, "shared"))

    first = runtime.render(shared, root_element)
    second = runtime.render(shared, other)

    assert "shared" in collect_texts(root_element.element)
    assert "shared" in collect_texts(other.element)
    assert first._mounted is not second._mounted
    assert runtime.stats()["mounts"] == 2

    first.dispose()
    assert "shared" not in collect_texts(root_element.element)
    assert "shared" in collect_texts(other.element)
    assert runtime.stats()["mounts"] == 1


def test_rendering_same_container_updates_existing_handle(wyb, root_element):
    from wybthon.runtime import create_runtime

    runtime = create_runtime()
    handle = runtime.render(h("p", {}, "one"), root_element)
    updated = runtime.render(h("p", {}, "two"), root_element)

    assert updated is handle
    assert "two" in collect_texts(root_element.element)
    assert runtime.stats()["mounts"] == 1

    runtime.dispose()
    assert handle.disposed is True
    assert runtime.stats() == {"mounts": 0, "mounted_nodes": 0, "owners": 0, "tasks": 0}


def test_effects_and_mount_callbacks_observe_committed_dom(wyb, root_element):
    reactivity = wyb["reactivity"]
    Ref = wyb["dom"].Ref
    observations = []

    def App(props):
        ref = Ref()
        reactivity.create_effect(lambda: observations.append(("effect", ref.current is not None)))
        reactivity.on_mount(lambda: observations.append(("mount", ref.current is not None)))
        return h("input", {"ref": ref})

    wyb["reconciler"].render(h(App, {}), root_element)

    assert observations == [("mount", True), ("effect", True)]


def test_mount_disposal_cancels_owned_resource_tasks(wyb, root_element):
    import asyncio

    async def run():
        reactivity = wyb["reactivity"]
        cancelled = asyncio.Event()

        async def fetcher():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        def App(props):
            reactivity.create_resource(fetcher)
            return h("p", {}, "waiting")

        handle = wyb["reconciler"].render(h(App, {}), root_element)
        await asyncio.sleep(0)
        assert handle._runtime.stats()["tasks"] == 1

        handle.dispose()
        await asyncio.sleep(0)
        assert cancelled.is_set()
        assert handle._runtime.stats()["tasks"] == 0

    asyncio.run(run())
