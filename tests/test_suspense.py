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


@pytest.mark.skipif(not HAS_JS, reason="requires Pyodide/js module")
def test_error_boundary_reset_and_on_error(monkeypatch):
    wyb = importlib.import_module("wybthon")
    ErrorBoundary = getattr(wyb, "ErrorBoundary")
    h = getattr(wyb, "h")
    render = getattr(wyb, "render")
    Element = getattr(wyb, "Element")

    # Component that always throws
    def Boom(_props):
        raise RuntimeError("boom")

    observed = {"error": None, "reset": None}

    # Fallback captures error and exposes a button to reset
    def fallback(err, reset):
        observed["error"] = str(err)
        observed["reset"] = reset
        return h("div", {}, "Oops")

    # Track on_error callback invocation
    called = {"err": None}

    def on_error(e):
        called["err"] = str(e)

    container = Element("div")
    vnode = h(ErrorBoundary, {"fallback": fallback, "on_error": on_error}, Boom({}))
    render(vnode, container)
    # Allow microtasks
    import time

    time.sleep(0.01)

    html = container.element.innerHTML
    assert "Oops" in html
    assert observed["error"] is not None
    assert called["err"] is not None

    # Imperative reset should clear error state (render may still error next tick)
    reset_fn = observed["reset"]
    assert callable(reset_fn)
    reset_fn()
    time.sleep(0.005)
    # Since Boom always throws, it should re-enter fallback again; but reset call shouldn't error
    html2 = container.element.innerHTML
    assert "Oops" in html2
