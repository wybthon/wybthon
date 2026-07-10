#!/usr/bin/env python3
"""Wybthon benchmark runner — js-framework-benchmark compatible operations.

Measures the idiomatic fine-grained rendering path (signals + ``For`` +
``create_selector``) for all 9 standard operations from
krausest/js-framework-benchmark using a lightweight DOM stub. This
isolates the Python-side framework cost from browser/Pyodide overhead.

The app under test is built the way a real Wybthon app should be: the
table mounts **once**; every operation is a signal write. Rows are cached
per item, row labels are per-row signals, and selection flows through a
selector, so each operation touches only the DOM it must.

The stub DOM implements ``<template>`` + ``innerHTML`` parsing (via
``html.parser``) so the template-based mount fast path is exercised the
same way it is in a real browser.

Usage:
    python benchmarks/bench_runner.py                    # table output
    python benchmarks/bench_runner.py --json             # JSON output
    python benchmarks/bench_runner.py --memory           # include memory
    python benchmarks/bench_runner.py --warmup 3         # override warmup
    python benchmarks/bench_runner.py --iterations 5     # measured iterations

Reference: https://github.com/krausest/js-framework-benchmark
"""

import argparse
import importlib
import json as json_module
import random
import sys
import time
import tracemalloc
from html.parser import HTMLParser
from math import sqrt
from statistics import mean, stdev
from types import ModuleType

# ---------------------------------------------------------------------------
# Standard benchmark data (matching js-framework-benchmark exactly)
# ---------------------------------------------------------------------------

ADJECTIVES = [
    "pretty",
    "large",
    "big",
    "small",
    "tall",
    "short",
    "long",
    "handsome",
    "plain",
    "quaint",
    "clean",
    "elegant",
    "easy",
    "angry",
    "crazy",
    "helpful",
    "mushy",
    "odd",
    "unsightly",
    "adorable",
    "important",
    "inexpensive",
    "cheap",
    "expensive",
    "fancy",
]
COLOURS = [
    "red",
    "yellow",
    "blue",
    "green",
    "pink",
    "brown",
    "purple",
    "brown",
    "white",
    "black",
    "orange",
]
NOUNS = [
    "table",
    "chair",
    "house",
    "bbq",
    "desk",
    "car",
    "pony",
    "cookie",
    "sandwich",
    "burger",
    "pizza",
    "mouse",
    "keyboard",
]

# ---------------------------------------------------------------------------
# DOM stub — lightweight stand-in for browser DOM nodes
# ---------------------------------------------------------------------------


class _ClassList:
    __slots__ = ("_set",)

    def __init__(self):
        self._set = set()

    def add(self, name):
        self._set.add(name)

    def remove(self, name):
        self._set.discard(name)

    def contains(self, name):
        return name in self._set

    def toggle(self, name, force=None):
        if force is None:
            self._set.symmetric_difference_update({name})
        elif force:
            self._set.add(name)
        else:
            self._set.discard(name)


class _Style:
    __slots__ = ("_props",)

    def __init__(self):
        self._props = {}

    def setProperty(self, name, value):
        self._props[name] = str(value)

    def removeProperty(self, name):
        self._props.pop(name, None)


