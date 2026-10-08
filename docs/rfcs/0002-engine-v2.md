# RFC 0002: Engine v2: compiled mounting, typed props, and Solid 2.0 RC.14 alignment

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-10-07

## Summary

Rebuild the rendering path for speed, make component props typed and explicit, and align the public API with the SolidJS 2.0 release candidate. The Virtual DOM stays: it remains the batching layer between Python and the browser. What changes is how much Python work each mounted node costs, how components declare their inputs, and which names the package exports.

The change has six parts:

1. **Compiled mounting.** Each repeated subtree shape gets a generated mount function. One fused kernel command clones, fills, inserts, and wires a whole row. Teardown releases native nodes in bulk instead of walking every node in Python.
2. **Lighter reactive nodes and rows.** Render bindings run their expression directly instead of through a wrapper closure, and list rows release the static nodes they never patch, so a row allocates, retains, and disposes less.
3. **Typed, explicit props.** Components declare inputs on a `Props` class that pyright and mypy check without a plugin. The declared type, not a function's argument count, decides whether a prop is reactive.
4. **Python 3.14 and template strings.** The runtime already runs Python 3.14 in Pyodide. Requiring it everywhere enables t-string holes such as `p(t"Count: {count}")`.
5. **Solid 2.0 RC.14 alignment.** Add the primitives the release candidate exports, and remove the ones it dropped.
6. **Production and housekeeping.** Production builds turn dev mode off, the package imports less at startup, a usable test renderer ships, and modules that only exist for historical reasons go away.

## Motivation

### Rendering spends its time in Python

Profiling a 1,000-row table (the js-framework-benchmark shape) with a recording backend shows that Python work dominates. The browser's DOM work is under 15% of the time to create rows. Each row costs:

- about 187 Python function calls to mount and 72 to dispose;
- about 66 garbage-collected container objects, retaining roughly 9.75 KB;
- 7 kernel commands (`CLONE_TPL`, `SET_ATTR`, `SET_TEXT`, `HOLE_TEXT`, two `LISTEN`, and `INSERT`).

The largest costs are:

| Share of create time | Where |
| --- | --- |
| 28% | Building a `MountPlan`: the guarded extraction routine runs about 90 checks per row and allocates order and binding lists |
| 13% | Building the row's VNodes (user code) |
| 11% | `_mount_template` plus seven command tuples |
| 11% | The reactive `class` binding (one `Computation`) |
| 10% | The label hole (one `Computation` and two closures) |
| 10% | `set_handler`, twice |

Clearing 10,000 rows takes about 420 ms in the browser, yet sends only two commands. Nearly all of it is `_dispose_tree`, which visits 100,000 nodes in Python and probes three global tables for each one. Replacing every row removes them one at a time: 1,000 range removals and 1,000 releases.

A prototype that compiled each shape into a mount function was 4.1 to 4.9 times faster for create and clear at both 1,000 and 10,000 rows. It skipped VNode construction, so a realistic target is about 3 times.

### Props are untyped outside mypy, and reactivity is decided by argument count

`Component.__call__(*children: Any, **props: Any)` means pyright and Pylance check nothing at a component's call sites. Only the bundled mypy plugin rewrites the signature.

Wybthon decides what's reactive by counting a function's required arguments. Any zero-argument callable is treated as a reactive expression, including at component boundaries. A parent passing `on_close=lambda: set_open(False)` makes the child's `on_close()` *call* the handler when it reads the prop. The documentation teaches workarounds: `literal()`, `props.raw()`, and `on_done()()`.

### The API has drifted from Solid 2.0

Wybthon pins Solid 2.0 RC.9. RC.14 exports `createReaction`, `repeat`, `TimeoutError`, `NoHydration`, `Hydration`, `isHydrating`, `httpStatus`, and `httpHeader`. It removed `createSelector` (use `createProjection`) and `renderToStringAsync` (await `renderToStream`). Its `Errored` fallback receives an error accessor, and its `children` helper resolves nested accessors and offers `toArray()`.

### Production builds ship development checks

`DEV_MODE` defaults to `True`, and nothing in `wyb build` or the production bootstrap turns it off. Production apps pay for dev-only checks and print development warnings. `wybthon.testing.render_test` also fails outside the browser with `ModuleNotFoundError: js`, so applications can't unit test components with the shipped helper.

