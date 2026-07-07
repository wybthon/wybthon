"""Wybthon benchmark app — js-framework-benchmark keyed implementation.

This module implements the standard benchmark table the idiomatic
Wybthon way: the table mounts once, and every operation is a signal
write. Rows are cached per item via ``For``, row labels are per-row
signals, and selection flows through ``create_selector`` so each
operation touches only the DOM it must.

It is loaded by index.html inside Pyodide.

Reference: https://github.com/krausest/js-framework-benchmark
"""

import random

from js import document
from pyodide.ffi import create_proxy

from wybthon.dom import Element
from wybthon.flow import For
from wybthon.reactivity import batch, create_selector, create_signal
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
# Application state — plain signals, mounted once
# ---------------------------------------------------------------------------

_next_id = 1

data, set_data = create_signal([])
selected, set_selected = create_signal(None)
_is_selected = create_selector(selected)

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
        label_get, label_set = create_signal(label)
        result.append({"id": _next_id, "label": label_get, "set_label": label_set})
        _next_id += 1
    return result


# ---------------------------------------------------------------------------
# Row template — built once per item, updated through signals
# ---------------------------------------------------------------------------


def _row(item, idx):
    d = item()
    iid = d["id"]
    return h(
        "tr",
        {"class": lambda: "danger" if _is_selected(iid) else ""},
        h("td", {"class": "col-md-1"}, str(iid)),
        h(
            "td",
            {"class": "col-md-4"},
            h("a", {"on_click": lambda e: set_selected(iid)}, d["label"]),
        ),
        h(
            "td",
            {"class": "col-md-1"},
            h(
                "a",
                {"on_click": lambda e: delete(iid)},
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


app = h(
    "table",
    {"class": "table table-hover table-striped test-data"},
    h("tbody", {"id": "tbody"}, For(each=data, children=_row)),
)
render(app, container)


# ---------------------------------------------------------------------------
# Benchmark operations — every one is a signal write
# ---------------------------------------------------------------------------


def run(e=None):
    def update_state():
        set_data(build_data(1000))
        set_selected(None)

    batch(update_state)


def run_lots(e=None):
    def update_state():
        set_data(build_data(10000))
        set_selected(None)

    batch(update_state)


def add(e=None):
    set_data(lambda rows: rows + build_data(1000))


def update(e=None):
    rows = data()

    def update_state():
        for i in range(0, len(rows), 10):
            rows[i]["set_label"](lambda label: label + " !!!")

    batch(update_state)


def clear(e=None):
    def update_state():
        set_data([])
        set_selected(None)

    batch(update_state)


def swap_rows(e=None):
    rows = list(data())
    if len(rows) > 998:
        rows[1], rows[998] = rows[998], rows[1]
    set_data(rows)


def select(item_id):
    set_selected(item_id)


def delete(item_id):
    set_data(lambda rows: [d for d in rows if d["id"] != item_id])


# ---------------------------------------------------------------------------
# Wire up button handlers
# ---------------------------------------------------------------------------

document.getElementById("run").addEventListener("click", create_proxy(run))
document.getElementById("runlots").addEventListener("click", create_proxy(run_lots))
document.getElementById("add").addEventListener("click", create_proxy(add))
document.getElementById("update").addEventListener("click", create_proxy(update))
document.getElementById("clear").addEventListener("click", create_proxy(clear))
document.getElementById("swaprows").addEventListener("click", create_proxy(swap_rows))
