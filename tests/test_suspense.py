import importlib
import time

import pytest

try:
    importlib.import_module("js")
    HAS_JS = True
except Exception:
    HAS_JS = False


@pytest.mark.skipif(not HAS_JS, reason="requires Pyodide/js module")
def test_suspense_keeps_previous_on_reload(monkeypatch):
    wyb = importlib.import_module("wybthon")
    Suspense = getattr(wyb, "Suspense")
    h = getattr(wyb, "h")
    render = getattr(wyb, "render")
    Element = getattr(wyb, "Element")
    use_resource = getattr(wyb, "use_resource")

    # Resource that completes quickly
    async def fetcher(signal=None):
        return "A"

    res = use_resource(fetcher)

    # Mount container
    container = Element("div")

    def Content(_props):
        return h("span", {}, res.data.get() or "")

    vnode = h(
        Suspense,
        {"resource": res, "fallback": h("span", {}, "Loading"), "keep_previous": True},
        Content({}),
    )
    render(vnode, container)
    # Allow microtasks
    time.sleep(0.05)

    # After first load, content should be present and not fallback
    html = container.element.innerHTML
    assert "Loading" not in html

    # Trigger reload and ensure previous content remains
    res.reload()
    time.sleep(0.005)
    html2 = container.element.innerHTML
    assert "Loading" not in html2
