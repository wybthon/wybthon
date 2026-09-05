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
from typing import Any

from js import document, window

from wybthon import kernel
from wybthon.dom import Element
from wybthon.events import set_handler
from wybthon.flow import For
from wybthon.reactivity import Accessor, Setter, create_selector, create_signal, flush
from wybthon.reconciler import render
from wybthon.store import create_store
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
random.seed(42)
STORE_MODE = "mode=store" in str(window.location.search)

Row = dict[str, Any]

data: Any
set_data: Any
if STORE_MODE:
    _store, set_data = create_store(list[Row]())

    def data():
        return _store

else:
    data, set_data = create_signal(list[Row]())

selected: Accessor[int | None]
set_selected: Setter[int | None]
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
        if STORE_MODE:
            result.append({"id": _next_id, "label": label})
        else:
            label_get, label_set = create_signal(label)
            result.append({"id": _next_id, "label": label_get, "set_label": label_set})
        _next_id += 1
    return result


# ---------------------------------------------------------------------------
# Row template — built once per item, updated through signals
# ---------------------------------------------------------------------------


def _row(d, idx):
    iid = d["id"]
    return h(
        "tr",
        {"class": lambda: "danger" if _is_selected(iid) else ""},
        h("td", {"class": "col-md-1"}, str(iid)),
        h(
            "td",
            {"class": "col-md-4"},
            h("a", {"on_click": lambda e: set_selected(iid)}, (lambda: d["label"]) if STORE_MODE else d["label"]),
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
    h("tbody", {"id": "tbody"}, For(data, _row)),
)
render(app, container)


# ---------------------------------------------------------------------------
# Benchmark operations — every one is a batch of signal writes.
#
# Writes batch automatically; the explicit ``flush()`` settles effects
# and commits the DOM synchronously so the benchmark measures the full
# update inside the delegated click handler. The checkout comparison
# also invokes these operations directly to isolate runtime work from
# event dispatch.
# ---------------------------------------------------------------------------


def run(e=None):
    set_data(build_data(1000))
    set_selected(None)
    flush()


def run_lots(e=None):
    set_data(build_data(10000))
    set_selected(None)
    flush()


def add(e=None):
    if STORE_MODE:
        set_data(lambda rows: rows.extend(build_data(1000)))
    else:
        set_data(lambda rows: rows + build_data(1000))
    flush()


def update(e=None):
    if STORE_MODE:

        def edit(rows):
            for i in range(0, len(rows), 10):
                rows[i]["label"] += " !!!"

        set_data(edit)
    else:
        rows = data()
        for i in range(0, len(rows), 10):
            rows[i]["set_label"](lambda label: label + " !!!")
    flush()


def clear(e=None):
    set_data([])
    set_selected(None)
    flush()


def swap_rows(e=None):
    def swap(rows):
        if len(rows) > 998:
            rows[1], rows[998] = rows[998], rows[1]

    if STORE_MODE:
        set_data(swap)
    else:
        rows = list(data())
        swap(rows)
        set_data(rows)
    flush()


def select(item_id):
    set_selected(item_id)
    flush()


def delete(item_id):
    if STORE_MODE:
        index = next(index for index, row in enumerate(data()) if row["id"] == item_id)

        def remove(draft):
            del draft[index]

        set_data(remove)
    else:
        set_data(lambda rows: [d for d in rows if d["id"] != item_id])
    flush()


# ---------------------------------------------------------------------------
# Wire up button handlers
# ---------------------------------------------------------------------------

for button_id, handler in (
    ("run", run),
    ("runlots", run_lots),
    ("add", add),
    ("update", update),
    ("clear", clear),
    ("swaprows", swap_rows),
):
    set_handler(kernel.adopt(document.getElementById(button_id)), "on_click", handler)
kernel.emit((kernel.OP_ROOT, kernel.adopt(document.getElementById("main"))))
kernel.commit()