class _Node:
    __slots__ = (
        "tag",
        "nodeValue",
        "parentNode",
        "childNodes",
        "attributes",
        "classList",
        "style",
        "textContent",
        "value",
        "checked",
        "_wyb_id",
    )

    def __init__(self, tag=None, text=None):
        self.tag = tag
        self.nodeValue = text
        self.parentNode = None
        self.childNodes = []
        self.attributes = {}
        self.classList = _ClassList()
        self.style = _Style()
        self.textContent = None
        self.value = ""
        self.checked = False

    @property
    def nextSibling(self):
        p = self.parentNode
        if p is None:
            return None
        children = p.childNodes
        try:
            idx = children.index(self)
        except ValueError:
            return None
        return children[idx + 1] if idx + 1 < len(children) else None

    @property
    def firstChild(self):
        return self.childNodes[0] if self.childNodes else None

    def appendChild(self, node):
        if getattr(node, "parentNode", None) is not None:
            try:
                node.parentNode.childNodes.remove(node)
            except (ValueError, AttributeError):
                pass
        node.parentNode = self
        self.childNodes.append(node)
        return node

    def insertBefore(self, node, anchor):
        if getattr(node, "parentNode", None) is not None:
            try:
                node.parentNode.childNodes.remove(node)
            except (ValueError, AttributeError):
                pass
        node.parentNode = self
        if anchor is None:
            self.childNodes.append(node)
            return node
        try:
            idx = self.childNodes.index(anchor)
        except ValueError:
            self.childNodes.append(node)
            return node
        self.childNodes.insert(idx, node)
        return node

    def removeChild(self, node):
        try:
            self.childNodes.remove(node)
            node.parentNode = None
        except ValueError:
            pass
        return node

    def setAttribute(self, name, value):
        self.attributes[name] = str(value)

    def getAttribute(self, name):
        return self.attributes.get(name)

    def removeAttribute(self, name):
        self.attributes.pop(name, None)


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _StubHTMLParser(HTMLParser):
    """Minimal HTML parser building _Node trees (backs template.innerHTML)."""

    def __init__(self, root):
        super().__init__(convert_charrefs=True)
        self._stack = [root]

    def _add_element(self, tag, attrs):
        node = _Node(tag=tag)
        for name, value in attrs:
            value = "" if value is None else value
            node.setAttribute(name, value)
            if name == "class":
                for cls in value.split():
                    node.classList.add(cls)
            elif name == "style":
                for decl in value.split(";"):
                    if ":" in decl:
                        k, v = decl.split(":", 1)
                        node.style.setProperty(k.strip(), v.strip())
        self._stack[-1].appendChild(node)
        return node

    def handle_starttag(self, tag, attrs):
        node = self._add_element(tag, attrs)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._add_element(tag, attrs)

    def handle_endtag(self, tag):
        if len(self._stack) > 1:
            self._stack.pop()

    def handle_data(self, data):
        if data:
            self._stack[-1].appendChild(_Node(text=data))

    def handle_comment(self, data):
        self._stack[-1].appendChild(_Node(text=data))


class _Template(_Node):
    """Stub for `<template>`: parses innerHTML into a content fragment."""

    __slots__ = ("content",)

    def __init__(self):
        super().__init__(tag="template")
        self.content = _Node(tag="#fragment")

    @property
    def innerHTML(self):
        return ""

    @innerHTML.setter
    def innerHTML(self, html):
        self.content.childNodes = []
        if html:
            parser = _StubHTMLParser(self.content)
            parser.feed(html)
            parser.close()


class _Document:
    def __init__(self):
        self._listeners = {}

    def createElement(self, tag):
        if tag == "template":
            return _Template()
        return _Node(tag=tag)

    def createTextNode(self, text):
        return _Node(text=str(text))

    def createComment(self, text=""):
        return _Node(text=str(text))

    def addEventListener(self, event_type, proxy):
        self._listeners.setdefault(event_type, set()).add(proxy)

    def removeEventListener(self, event_type, proxy):
        s = self._listeners.get(event_type)
        if s is not None:
            s.discard(proxy)

    def querySelector(self, sel):
        return _Node(tag="div")

    def querySelectorAll(self, sel):
        return []


# ---------------------------------------------------------------------------
# Module stubs — allow importing Wybthon under CPython
# ---------------------------------------------------------------------------


def _install_stubs():
    js_mod = ModuleType("js")
    js_mod.document = _Document()
    js_mod.fetch = lambda url: None

    class _Location:
        def __init__(self):
            self.pathname = "/"
            self.search = ""

    class _History:
        def __init__(self, win):
            self._win = win

        def pushState(self, _a, _b, path):
            self._win.location.pathname = str(path)

        def replaceState(self, _a, _b, path):
            self._win.location.pathname = str(path)

    class _Window:
        def __init__(self):
            self._listeners = {}
            self.location = _Location()
            self.history = _History(self)

        def addEventListener(self, event_type, proxy):
            self._listeners.setdefault(event_type, set()).add(proxy)

    js_mod.window = _Window()
    try:
        from urllib.parse import unquote

        js_mod.decodeURIComponent = lambda s: unquote(s)
    except Exception:
        js_mod.decodeURIComponent = lambda s: s

    sys.modules["js"] = js_mod

    pyodide_mod = ModuleType("pyodide")
    ffi_mod = ModuleType("pyodide.ffi")
    ffi_mod.create_proxy = lambda fn: fn
    sys.modules["pyodide"] = pyodide_mod
    sys.modules["pyodide.ffi"] = ffi_mod
    setattr(pyodide_mod, "ffi", ffi_mod)


