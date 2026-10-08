# mypy: ignore-errors
# (Runs against any checkout, including ones with older APIs.)
"""Native js-framework-benchmark row workloads, comparable across checkouts.

Usage:

    python benchmarks/row_bench.py <checkout>/src [--reps N] [--noselect]

The backend JSON-encodes every command batch exactly like the browser
backend but applies nothing, so each time is the Python cost of the
operation: building rows, reconciling, wiring bindings, and serializing.
The browser adds the JavaScript kernel's DOM work on top.

Rows are written with the HTML helpers. Selection uses each checkout's
idiomatic primitive: `create_selector` where it exists (v0.36.0 and
earlier) and a projection otherwise. `--noselect` drops the selection
binding to compare the rendering engines alone. Prints JSON: the minimum
and median process CPU time per workload, the commands the last sample
sent, and Python bytes retained per mounted row.
"""

import gc
import json
import random
import sys
import time
import tracemalloc
from types import ModuleType

src = sys.argv[1]
sys.path.insert(0, src)
reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 5

js = ModuleType("js")
js.document = None
sys.modules["js"] = js

from wybthon import kernel  # noqa: E402


class RecBackend:
    def __init__(self):
        self.ops = 0
        self.bytes = 0

    def apply(self, ops):
        s = json.dumps(ops, separators=(",", ":"), ensure_ascii=False)
        self.bytes += len(s)
        self.ops += len(ops)

    def supports_html(self):
        return True

    def set_dispatcher(self, fn):
        pass


be = RecBackend()
kernel.set_backend(be)

from wybthon.dom import Element  # noqa: E402
from wybthon.flow import For  # noqa: E402
from wybthon.reactivity import create_signal, flush  # noqa: E402
from wybthon.reconciler import render  # noqa: E402
from wybthon.vnode import h  # noqa: E402

try:
    from wybthon.reactivity import create_selector

    def make_selector(selected):
        return create_selector(selected)

except ImportError:
    from wybthon import create_projection

    def make_selector(selected):
        proj = create_projection(lambda: {} if selected() is None else {selected(): True})
        return lambda key: bool(proj.get(key))


random.seed(1)
A = ["pretty", "large", "big", "small", "tall", "short", "long", "handsome"]
C = ["red", "yellow", "blue", "green", "pink", "brown"]
N = ["table", "chair", "house", "bbq", "desk", "car", "pony"]

data, set_data = create_signal([])
selected, set_selected = create_signal(None)
is_sel = make_selector(selected)
if "--noselect" in sys.argv:

    def is_sel(key):
        return False


_next = [1]


def build(n):
    out = []
    for _ in range(n):
        g, s = create_signal(f"{random.choice(A)} {random.choice(C)} {random.choice(N)}")
        out.append({"id": _next[0], "label": g, "set_label": s})
        _next[0] += 1
    return out


from wybthon.html import a, span, td, tr  # noqa: E402


def row(d, idx):
    iid = d["id"]
    return tr(
        td(str(iid), class_="col-md-1"),
        td(a(d["label"], on_click=lambda e: set_selected(iid)), class_="col-md-4"),
        td(
            a(span(class_="glyphicon glyphicon-remove", aria_hidden="true"), on_click=lambda e: None), class_="col-md-1"
        ),
        td(class_="col-md-6"),
        class_=lambda: "danger" if is_sel(iid) else "",
    )


root_el = Element(node_id=kernel.alloc_id())
render(h("table", {"class": "t"}, h("tbody", {"id": "tbody"}, For(data, row))), root_el)


def clock():
    return time.process_time()


def measure(setup, op, n=reps):
    times = []
    ops = []
    for _ in range(n):
        setup()
        gc.collect()
        be.ops = 0
        t = clock()
        op()
        times.append((clock() - t) * 1000)
        ops.append(be.ops)
    return {"min": round(min(times), 2), "median": round(sorted(times)[len(times) // 2], 2), "ops": ops[-1]}


def clear():
    set_data([])
    set_selected(None)
    flush()


def mount(n):
    def go():
        clear()
        global pending
        pending = build(n)

    return go


pending = []


def do_set():
    set_data(pending)
    flush()


results = {}
for _ in range(2):
    set_data(build(1000))
    flush()
    clear()

results["create_1k"] = measure(mount(1000), do_set)


def setup_replace():
    set_data(build(1000))
    flush()
    global pending
    pending = build(1000)


results["replace_1k"] = measure(setup_replace, do_set)
results["create_10k"] = measure(mount(10000), do_set, n=max(2, reps // 2))


def setup_n(n):
    def go():
        clear()
        set_data(build(n))
        flush()

    return go


results["clear_1k"] = measure(setup_n(1000), clear)
results["clear_10k"] = measure(setup_n(10000), clear, n=max(2, reps // 2))


def update10():
    rows = data()
    for i in range(0, len(rows), 10):
        rows[i]["set_label"](lambda v: v + " !!!")
    flush()


results["update_10th_10k"] = measure(lambda: None if len(data()) == 10000 else setup_n(10000)(), update10)
sel = [0]


def select():
    sel[0] += 1
    set_selected(sel[0] * 7 % 10000 + data()[0]["id"])
    flush()


results["select_10k"] = measure(lambda: None, select)


def swap():
    rows = list(data())
    rows[1], rows[998] = rows[998], rows[1]
    set_data(rows)
    flush()


results["swap_10k"] = measure(lambda: None, swap)


def remove_first():
    set_data(data()[1:])
    flush()


results["remove_first_10k"] = measure(setup_n(10000), remove_first, n=max(2, reps // 2))


def setup_append():
    setup_n(10000)()
    global pending
    pending = data() + build(1000)


results["append_1k_to_10k"] = measure(setup_append, do_set, n=max(2, reps // 2))

# memory per row
clear()
items = build(1000)
gc.collect()
tracemalloc.start()
s0 = tracemalloc.take_snapshot()
set_data(items)
flush()
gc.collect()
s1 = tracemalloc.take_snapshot()
tracemalloc.stop()
results["bytes_per_row"] = round(sum(x.size_diff for x in s1.compare_to(s0, "filename")) / 1000)
clear()
print(json.dumps(results, indent=1))
