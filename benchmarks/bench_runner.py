#!/usr/bin/env python3
"""Wybthon benchmark runner — js-framework-benchmark compatible operations.

Measures VDOM reconciler performance for all 9 standard operations from
krausest/js-framework-benchmark using a lightweight DOM stub. This isolates
the Python-side VDOM cost from browser/Pyodide overhead.

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


class _Document:
    def __init__(self):
        self._listeners = {}

    def createElement(self, tag):
        return _Node(tag=tag)

    def createTextNode(self, text):
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
    modules = {}
    for name in (
        "wybthon._warnings",
        "wybthon.dom",
        "wybthon.vnode",
        "wybthon.events",
        "wybthon.props",
        "wybthon.reactivity",
        "wybthon.context",
        "wybthon.error_boundary",
        "wybthon.suspense",
        "wybthon.portal",
        "wybthon.reconciler",
        "wybthon.vdom",
    ):
        mod = importlib.import_module(name)
        importlib.reload(mod)
        modules[name] = mod
    return modules


# ---------------------------------------------------------------------------
# Benchmark state
# ---------------------------------------------------------------------------


class BenchState:
    """Holds data, rendering context, and DOM root for one benchmark run."""

    def __init__(self, h_fn, render_fn, dom_mod, registry):
        self._h = h_fn
        self._render_fn = render_fn
        self._dom_mod = dom_mod
        self._registry = registry
        self.root = dom_mod.Element(node=_Node(tag="div"))
        self.data = []
        self.selected = -1
        self._next_id = 1

    def build_data(self, count):
        result = []
        nid = self._next_id
        for _ in range(count):
            label = (
                f"{ADJECTIVES[random.randint(0, len(ADJECTIVES) - 1)]} "
                f"{COLOURS[random.randint(0, len(COLOURS) - 1)]} "
                f"{NOUNS[random.randint(0, len(NOUNS) - 1)]}"
            )
            result.append({"id": nid, "label": label})
            nid += 1
        self._next_id = nid
        return result

    def build_tree(self):
        h = self._h
        sel = self.selected
        rows = []
        for item in self.data:
            iid = item["id"]
            rows.append(
                h(
                    "tr",
                    {"key": iid, "class": "danger" if iid == sel else ""},
                    h("td", {"class": "col-md-1"}, str(iid)),
                    h("td", {"class": "col-md-4"}, h("a", {}, item["label"])),
                    h(
                        "td",
                        {"class": "col-md-1"},
                        h("a", {}, h("span", {"class": "glyphicon glyphicon-remove", "aria-hidden": "true"})),
                    ),
                    h("td", {"class": "col-md-6"}),
                )
            )
        return h(
            "table",
            {"class": "table table-hover table-striped test-data"},
            h("tbody", {"id": "tbody"}, *rows),
        )

    def do_render(self):
        self._render_fn(self.build_tree(), self.root)

    def cleanup(self):
        self._registry.pop(id(self.root.element), None)


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _setup_empty(state):
    pass


def _setup_1k(state):
    state.data = state.build_data(1000)
    state.do_render()


def _setup_10k(state):
    state.data = state.build_data(10000)
    state.do_render()


# ---------------------------------------------------------------------------
# Benchmark operations (matching js-framework-benchmark)
# ---------------------------------------------------------------------------


def op_create_rows(state):
    """Create 1,000 rows."""
    state.data = state.build_data(1000)
    state.do_render()


def op_replace_all(state):
    """Replace all 1,000 rows with new data."""
    state.data = state.build_data(1000)
    state.do_render()


def op_partial_update(state):
    """Update every 10th row's label."""
    for i in range(0, len(state.data), 10):
        state.data[i] = {**state.data[i], "label": state.data[i]["label"] + " !!!"}
    state.do_render()


def op_select_row(state):
    """Highlight a selected row."""
    if state.data:
        state.selected = state.data[len(state.data) // 2]["id"]
    state.do_render()


def op_swap_rows(state):
    """Swap rows at indices 1 and 998."""
    if len(state.data) > 998:
        state.data[1], state.data[998] = state.data[998], state.data[1]
    state.do_render()


def op_remove_row(state):
    """Remove one row from the middle."""
    if state.data:
        mid = len(state.data) // 2
        target_id = state.data[mid]["id"]
        state.data = [d for d in state.data if d["id"] != target_id]
    state.do_render()


def op_create_many(state):
    """Create 10,000 rows."""
    state.data = state.build_data(10000)
    state.do_render()


def op_append_rows(state):
    """Append 1,000 rows to existing table."""
    state.data = state.data + state.build_data(1000)
    state.do_render()


def op_clear_rows(state):
    """Clear all rows."""
    state.data = []
    state.selected = -1
    state.do_render()


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


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _make_state(h_fn, render_fn, dom_mod, registry):
    registry.clear()
    return BenchState(h_fn, render_fn, dom_mod, registry)


def run_benchmarks(warmup_override=None, iterations=10, include_memory=False):
    _install_stubs()
    mods = _load_wybthon()

    h_fn = mods["wybthon.vdom"].h
    render_fn = mods["wybthon.vdom"].render
    dom_mod = mods["wybthon.dom"]
    registry = mods["wybthon.reconciler"]._container_registry

    results = []
    for name, setup_fn, op_fn, default_warmup in BENCHMARKS:
        warmup = warmup_override if warmup_override is not None else default_warmup
        times = []

        for i in range(warmup + iterations):
            state = _make_state(h_fn, render_fn, dom_mod, registry)
            setup_fn(state)

            start = time.perf_counter()
            op_fn(state)
            elapsed_ms = (time.perf_counter() - start) * 1000

            state.cleanup()

            if i >= warmup:
                times.append(elapsed_ms)

        avg = mean(times)
        sd = stdev(times) if len(times) > 1 else 0.0
        ci = 1.96 * sd / sqrt(len(times)) if len(times) > 1 else 0.0
        results.append(
            {
                "name": name,
                "mean_ms": round(avg, 2),
                "stdev_ms": round(sd, 2),
                "ci95_ms": round(ci, 2),
                "min_ms": round(min(times), 2),
                "max_ms": round(max(times), 2),
                "iterations": len(times),
            }
        )

    memory = None
    if include_memory:
        memory = _measure_memory(h_fn, render_fn, dom_mod, registry)

    return results, memory


def _measure_memory(h_fn, render_fn, dom_mod, registry):
    tracemalloc.start()

    state = _make_state(h_fn, render_fn, dom_mod, registry)
    ready_cur, _ = tracemalloc.get_traced_memory()

    state.data = state.build_data(1000)
    state.do_render()
    run_cur, _ = tracemalloc.get_traced_memory()

    state.cleanup()
    state2 = _make_state(h_fn, render_fn, dom_mod, registry)
    for _ in range(5):
        state2.data = state2.build_data(1000)
        state2.do_render()
        state2.data = []
        state2.selected = -1
        state2.do_render()
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
    lines.append("Wybthon Framework Benchmark (stubbed DOM)")
    lines.append("=" * 78)
    lines.append(
        f"{'Benchmark':<24} {'Mean (ms)':>10} {'± 95% CI':>10} "
        f"{'Std Dev':>10} {'Min':>10} {'Max':>10} {'Slowdown':>10}"
    )
    lines.append("-" * 78)

    fastest = min(r["mean_ms"] for r in results) if results else 1.0

    for r in results:
        slowdown = r["mean_ms"] / fastest if fastest > 0 else 0
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