def _load_wybthon():
    import js

    modules = {}
    for name in (
        "wybthon._warnings",
        "wybthon.kernel",
        "wybthon.dom",
        "wybthon.vnode",
        "wybthon.events",
        "wybthon.props",
        "wybthon.reactivity",
        "wybthon.context",
        "wybthon.template",
        "wybthon.error_boundary",
        "wybthon.suspense",
        "wybthon.portal",
        "wybthon.reconciler",
        "wybthon.flow",
    ):
        mod = importlib.import_module(name)
        importlib.reload(mod)
        modules[name] = mod
    kernel = modules["wybthon.kernel"]
    kernel.set_backend(kernel.PythonBackend(js.document))
    return modules


# ---------------------------------------------------------------------------
# Benchmark app — idiomatic fine-grained Wybthon
# ---------------------------------------------------------------------------


class BenchState:
    """One instance of the benchmark app, mounted once.

    The DOM mounts a single time in ``__init__``; every benchmark
    operation afterwards is a signal write, exactly as a real Wybthon
    app would do it.
    """

    def __init__(self, mods, registry):
        self._registry = registry
        rx = mods["wybthon.reactivity"]
        h = mods["wybthon.vnode"].h
        For = mods["wybthon.flow"].For
        self._rx = rx
        self._h = h
        self.root = mods["wybthon.dom"].Element(node=_Node(tag="div"))
        self._next_id = 1

        self.data, self.set_data = rx.create_signal([])
        self.selected, self.set_selected = rx.create_signal(None)
        self._is_selected = rx.create_selector(self.selected)

        app = h(
            "table",
            {"class": "table table-hover table-striped test-data"},
            h("tbody", {"id": "tbody"}, For(each=self.data, children=self._row)),
        )
        mods["wybthon.reconciler"].render(app, self.root)

    def _row(self, item, idx):
        h = self._h
        d = item()
        iid = d["id"]
        return h(
            "tr",
            {"class": lambda: "danger" if self._is_selected(iid) else ""},
            h("td", {"class": "col-md-1"}, str(iid)),
            h("td", {"class": "col-md-4"}, h("a", {"on_click": lambda e: self.set_selected(iid)}, d["label"])),
            h(
                "td",
                {"class": "col-md-1"},
                h(
                    "a",
                    {"on_click": lambda e: self.remove(iid)},
                    h("span", {"class": "glyphicon glyphicon-remove", "aria-hidden": "true"}),
                ),
            ),
            h("td", {"class": "col-md-6"}),
        )

    def build_data(self, count):
        rx = self._rx
        result = []
        nid = self._next_id
        for _ in range(count):
            label = (
                f"{ADJECTIVES[random.randint(0, len(ADJECTIVES) - 1)]} "
                f"{COLOURS[random.randint(0, len(COLOURS) - 1)]} "
                f"{NOUNS[random.randint(0, len(NOUNS) - 1)]}"
            )
            label_get, label_set = rx.create_signal(label)
            result.append({"id": nid, "label": label_get, "set_label": label_set})
            nid += 1
        self._next_id = nid
        return result

    def remove(self, iid):
        self.set_data(lambda rows: [r for r in rows if r["id"] != iid])

    def cleanup(self):
        self._registry.pop(self.root.node_id, None)


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _setup_empty(state):
    pass


def _setup_1k(state):
    state.set_data(state.build_data(1000))


def _setup_10k(state):
    state.set_data(state.build_data(10000))


# ---------------------------------------------------------------------------
# Benchmark operations (matching js-framework-benchmark)
# ---------------------------------------------------------------------------


def op_create_rows(state):
    """Create 1,000 rows."""
    state.set_data(state.build_data(1000))


def op_replace_all(state):
    """Replace all 1,000 rows with new data."""
    state.set_data(state.build_data(1000))


def op_partial_update(state):
    """Update every 10th row's label signal."""
    rows = state.data()

    def update():
        for i in range(0, len(rows), 10):
            rows[i]["set_label"](lambda label: label + " !!!")

    state._rx.batch(update)


