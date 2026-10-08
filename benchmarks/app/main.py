"""Wybthon benchmark app: the js-framework-benchmark keyed implementation.

The app is written the idiomatic Wybthon way: the table and its controls
mount once, every operation is a signal (or store) write, rows are cached
per item by `For`, row labels are per-row signals, and selection is a
projection that notifies only the two rows whose state changes.

It's loaded by `index.html` inside Pyodide, straight from the checkout's
sources (see `benchmarks/_serve.py`).

Reference: https://github.com/krausest/js-framework-benchmark
"""

import random
from typing import Any

from js import window

from wybthon import (
    Accessor,
    For,
    Setter,
    a,
    button,
    component,
    create_projection,
    create_signal,
    create_store,
    div,
    flush,
    h1,
    render,
    span,
    table,
    tbody,
    td,
    tr,
)

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
# Application state: plain signals (or a store), mounted once
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
# The selected row id maps to True; changing the selection updates two keys.
is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})


def _random(max_val):
    return int(random.random() * 1000) % max_val


def build_data(count):
    global _next_id
    result = []
    for _ in range(count):
        label = f"{ADJECTIVES[_random(len(ADJECTIVES))]} {COLOURS[_random(len(COLOURS))]} {NOUNS[_random(len(NOUNS))]}"
        if STORE_MODE:
            result.append({"id": _next_id, "label": label})
        else:
            label_get, label_set = create_signal(label)
            result.append({"id": _next_id, "label": label_get, "set_label": label_set})
        _next_id += 1
    return result


# ---------------------------------------------------------------------------
# Operations: every one is a batch of writes
#
# Writes batch automatically; the explicit `flush()` settles effects and
# commits the DOM synchronously, so the benchmark measures the full update
# inside the delegated click handler. The checkout comparison also calls
# these operations directly to isolate runtime work from event dispatch.
# ---------------------------------------------------------------------------


def run():
    set_data(build_data(1000))
    set_selected(None)
    flush()


def run_lots():
    set_data(build_data(10000))
    set_selected(None)
    flush()


def add():
    if STORE_MODE:
        set_data(lambda rows: rows.extend(build_data(1000)))
    else:
        set_data(lambda rows: rows + build_data(1000))
    flush()


def update():
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


def clear():
    set_data([])
    set_selected(None)
    flush()


def swap_rows():
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
# View
# ---------------------------------------------------------------------------


def _row(d, _index):
    iid = d["id"]
    label = (lambda: d["label"]) if STORE_MODE else d["label"]
    return tr(
        td(str(iid), class_="col-md-1"),
        td(a(label, on_click=lambda: select(iid)), class_="col-md-4"),
        td(
            a(span(class_="glyphicon glyphicon-remove", aria_hidden="true"), on_click=lambda: delete(iid)),
            class_="col-md-1",
        ),
        td(class_="col-md-6"),
        class_=lambda: "danger" if is_selected.get(iid) else "",
    )


def _control(label, element_id, handler):
    return div(
        button(label, type="button", class_="btn btn-primary btn-block", id=element_id, on_click=handler),
        class_="col-sm-6 smallpad",
    )


@component
def App():
    return div(
        div(
            div(
                div(h1("Wybthon (keyed)"), class_="col-md-6"),
                div(
                    div(
                        _control("Create 1,000 rows", "run", run),
                        _control("Create 10,000 rows", "runlots", run_lots),
                        _control("Append 1,000 rows", "add", add),
                        _control("Update every 10th row", "update", update),
                        _control("Clear", "clear", clear),
                        _control("Swap Rows", "swaprows", swap_rows),
                        class_="row",
                    ),
                    class_="col-md-6",
                ),
                class_="row",
            ),
            class_="jumbotron",
        ),
        table(tbody(For(data, _row), id="tbody"), class_="table table-hover table-striped test-data"),
    )


render(App(), "#app-root")
