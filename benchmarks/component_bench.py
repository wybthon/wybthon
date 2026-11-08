# mypy: ignore-errors
# ruff: noqa: E501
# (Runs against any checkout with the compiler, v0.39.0 or later.)
"""What components, control flow, and hydration cost, comparable across checkouts.

Usage:

    python benchmarks/component_bench.py <checkout>/src [--reps N]

Each workload mounts 1,000 list rows that show the same markup, written four
ways: inline in the row's template (`plain`), with a `Show` in it (`show`),
as a component tag (`component`), and as a component tag whose body has a
`Show` (`component_show`). The backend JSON-encodes every command batch and
applies nothing, as `row_bench.py`'s does, so each time is Python's share.

For every workload it reports the best and median process CPU time to create
and to clear the rows, the commands and the Python calls per row, and the
Python bytes a mounted row retains. `hydrate` renders the `plain` and
`component` tables on the server and hydrates them into an in-memory
document, reporting the commands per row, the time, and the mismatches.

Prints JSON.
"""

import cProfile
import gc
import json
import pstats
import sys
import time
import tracemalloc
from types import ModuleType

src = sys.argv[1]
sys.path.insert(0, src)
reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 7

js = ModuleType("js")
js.document = None
sys.modules["js"] = js

import wybthon  # noqa: E402,F401
from wybthon import kernel  # noqa: E402

try:
    from wybthon import set_dev_mode
except ImportError:  # pragma: no cover - older checkouts
    from wybthon._warnings import set_dev_mode


class RecBackend:
    def __init__(self):
        self.ops = 0

    def apply(self, ops):
        json.dumps(ops, separators=(",", ":"), ensure_ascii=False)
        self.ops += len(ops)

    def supports_html(self):
        return True

    def set_dispatcher(self, fn):
        pass


set_dev_mode(False)
be = RecBackend()
kernel.set_backend(be)

from wybthon.compiler import compile_source  # noqa: E402
from wybthon.dom import Element  # noqa: E402
from wybthon.flow import For  # noqa: E402
from wybthon.reactivity import create_signal, flush  # noqa: E402
from wybthon.reconciler import render  # noqa: E402
from wybthon.vnode import h  # noqa: E402

ROWS = '''
from wybthon import ParentProps, Show, component, create_signal, html


class CardProps(ParentProps):
    title: str
    count: int = 0


@component
def Card(props: CardProps):
    return html(t"""<div class="card"><h3>{props.title}</h3><span>{props.count}</span><button onclick={(lambda: None)}>t</button>{props.children}</div>""")


@component
def ShowCard(props: CardProps):
    open_, _ = create_signal(False)
    return html(t"""<div class="card"><h3>{props.title}</h3><span>{props.count}</span><button onclick={(lambda: None)}>t</button>{Show(open_(), html(t"<p>open</p>"))}{props.children}</div>""")


def plain(item, index):
    return html(t"""<div class="card"><h3>{item["label"]}</h3><span>{item["id"]}</span><button onclick={(lambda: None)}>t</button><em>{item["id"]}</em></div>""")


def show(item, index):
    open_, _ = create_signal(False)
    return html(t"""<div class="card"><h3>{item["label"]}</h3><span>{item["id"]}</span><button onclick={(lambda: None)}>t</button>{Show(open_(), html(t"<p>open</p>"))}<em>{item["id"]}</em></div>""")


def component(item, index):
    return html(t"<{Card} title={item['label']} count={item['id']}><em>{item['id']}</em></{Card}>")


def component_show(item, index):
    return html(t"<{ShowCard} title={item['label']} count={item['id']}><em>{item['id']}</em></{ShowCard}>")


def table(items, row):
    return html(t"<section>{For(items, row)}</section>")
'''

rows_module = ModuleType("component_bench_rows")
sys.modules["component_bench_rows"] = rows_module
rows_module.__dict__["For"] = For
exec(compile_source(ROWS, "component_bench_rows.py"), rows_module.__dict__)

ITEMS = [{"id": i, "label": f"label {i}"} for i in range(1000)]
WORKLOADS = ("plain", "show", "component", "component_show")


def clock():
    return time.process_time()


def summary(times):
    times = sorted(times)
    return {"min": round(times[0] * 1000, 2), "median": round(times[len(times) // 2] * 1000, 2)}


def measure(name):
    data, set_data = create_signal([])
    render(h("div", {}, For(data, getattr(rows_module, name))), Element(node_id=kernel.alloc_id()))
    flush()
    create, clear = [], []
    for _ in range(reps):
        set_data([])
        flush()
        gc.collect()
        be.ops = 0
        t = clock()
        set_data(list(ITEMS))
        flush()
        create.append(clock() - t)
        ops = be.ops
        gc.collect()
        t = clock()
        set_data([])
        flush()
        clear.append(clock() - t)
    gc.collect()
    tracemalloc.start()
    set_data(list(ITEMS))
    flush()
    gc.collect()
    retained, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    set_data([])
    flush()
    profile = cProfile.Profile()
    profile.enable()
    set_data(list(ITEMS))
    flush()
    profile.disable()
    calls = pstats.Stats(profile).total_calls
    set_data([])
    flush()
    return {
        "create": summary(create),
        "clear": summary(clear),
        "commands_per_row": round(ops / len(ITEMS), 2),
        "calls_per_row": round(calls / len(ITEMS), 1),
        "bytes_per_row": round(retained / len(ITEMS)),
    }


def hydration(name):
    from wybthon.reconciler import hydrate
    from wybthon.server import render_to_string
    from wybthon.testing import TestDocument, TestNode, _Parser

    def view():
        return rows_module.table(ITEMS, getattr(rows_module, name))

    html = render_to_string(view())
    times, commands, mismatches = [], 0, 0
    for _ in range(max(3, reps // 2)):
        container = TestNode(tag="div")
        parser = _Parser(container)
        parser.feed(html)
        parser.close()
        backend = kernel.PythonBackend(TestDocument())
        counted = [0]
        apply = backend.apply

        def counting(ops, apply=apply):
            counted[0] += len(ops)
            return apply(ops)

        backend.apply = counting
        kernel.set_backend(backend)
        gc.collect()
        t = clock()
        root = hydrate(view(), Element(node=container))
        times.append(clock() - t)
        commands = counted[0]
        mismatches = backend.hydration_mismatches
        root.dispose()
    kernel.set_backend(be)
    return {"hydrate": summary(times), "commands_per_row": round(commands / len(ITEMS), 2), "mismatches": mismatches}


report = {name: measure(name) for name in WORKLOADS}
report["hydrate"] = {name: hydration(name) for name in ("plain", "component")}
print(json.dumps(report, indent=1))