## Design

### 1. Compiled mounting

The VDOM, holes, reconciler, and kernel stay. The template fast path changes from "describe a plan, then interpret it" to "run a function generated for this shape."

**Shapes.** The first mount of an element subtree walks it once and records a *shape*:

- the serialized skeleton HTML;
- the pre-order node count;
- each text slot's offset;
- each binding's offset and kind (event, reactive prop, static prop, ref);
- each dynamic child's offset (hole or nested mount).

Shapes are cached by structure, as today.

**Mount functions.** A repeated shape gets a generated Python function. It does everything the current `build_plan` plus `_mount_template` pair does, in straight-line code:

- guard the instance's structure;
- allocate the id block;
- append one fused command;
- wire bindings by offset;
- mount holes;
- record the template root on the root VNode.

The guards avoid allocations: no `tuple(props)` per node, and no order or binding lists. A guard failure falls back to the generic path. The generated source contains only framework names and integer offsets; tags, prop names, and static values live in a constants table, as they do now.

**Fused commands.** `REGISTER_TPL` carries the skeleton, the text-slot offsets, and the delegated event types per offset. One `CLONE` command then:

- clones the prototype;
- registers its nodes;
- fills its text slots;
- marks its delegated listeners;
- inserts it before an anchor.

The command is `[op, first_id, tpl_id, parent_id, anchor_id, ...texts]`. A row that used seven commands uses one, and the per-row JSON payload falls from about 140 to about 40 bytes.

**Text holes.** A hole whose neighbors in the skeleton aren't text uses a text-node placeholder instead of a comment. Its first text result fills that placeholder's slot in the clone command, which is still being built when the hole first runs, so a row with a text label costs no extra command. Later results are plain `nodeValue` writes.

**Lazy node ids.** A template-mounted subtree records its first id and its shape on the root VNode, and assigns ids to the static descendants' `el` fields only when the reconciler first needs them. That happens when a hole patches the subtree, or when a dynamic child needs an anchor. List rows and component output are never patched, so they skip those assignments entirely.

**Released static nodes.** List rows and component output are never patched: a row only moves or leaves, and a component only receives new props. Once such a subtree mounts from a template, its static VNodes are released, and the root keeps only its shape, its first node id, its dynamic children, and its binding computations. That roughly halves the memory a row retains, and the collector has fewer objects to scan.

**Native teardown.** `DISPOSE_RANGE` and `DISPOSE` remove nodes and release every registered descendant inside the kernel, walking the removed nodes natively. Python no longer builds and sends lists of every id. Python-side registrations (handlers, reactive bindings, refs) are found through the shape's binding offsets, not by visiting every node. Clearing a list becomes one native range removal plus disposal of each row's owner.

**Bulk replacement.** When a keyed list reuses no rows, the region clears in one command and mounts the new rows as one splice, instead of reconciling 1,000 unrelated pairs.

**Event registration.** Handlers are stored in one table keyed by node id, with the event key derived once per shape. Delegated listener types come from the template registration, so mounting a row with two handlers sends no `LISTEN` commands. Handlers may accept the event or take no arguments; the arity is checked once at registration: `on_click=lambda: set_open(False)`.

### 2. Lighter reactive nodes

Every hole and reactive attribute used to wrap its expression in a second closure that turned "not ready" and errors into special values. A `keep` flag on the framework's render computations now gives the same behavior directly: a source that isn't ready keeps the current DOM state, and an error routes to the nearest `Errored` boundary through the apply stage. Framework-created computations pass their apply arity explicitly instead of inspecting the callback's signature.

The reactive core stays in one module. Its hot paths read module globals, and splitting it across modules would turn those reads into attribute lookups on the critical path. That's the opposite of this RFC's goal.

### 3. Typed, explicit props

Components declare inputs on a subclass of `Props`. The component function takes one parameter annotated with that class:

```python
from collections.abc import Callable

from wybthon import Prop, Props, button, component, create_signal, div, p, prop


class CounterProps(Props):
    label: Prop[str]
    initial: Prop[int] = prop(default=0)
    on_change: Callable[[int], None] | None = None


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())

    def increment():
        set_count(lambda n: n + 1)
        if props.on_change is not None:
            props.on_change(count.peek() + 1)

    return div(p(props.label, ": ", count), button("+", on_click=increment))


@component
def App():
    return Counter(label="Clicks", initial=5)
```

