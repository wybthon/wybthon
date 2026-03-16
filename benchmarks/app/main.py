"""Wybthon benchmark app — js-framework-benchmark keyed implementation.

This module implements the standard benchmark table using Wybthon's VDOM
reconciler.  It is loaded by index.html inside Pyodide.

Reference: https://github.com/krausest/js-framework-benchmark
"""

import random

from js import document
from pyodide.ffi import create_proxy

from wybthon.dom import Element
from wybthon.reconciler import render
from wybthon.vnode import h

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
# Application state
# ---------------------------------------------------------------------------

data: list = []
selected = -1
_next_id = 1

container = Element(node=document.getElementById("table-container"))


def _random(max_val):
    return int(random.random() * 1000) % max_val


def build_data(count):
    global _next_id
    result = []
    for _ in range(count):
        label = (
            f"{ADJECTIVES[_random(len(ADJECTIVES))]} "
            f"{COLOURS[_random(len(COLOURS))]} "
            f"{NOUNS[_random(len(NOUNS))]}"
        )
        result.append({"id": _next_id, "label": label})
        _next_id += 1
    return result


# ---------------------------------------------------------------------------
# VNode tree builder
# ---------------------------------------------------------------------------


def _select_handler(item_id):
    def handler(e):
        select(item_id)

    return handler


def _delete_handler(item_id):
    def handler(e):
        delete(item_id)

    return handler


def build_tree():
    sel = selected
    rows = []
    for item in data:
        iid = item["id"]
        rows.append(
            h(
                "tr",
                {"key": iid, "class": "danger" if iid == sel else ""},
                h("td", {"class": "col-md-1"}, str(iid)),
                h(
                    "td",
                    {"class": "col-md-4"},
                    h("a", {"on_click": _select_handler(iid)}, item["label"]),
                ),
                h(
                    "td",
                    {"class": "col-md-1"},
                    h(
                        "a",
                        {"on_click": _delete_handler(iid)},
                        h(
                            "span",
                            {
                                "class": "glyphicon glyphicon-remove",
                                "aria-hidden": "true",
                            },
                        ),
                    ),
                ),
                h("td", {"class": "col-md-6"}),
            )
        )
    return h(
        "table",
        {"class": "table table-hover table-striped test-data"},
        h("tbody", {"id": "tbody"}, *rows),
    )


def _render():
    render(build_tree(), container)


# ---------------------------------------------------------------------------
# Benchmark operations
# ---------------------------------------------------------------------------


def run(e=None):
    global data, selected
    data = build_data(1000)
    selected = -1
    _render()


def run_lots(e=None):
    global data, selected
    data = build_data(10000)
    selected = -1
    _render()


def add(e=None):
    global data
    data = data + build_data(1000)
    _render()


def update(e=None):
    global data
    for i in range(0, len(data), 10):
        data[i] = {**data[i], "label": data[i]["label"] + " !!!"}
    _render()


def clear(e=None):
    global data, selected
    data = []
    selected = -1
    _render()


def swap_rows(e=None):
    global data
    if len(data) > 998:
        data[1], data[998] = data[998], data[1]
    _render()


def select(item_id):
    global selected
    selected = item_id
    _render()


def delete(item_id):
    global data
    data = [d for d in data if d["id"] != item_id]
    _render()


# ---------------------------------------------------------------------------
# Wire up button handlers
# ---------------------------------------------------------------------------

document.getElementById("run").addEventListener("click", create_proxy(run))
document.getElementById("runlots").addEventListener("click", create_proxy(run_lots))
document.getElementById("add").addEventListener("click", create_proxy(add))
document.getElementById("update").addEventListener("click", create_proxy(update))
document.getElementById("clear").addEventListener("click", create_proxy(clear))
document.getElementById("swaprows").addEventListener("click", create_proxy(swap_rows))
