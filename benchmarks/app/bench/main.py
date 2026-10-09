"""Wybthon benchmark app: the js-framework-benchmark keyed implementation.

The app is written the idiomatic Wybthon way: the table and its controls
mount once, every operation is a signal (or store) write, rows are cached
per item by `For`, row labels are per-row signals, and selection is a
projection that notifies only the two rows whose state changes.

`benchmarks/app` is an ordinary Wybthon project: the benchmark scripts build
it with `wyb build` and drive it from `index.html` through the runtime the
bootstrap exposes (`window.__WYB.pyodide`).

Reference: https://github.com/krausest/js-framework-benchmark
"""

import random
from typing import Any

from js import window

from wybthon import (
    Accessor,
    For,
    Setter,
    component,
    create_projection,
    create_signal,
    create_store,
    flush,
    html,
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

    def selected_class():
        return "danger" if is_selected.get(iid) else ""

    return html(
        t"""<tr class={selected_class}>
              <td class="col-md-1">{iid}</td>
              <td class="col-md-4"><a onclick={(lambda: select(iid))}>{label}</a></td>
              <td class="col-md-1">
                <a onclick={(lambda: delete(iid))}>
                  <span class="glyphicon glyphicon-remove" aria-hidden="true"></span>
                </a>
              </td>
              <td class="col-md-6"></td>
            </tr>"""
    )


def _control(label, element_id, handler):
    return html(
        t"""<div class="col-sm-6 smallpad">
              <button type="button" class="btn btn-primary btn-block" id={element_id} onclick={handler}>{label}</button>
            </div>"""
    )


@component
def App():
    return html(
        t"""<div>
              <div class="jumbotron">
                <div class="row">
                  <div class="col-md-6"><h1>Wybthon (keyed)</h1></div>
                  <div class="col-md-6">
                    <div class="row">
                      {_control("Create 1,000 rows", "run", run)}
                      {_control("Create 10,000 rows", "runlots", run_lots)}
                      {_control("Append 1,000 rows", "add", add)}
                      {_control("Update every 10th row", "update", update)}
                      {_control("Clear", "clear", clear)}
                      {_control("Swap Rows", "swaprows", swap_rows)}
                    </div>
                  </div>
                </div>
              </div>
              <table class="table table-hover table-striped test-data">
                <tbody id="tbody">{For(data, _row)}</tbody>
              </table>
            </div>"""
    )


def app():
    """The entry the bootstrap renders into `#app-root`."""
    return App()