- `Props` is a [PEP 681](https://peps.python.org/pep-0681/) `dataclass_transform` base, so pyright and mypy check `Counter(label="Clicks", initial=5)` with no plugin. A missing required prop, a wrong type, or an unknown name is a type error. At run time an unknown or missing required prop raises `TypeError` in dev mode.
- A `Prop[T]` field accepts `T`, an accessor of `T`, or a zero-argument function returning `T`. Reading `props.label` returns an `Accessor[T]`. Place it in the tree to create a hole, call it inside a tracking scope, or use `.peek()`.
- Any other field is plain data. `props.on_change` is the callable the parent passed, never invoked by the read. A plain field reads the parent's latest value without tracking.
- Defaults use `prop(default=...)`. Checkers only recognize a field specifier's default when it's passed by keyword. Plain fields use ordinary defaults.
- `ParentProps` declares `children: Prop[Child]`. Children are passed as the `children` keyword, or with item syntax: `Card(title="Hi")[h2("Body"), p("More")]`.
- A component with no inputs takes no parameters. Calling a component returns a node. Its static return type is the props class, which is how checkers validate the keywords; every child position accepts it.
- `merge(*sources)` and `omit(props, *keys)` accept props instances; `omit` also accepts a predicate. Both return reactive mappings that can be spread onto elements.

DOM positions keep their rule: a zero-argument callable placed as a child or as an attribute value is a reactive expression. That's Wybthon's spelling of JSX's `{expr}`. Event handlers and refs are never reactive. The arity rule no longer applies anywhere else.

### 4. Python 3.14 and template strings

`requires-python` becomes `>=3.14`, matching the Pyodide 314 runtime that production builds already target. Server rendering, tests, and tooling run on the same version as the browser.

A [PEP 750](https://peps.python.org/pep-0750/) template string is a reactive expression wherever text is accepted:

```python
p(t"Count: {count} (doubled: {doubled})")
a("Profile", href=t"/users/{user_id}")
div(class_=t"card card-{variant}")
```

- Interpolations that are accessors or zero-argument functions are called inside one binding, so the whole string updates together. Other interpolations are formatted once.
- Conversions and format specifications apply (`t"{price:.2f}"`).
- A template string with no reactive interpolations is static text.

### 5. Solid 2.0 RC.14 alignment

Added:

| Solid 2.0 RC.14 | Wybthon |
| --- | --- |
| `createReaction(effect)` | `create_reaction(effect, *, error=None)` returns `track(fn)` |
| `repeat(count, map, { from, fallback })` | `repeat(count, fn, *, start=0, fallback=None)` |
| `mapArray(list, map, { fallback })` | `map_array(..., fallback=...)` |
| `children(fn).toArray()` | `children(fn)` resolves nested accessors; `.to_array()` |
| `reconcile(value, key)` | `key` may be a string, a function, or `None` |
| `omit(props, predicate)` | `omit(props, predicate)` |
| `TimeoutError` | `until(..., timeout=)` raises the built-in `TimeoutError` |
| `NoHydration`, `Hydration`, `isHydrating` | `NoHydration`, `Hydration`, `is_hydrating()` |
| `httpStatus`, `httpHeader`, `getRequestEvent` | `http_status`, `http_header`, `get_request_event`, and `RequestEvent`, exported from `wybthon` (no-ops in the browser) |
| `Errored` fallback `(err: Accessor, reset)` | `fallback=lambda err, reset: ...` where `err` is an accessor |

Removed:

- `create_selector`. Use `create_projection`, which notifies only the keys it changes.
- `render_to_string_async`. `render_to_stream(view)` returns a `RenderStream`: iterate it for chunks, or await it for the complete HTML.
- `create_render_effect` with no apply stage. Like Solid, it takes `(compute, apply)`.

### 6. Production, testing, startup, and housekeeping

**Production mode.**
- `wyb build` writes the mode into the bundle manifest, and the bootstrap calls `set_dev_mode(False)` before the application imports.
- `wyb dev` keeps dev mode on.
- The stale `DEV_MODE` export is removed; `is_dev_mode()` is the live flag.

**Startup.**
- The top-level package no longer imports the router, forms, virtual lists, or server helpers.
- Stores load on first use; list regions learn about store lists when the store module registers itself.
- `hashlib` loads only when hydration keys are needed.

**Testing.** `wybthon.testing` renders into the in-memory DOM in plain CPython:

```python
from wybthon.testing import fire, render

screen = render(Counter(label="Clicks"))
fire.click(screen.get_by_text("+"))
assert screen.get_by_text("Clicks: 1")
```

It provides:
- queries by text, role, label, and test id, each with `get`, `query`, and `get_all` variants;
- `fire` helpers;
- `screen.html()`;
- automatic cleanup between tests.

**Namespace.**
- `wybthon` exports the core: reactivity, components, flow control, boundaries, stores, DOM helpers, rendering, and context.
- The router, forms, and virtual lists are imported from `wybthon.router`, `wybthon.forms`, and `wybthon.virtual`.
- `wybthon.router_core` merges into `wybthon.router`.
- The DOM attribute module becomes private.
- The kernel's JavaScript moves out of a Python string into `_kernel.js`, where it can be linted.

**HTML helpers.**
- Missing tags are added: `b`, `i`, `u`, `s`, `sub`, `sup`, `kbd`, `abbr`, `cite`, `q`, `dl`, `dt`, `dd`, `iframe`, `template`, `slot`, `output`, `data`, `del_`, `ins`, `samp`, `var`, `wbr`, `address`, `hgroup`, `search`, and `menu`.
- `class` normalization lives in one place.

**Tooling.**
- The dev server's static-directory mode and its `/__manifest` endpoint are removed. The browser test fixture and benchmark app become ordinary `wybthon.toml` projects.
- `ruff format` replaces Black.
- CI runs on Python 3.14, and the coverage gate rises from 45% to 80%.

## Breaking changes

| Removed or changed | Replacement |
| --- | --- |
| Python 3.12 and 3.13 support | Python 3.14 |
| Component parameters annotated `Prop[T]` (`def Card(title: Prop[str])`), `**rest`, and a bare `props` parameter | One parameter annotated with a `Props` subclass |
| `prop(value)` | `prop(default=value)` on a `Props` field |
| `wybthon.mypy_plugin` | Not needed; checkers understand `Props` natively |
| `literal`, `LiteralValue`, `Props.raw` | Declare callbacks as plain (non-`Prop`) fields |
| `Props` as a mapping of accessors (`props["name"]`, iteration) | Attribute access on the typed instance; `merge` and `omit` for spreading |
| `create_selector` | `create_projection` |
| `wybthon.server.render_to_string_async` | `await render_to_stream(view)` |
| `create_render_effect(fn)` with one argument | `create_render_effect(compute, apply)` or `create_tracked_effect(fn)` |
| `Errored` fallback receiving the exception | It receives an accessor; call `err()` |
| `children(fn)` returning a flat list | An accessor of resolved children with `.to_array()` |
| Router, forms, virtual list, and scheduling names exported from `wybthon` | Import from `wybthon.router`, `wybthon.forms`, and `wybthon.virtual` |
| `wybthon.router_core` | `wybthon.router` |
| `wybthon.props` (DOM attribute application) | Private (`wybthon._dom_props`) |
| `wybthon.DEV_MODE` | `wybthon.is_dev_mode()` |
| `wybthon.testing.render_test` | `wybthon.testing.render` |
| `wyb dev --dir` serving a directory without `wybthon.toml`, and `/__manifest` | A `wybthon.toml` project |
| Kernel wire protocol (`CLONE_TPL`, `LISTEN` per handler, `RELEASE` id lists) | `CLONE`, template-declared listeners, `DISPOSE_RANGE` and `DISPOSE`; internal |

## Alternatives considered

**Remove the VDOM and compile to direct DOM calls, as Solid does.** Rejected. Every DOM call from Python crosses the bridge, and the VDOM's batching is why mounting 1,000 rows is one crossing. Profiling shows the remaining cost is Python bookkeeping around the VDOM, not the VDOM itself.

**A build-time AST compiler** that rewrites `div(...)` trees into template factories. Deferred. It would also remove VNode construction, worth about 13% of create time beyond this RFC. But it needs source access the bytecode-only production build doesn't keep, and it must reason about name shadowing. Runtime shape compilation captures most of the gain with none of those constraints. It also gives a future compiler a ready target.

**Keep parameter-style components and the mypy plugin.** Rejected. Pyright and Pylance users get no checking, and the plugin must track mypy's internals. Function parameters can't be checked without a plugin: the body needs accessors while call sites pass plain values, and Python's type system can't express that mapping.

**Class components** (`class Card(Component)` with a `render` method). Rejected. They type-check, but they move away from Solid's function components and its `props` object, which the `Props` class mirrors directly.

**A binary wire format.** Rejected for now. JSON encoding is about 5% of commit time. Fusing commands reduces the payload more than a new encoding would.

**A `Runtime` object replacing module globals.** Deferred. It would help thread-safe server rendering, but it adds an indirection to every signal read.

**Do nothing.** Mounting stays about 3 times slower than it needs to be, pyright users stay unchecked, and production builds keep shipping development checks.

## Drawbacks and risks

- Small components get more verbose: a props class plus a function, instead of annotated parameters.
- A component call is statically typed as its props class. Code that inspects the result with `isinstance` sees a `VNode` at run time.
- Requiring Python 3.14 excludes older interpreters for server rendering and tests.
- Generated mount functions add code that's harder to read than an interpreter loop. The guards must stay exhaustive, or a changed shape could be mounted with a stale routine. Fallback tests cover every guard.
- Native teardown relies on the kernel walking removed nodes. Content parked off-document by `Loading` must be disposed explicitly, since it isn't inside the removed range.

## Testing

- **Unit tests.** Every existing behavior suite is ported to the new component API. That covers reactivity, transitions, async, stores, flow, boundaries, the router, forms, server rendering, and hydration. New suites cover:
  - generated mount guards, including every fallback path;
  - native teardown and replacement;
  - zero-argument handlers;
  - t-strings in text and attributes;
  - `Props` typing at run time;
  - the RC.14 additions;
  - production mode;
  - the test renderer.
- **Type checks.** A typing fixture runs under both mypy and pyright, with expected errors for missing, mistyped, and unknown props.
- **Browser tests.** The Playwright suite runs against the converted fixture project, including hydration and production builds.
- **Work gates.** `benchmarks/check_work.py` gates command counts. Appending 1,000 rows must emit 1,000 row commands, not 7,000. Selection and swap must still emit two.
- **Benchmarks.** Native and browser benchmarks compare against v0.36.0 with the existing interleaved method. Targets:
  - create and replace at least 2.5 times faster in Python;
  - clearing 10,000 rows at least 3 times faster;
  - update, select, swap, and remove no slower;
  - lower retained memory per row.

### Results

The [engine v2 evaluation](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v2.md) measured the implementation against v0.36.0:

- **Python cost** (`benchmarks/row_bench.py`):
  - Creating and replacing rows is 1.4 to 1.5 times faster in the idiomatic table, and 1.8 to 1.9 times faster for the engine alone, without the selection binding.
  - Clearing is 2.0 to 2.5 times faster.
  - Each row sends one command instead of seven.
  - A mounted row retains 44% less memory.
- **Startup:** application startup is 60% faster.
- **Targets:** both speedup targets were missed. Create reached 1.4 to 1.9 times against a target of 2.5, and clear reached 2.0 to 2.5 times against a target of 3. The largest remaining cost is building VNode trees in application code, which the deferred build-time compiler addresses.
- **Selection:** it's about 0.05 ms slower per change, because a projection does more work than the removed selector.

## Unresolved questions

- Whether to compile `For` row callbacks ahead of their first call, so the first row avoids the generic walk.
- Head management (`Title`, `Meta`). It belongs with a later routing and data-loading RFC.
- Whether `Props` should support generic components (`class ListProps[T](Props)`) beyond what the checkers infer today.
- Moving rarely used `Computation` and `Owner` fields into a side record allocated on first use. It would shrink each binding further, but it touches every transition path, so it's left for a focused change.
- `Hydration` is a passthrough: a `NoHydration` region stays static as a whole while hydrating. Islands that re-enable hydration inside it need ID namespaces in the hydration keys.

## Decision

Accepted on 2026-10-07. Wybthon is pre-1.0 and has no production users yet, so the breaking changes ship without a compatibility layer.
