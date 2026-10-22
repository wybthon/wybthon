# mypy: ignore-errors
# (Runs against any checkout, including ones with older APIs.)
"""Native js-framework-benchmark row workloads, comparable across checkouts.

Usage:

    python benchmarks/row_bench.py <checkout>/src [--reps N] [--noselect]

The backend JSON-encodes every command batch exactly like the browser
backend but applies nothing, so each time is the Python cost of the
operation: building rows, reconciling, wiring bindings, and serializing.
The browser adds the JavaScript kernel's DOM work on top.

Rows are `html` t-string templates, so the checkout needs templates
(RFC 0003, v0.38.0 or later). With the compiler (RFC 0004), the row module
is compiled the way an application's modules are, and its row is written
the Engine v4 way: `class={"danger" if is_sel(iid) else ""}` and
`{d["label"]}`, with no hand-written lambdas. Without it, the row uses the
idiom of its time, `class={(lambda: ...)}`. Selection uses each checkout's
idiomatic primitive: `create_selector` where it exists (v0.36.0 and
earlier) and a projection otherwise. `--noselect` drops the selection
binding to compare the rendering engines alone.

Prints JSON: the minimum and median process CPU time per workload, the
commands the last sample sent, the Python bytes and the objects the cyclic
garbage collector tracks per mounted row (with the objects by type), and
the total function calls for creating 1,000 rows (an untimed cProfile pass).
"""

import cProfile
import gc
import json
import pstats
import random
import sys
import time
import tracemalloc
from collections import Counter
from types import ModuleType

src = sys.argv[1]
sys.path.insert(0, src)
reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 5

js = ModuleType("js")
js.document = None
sys.modules["js"] = js

import wybthon  # noqa: E402,F401  (installs the import hook where one exists)
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


# The row module. Engine v4 compiles it, as the import hook or `wyb build`
# would compile an application module; older checkouts run it as is.
ROW_V4 = '''
from wybthon import html


def row(d, idx):
    iid = d["id"]
    return html(
        t"""<tr class={"danger" if is_sel(iid) else ""}>
              <td class="col-md-1">{iid}</td>
              <td class="col-md-4"><a onclick={(lambda e: set_selected(iid))}>{d["label"]}</a></td>
              <td class="col-md-1">
                <a onclick={(lambda e: None)}>
                  <span class="glyphicon glyphicon-remove" aria-hidden="true"></span>
                </a>
              </td>
              <td class="col-md-6"></td>
            </tr>"""
    )
'''

ROW_V3 = '''
from wybthon import html


def row(d, idx):
    iid = d["id"]
    return html(
        t"""<tr class={(lambda: "danger" if is_sel(iid) else "")}>
              <td class="col-md-1">{iid}</td>
              <td class="col-md-4"><a onclick={(lambda e: set_selected(iid))}>{d["label"]}</a></td>
              <td class="col-md-1">
                <a onclick={(lambda e: None)}>
                  <span class="glyphicon glyphicon-remove" aria-hidden="true"></span>
                </a>
              </td>
              <td class="col-md-6"></td>
            </tr>"""
    )
'''

try:
    from wybthon.compiler import compile_source
except ImportError:  # before RFC 0004: templates compile at run time
    compiled = False
    code = compile(ROW_V3, "row_bench_rows.py", "exec")
else:
    compiled = True
    code = compile_source(ROW_V4, "row_bench_rows.py")

rows_module = ModuleType("row_bench_rows")
rows_module.__dict__.update(is_sel=is_sel, set_selected=set_selected)
sys.modules["row_bench_rows"] = rows_module
exec(code, rows_module.__dict__)
row = rows_module.row

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


results = {"compiled": compiled}
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

# Python bytes retained per mounted row.
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
del s0, s1  # the snapshots hold their traces as tracked tuples

# Objects the cyclic collector tracks per mounted row, by type.
clear()
items = build(1000)
gc.collect()
before = Counter(type(o).__name__ for o in gc.get_objects())
set_data(items)
flush()
gc.collect()
after = Counter(type(o).__name__ for o in gc.get_objects())
grown = {name: after[name] - before[name] for name in after if after[name] != before[name]}
results["gc_objects_per_row"] = round(sum(grown.values()) / 1000, 2)
results["gc_objects_by_type"] = {
    name: round(count / 1000, 2)
    for name, count in sorted(grown.items(), key=lambda item: -item[1])
    if abs(count) >= 100  # at least 0.1 per row; drops incidental objects
}

# Function calls for creating 1,000 rows (untimed: the profiler's overhead).
clear()
pending = build(1000)
gc.collect()
profiler = cProfile.Profile()
profiler.runcall(do_set)
results["calls_create_1k"] = pstats.Stats(profiler).total_calls
clear()
print(json.dumps(results, indent=1))
