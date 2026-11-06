# mypy: ignore-errors
"""Server rendering throughput, comparable across checkouts (RFC 0006).

Usage:

    python benchmarks/ssr_bench.py <checkout>/src [--reps N]

Renders three pages with `render_to_string` in plain CPython and prints
JSON with the minimum and median wall time per render, in milliseconds:

- `table_1k` and `table_10k`: the js-framework-benchmark table (a keyed
  `For` of template rows with a dynamic class and text).
- `cards_1k`: 1,000 `Card` components (a component tag with props, a
  `Show`, and children) in a list.
- `boundaries`: a page of 50 `Errored` and `Loading` boundaries around
  components, with async data that isn't loaded (fallbacks render).

A checkout before RFC 0006 renders by mounting into an in-memory DOM and
serializing it; afterwards the server writes HTML directly. Both produce
the same markup, which this script checks against the first checkout it
is given when `--expect <file>` names a previous run's output.
"""

import gc
import json
import statistics
import sys
import time
from types import ModuleType

src = sys.argv[1]
sys.path.insert(0, src)
reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 7

js = ModuleType("js")
js.document = None
sys.modules["js"] = js

import wybthon  # noqa: E402,F401
from wybthon.compiler import compile_source  # noqa: E402
from wybthon.server import render_to_string  # noqa: E402

PAGES = '''
from wybthon import Errored, For, Loading, ParentProps, Show, component, create_memo, create_signal, html

ADJ = ["pretty", "large", "big", "small", "tall", "short", "long", "handsome"]


def rows(n):
    return [{"id": i, "label": f"{ADJ[i % 8]} row {i}"} for i in range(n)]


def table(n):
    data, _ = create_signal(rows(n))
    selected, _ = create_signal(3)

    def row(item, index):
        return html(t"""<tr class={"danger" if selected() == item["id"] else ""}>
              <td class="col-md-1">{item["id"]}</td>
              <td class="col-md-4"><a onclick={(lambda: None)}>{item["label"]}</a></td>
              <td class="col-md-1"><a><span class="glyphicon glyphicon-remove" aria-hidden="true"></span></a></td>
              <td class="col-md-6"></td>
            </tr>""")

    return html(t'<table class="table"><tbody id="tbody">{For(data(), row)}</tbody></table>')


class CardProps(ParentProps):
    title: str
    count: int = 0


@component
def Card(props: CardProps):
    open_, _ = create_signal(True)
    return html(t"""<article class="card">
      <h3>{props.title}</h3>
      {Show(open_(), html(t"<p>{props.count} items</p>"), fallback=html(t"<p>closed</p>"))}
      <footer>{props.children}</footer>
    </article>""")


def cards():
    items, _ = create_signal(rows(1000))

    def card(item, index):
        return html(t"<{Card} title={item['label']} count={item['id']}><em>{item['id']}</em></{Card}>")

    return html(t"<section>{For(items(), card)}</section>")


@component
def Panel():
    async def load():
        return 1

    value = create_memo(load)
    return html(t"<div><b>{value()}</b></div>")


def boundaries():
    def failed(err, reset):
        return html(t"<p>failed</p>")

    return html(t"""<main>{[
        Errored(Loading(html(t"<{Panel} />"), fallback=html(t"<p>loading</p>")), fallback=failed)
        for _ in range(50)
    ]}</main>""")
'''

pages = ModuleType("ssr_bench_pages")
sys.modules["ssr_bench_pages"] = pages
exec(compile_source(PAGES, "ssr_bench_pages.py"), pages.__dict__)

SCENARIOS = {
    "table_1k": lambda: pages.table(1000),
    "table_10k": lambda: pages.table(10000),
    "cards_1k": pages.cards,
    "boundaries": pages.boundaries,
}


def measure(view):
    render_to_string(view)
    times = []
    for _ in range(reps):
        gc.collect()
        start = time.perf_counter()
        html = render_to_string(view)
        times.append((time.perf_counter() - start) * 1000)
    return {"min": round(min(times), 2), "median": round(statistics.median(times), 2), "bytes": len(html)}, html


report = {}
outputs = {}
for name, view in SCENARIOS.items():
    report[name], outputs[name] = measure(view)
if "--expect" in sys.argv:
    expected = json.load(open(sys.argv[sys.argv.index("--expect") + 1]))
    report["matches"] = {name: outputs[name] == expected.get(name) for name in outputs}
if "--save" in sys.argv:
    json.dump(outputs, open(sys.argv[sys.argv.index("--save") + 1], "w"))
print(json.dumps(report, indent=1))