def op_select_row(state):
    """Highlight a selected row (selector: touches two rows at most)."""
    rows = state.data()
    if rows:
        state.set_selected(rows[len(rows) // 2]["id"])


def op_swap_rows(state):
    """Swap rows at indices 1 and 998 (cached rows: two DOM moves)."""
    rows = list(state.data())
    if len(rows) > 998:
        rows[1], rows[998] = rows[998], rows[1]
    state.set_data(rows)


def op_remove_row(state):
    """Remove one row from the middle."""
    rows = state.data()
    if rows:
        target_id = rows[len(rows) // 2]["id"]
        state.set_data([d for d in rows if d["id"] != target_id])


def op_create_many(state):
    """Create 10,000 rows."""
    state.set_data(state.build_data(10000))


def op_append_rows(state):
    """Append 1,000 rows to the existing table."""
    state.set_data(state.data() + state.build_data(1000))


def op_clear_rows(state):
    """Clear all rows."""

    def update():
        state.set_data([])
        state.set_selected(None)

    state._rx.batch(update)


# ---------------------------------------------------------------------------
# Reactive-hole microbenchmarks
#
# Both benchmarks update a single text node inside a tree of 1,000 spans.
# The "hole" version uses a reactive hole — one effect, one DOM mutation.
# The "rerender" version re-renders the whole tree from scratch and lets
# the reconciler diff its way to the same single update.
# ---------------------------------------------------------------------------


_HOLE_TREE_SIZE = 1000


class _HoleState:
    """State for the hole-vs-rerender microbenchmarks."""

    def __init__(self, mods, registry):
        self._h = mods["wybthon.vnode"].h
        self._render_fn = mods["wybthon.reconciler"].render
        self._registry = registry
        self._reactivity = mods["wybthon.reactivity"]
        self.root = mods["wybthon.dom"].Element(node=_Node(tag="div"))

    def cleanup(self):
        self._registry.pop(self.root.node_id, None)


def _setup_hole(state):
    """Mount a tree of N spans where the first one is a reactive hole."""
    n = _HOLE_TREE_SIZE
    getter, setter = state._reactivity.create_signal(0)
    state._setter = setter
    state._counter = 0

    spans = [state._h("span", {}, getter)]
    spans.extend(state._h("span", {}, f"static-{i}") for i in range(1, n))
    state._render_fn(state._h("div", {}, *spans), state.root)


def _setup_rerender(state):
    """Mount the same tree as a single static render."""
    n = _HOLE_TREE_SIZE
    state._n = n
    state._counter = 0

    def build(value):
        spans = [state._h("span", {}, str(value))]
        spans.extend(state._h("span", {}, f"static-{i}") for i in range(1, n))
        return state._h("div", {}, *spans)

    state._build = build
    state._render_fn(build(0), state.root)


def op_hole_update(state):
    """Update one signal — only the one hole-driven text node is touched.

    Wrapped in ``batch`` so effects flush synchronously inside the timed
    region, matching the behavior of ``op_full_rerender``.
    """
    state._counter += 1

    def update():
        state._setter(state._counter)

    state._reactivity.batch(update)


def op_full_rerender(state):
    """Re-render the entire tree and let the reconciler diff to one text update."""
    state._counter += 1
    state._render_fn(state._build(state._counter), state.root)


# (name, setup_fn, operation_fn, default_warmup)
BENCHMARKS = [
    ("create rows", _setup_empty, op_create_rows, 5),
    ("replace all rows", _setup_1k, op_replace_all, 5),
    ("partial update", _setup_1k, op_partial_update, 3),
    ("select row", _setup_1k, op_select_row, 5),
    ("swap rows", _setup_1k, op_swap_rows, 5),
    ("remove row", _setup_1k, op_remove_row, 5),
    ("create many rows", _setup_empty, op_create_many, 5),
    ("append rows", _setup_10k, op_append_rows, 5),
    ("clear rows", _setup_1k, op_clear_rows, 5),
]


HOLE_BENCHMARKS = [
    ("hole update (1k tree)", _setup_hole, op_hole_update, 5),
    ("full rerender (1k tree)", _setup_rerender, op_full_rerender, 5),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _bench_loop(make_state, setup_fn, op_fn, warmup, iterations):
    times = []
    for i in range(warmup + iterations):
        state = make_state()
        setup_fn(state)

        start = time.perf_counter()
        op_fn(state)
        elapsed_ms = (time.perf_counter() - start) * 1000

        state.cleanup()

        if i >= warmup:
            times.append(elapsed_ms)
    return times


def _summarise(name, times):
    avg = mean(times)
    sd = stdev(times) if len(times) > 1 else 0.0
    ci = 1.96 * sd / sqrt(len(times)) if len(times) > 1 else 0.0
    return {
        "name": name,
        "mean_ms": round(avg, 2),
        "stdev_ms": round(sd, 2),
        "ci95_ms": round(ci, 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "iterations": len(times),
    }


def run_benchmarks(warmup_override=None, iterations=10, include_memory=False, name_filter=None):
    _install_stubs()
    mods = _load_wybthon()
    registry = mods["wybthon.reconciler"]._container_registry

    def _accept(name):
        return name_filter is None or name_filter in name

    def _make_state():
        registry.clear()
        return BenchState(mods, registry)

    def _make_hole_state():
        registry.clear()
        return _HoleState(mods, registry)

    results = []
    for name, setup_fn, op_fn, default_warmup in BENCHMARKS:
        if not _accept(name):
            continue
        warmup = warmup_override if warmup_override is not None else default_warmup
        times = _bench_loop(_make_state, setup_fn, op_fn, warmup, iterations)
        results.append(_summarise(name, times))

    for name, setup_fn, op_fn, default_warmup in HOLE_BENCHMARKS:
        if not _accept(name):
            continue
        warmup = warmup_override if warmup_override is not None else default_warmup
        times = _bench_loop(_make_hole_state, setup_fn, op_fn, warmup, iterations)
        results.append(_summarise(name, times))

    memory = None
    if include_memory and (name_filter is None or "memory" in name_filter):
        memory = _measure_memory(_make_state)

    return results, memory


def _measure_memory(make_state):
    tracemalloc.start()

    state = make_state()
    ready_cur, _ = tracemalloc.get_traced_memory()

    state.set_data(state.build_data(1000))
    run_cur, _ = tracemalloc.get_traced_memory()

    state.cleanup()
    state2 = make_state()
    for _ in range(5):
        state2.set_data(state2.build_data(1000))
        state2.set_data([])
        state2.set_selected(None)
    cycle_cur, _ = tracemalloc.get_traced_memory()

    tracemalloc.stop()

    return {
        "ready_mb": round(ready_cur / (1024 * 1024), 2),
        "run_1k_mb": round(run_cur / (1024 * 1024), 2),
        "create_clear_5x_mb": round(cycle_cur / (1024 * 1024), 2),
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_table(results, memory=None):
    lines = []
    lines.append("")
    lines.append("Wybthon Framework Benchmark (stubbed DOM, fine-grained app)")
    lines.append("=" * 78)
    lines.append(
        f"{'Benchmark':<24} {'Mean (ms)':>10} {'± 95% CI':>10} "
        f"{'Std Dev':>10} {'Min':>10} {'Max':>10} {'Slowdown':>10}"
    )
    lines.append("-" * 78)

    fastest = min(r["mean_ms"] for r in results) if results else 1.0
    if fastest <= 0:
        fastest = 0.01

    for r in results:
        slowdown = r["mean_ms"] / fastest
        lines.append(
            f"{r['name']:<24} {r['mean_ms']:>10.2f} {r['ci95_ms']:>9.2f} "
            f"{r['stdev_ms']:>10.2f} {r['min_ms']:>10.2f} {r['max_ms']:>10.2f} "
            f"{slowdown:>9.2f}x"
        )

    if memory:
        lines.append("")
        lines.append("Memory (Python heap via tracemalloc)")
        lines.append("-" * 44)
        lines.append(f"  Ready:                   {memory['ready_mb']:>8.2f} MB")
        lines.append(f"  After 1k rows:           {memory['run_1k_mb']:>8.2f} MB")
        lines.append(f"  After 5x create/clear:   {memory['create_clear_5x_mb']:>8.2f} MB")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Wybthon framework benchmark (js-framework-benchmark operations)",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--memory", action="store_true", help="Include memory measurements")
    parser.add_argument(
        "--bench",
        type=str,
        default=None,
        help="Run only benchmarks whose name contains this substring",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=None,
        help="Warmup iterations per benchmark (default: per-benchmark)",
    )
    parser.add_argument("--iterations", type=int, default=10, help="Measured iterations (default: 10)")
    args = parser.parse_args()

    results, memory = run_benchmarks(
        warmup_override=args.warmup,
        iterations=args.iterations,
        include_memory=args.memory,
        name_filter=args.bench,
    )

    if args.json:
        output = {"benchmarks": results}
        if memory:
            output["memory"] = memory
        print(json_module.dumps(output, indent=2))
    else:
        print(format_table(results, memory))


if __name__ == "__main__":
    main()
