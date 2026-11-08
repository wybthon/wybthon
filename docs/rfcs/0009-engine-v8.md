# RFC 0009: Engine v8: a leaner core, one clone path, and a Pythonic surface

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-11-07

## Summary

Make the reactive core cost what the work costs, put every template on the clone path, and make the API one obvious way to do each thing in Python. Engine v8 changes three layers:

1. **The reactive core.** Effects reuse one apply scope for their lifetime instead of allocating and disposing an owner per run; a re-run applies at once when no transition can hold it; memo and store reads take one straight-line path outside transitions, actions, and probes; an empty flush returns before doing any bookkeeping; disposal's fast path covers effects and stays on while transitions are open; callback arities are computed once per function definition. Framework modules write signals through four named methods instead of passing write origins to a private `_set`.
2. **Rendering.** SVG and MathML templates clone like any other markup, under any parent, instead of mounting node by node; hydration no longer re-sends the static attributes the server already wrote.
3. **The API.** Reading a prop never calls a function the parent passed; a component call is typed as a `Node`; one event spelling per layer; `is_pending` is `False` during a first load, as in Solid 2.0; tests fail on errors no boundary handled; dev warnings are Python warnings; `with set_state.edit() as draft:` and `with untrack():`; `For` rows may take the item alone; the router's hooks return tracked mappings; `wyb check` type-checks the props of component tags in markup; and the top-level namespace keeps what applications use.

The virtual DOM, the batched JavaScript kernel, and the reactive semantics stay as they are.

## Motivation

### Solid 2.0 hasn't moved

npm's `latest` is still `solid-js@1.9.18`, and `next` is `2.0.0-rc.21`, which Engine v6 already targets. The changes queued on Solid's `next` branch since then are fixes (a cheaper context provider, `DEV.setSignal`, live server components). One documented behavior had drifted: Solid's async guide says `isPending()` is `false` while a first load shows a `Loading` fallback, and Wybthon's `is_pending` was `True`.

### The reactive core grew by accretion

A 190-line push-pull reference implementation (staged writes, lazy memos, owners, dynamic dependencies, all plain Python) measured how far each operation was from what the work costs. Native CPython 3.14, best of seven:

| Operation | v0.43.0 | Reference | Ratio |
| --- | ---: | ---: | ---: |
| Write and flush, a memo read by 100 render effects | 225 µs | 59 µs | 3.8x |
| Write and flush, one render effect | 3.1 µs | 1.0 µs | 3.1x |
| Create and dispose 1,000 render effects | 2.75 ms | 0.86 ms | 3.2x |
| Dispose 1,000 render effects | 614 µs | 210 µs | 2.9x |
| An empty `flush()` | 0.52 µs | 0.05 µs | 11.4x |
| A framework binding (the template fast path) | 1.15 µs | 0.85 µs | 1.3x |

Template bindings had already been made lean in Engine v5; the public primitives, updates, flushes, and disposal hadn't. Profiles showed why: every effect run allocated and disposed a fresh apply owner, every re-run inside a flush was queued as a tuple and replayed by `_partition_applies` even with no transition open, every memo read checked async state, actions, held values, errors, readiness, and probes in turn, every empty flush paused and resumed the collector, and disposal's fast path was off for any effect (they all have an extension record) and whenever a transition was open.

The core's write protocol had also leaked: 23 call sites in 12 modules passed write origins (`_set(value, _core._O_REVEAL)`) to a private method.

### SVG fell off the clone path

Any template containing `<svg>` or `<math>`, and any template mounted under an SVG parent, expanded into a VNode tree and mounted node by node. An inline SVG icon in a list row made creating rows about six times slower and the commands twenty times larger. The HTML parser handles foreign content inside `<template>` correctly; what it can't do is restore the case of SVG names outside the specification's table, and that was the only real constraint.

### Hydration re-sent what the server wrote

Hydrating 1,000 benchmark rows sent 19,007 commands (569 KB of JSON), where a client render sends 1,008. A third of them set static attributes the server had already written.

### The surface had sharp edges

An outside-in audit, writing small applications against the documentation, found these, each reproduced:

- A prop annotated `Any` (or any non-callable type) called a function the parent passed, at every read: a click handler ran when read, then crashed.
- `@component` was typed as returning its props class, so `-> VNode` and `list[VNode]` failed under mypy, and `key=` failed on a component without props.
- Errors in holes, bindings, and effects were printed, so a test passed against an empty DOM. Dev warnings were printed too, so `pytest.warns` and `-W error` couldn't see them.
- Four spellings bound the same handler (`onclick`, `onClick`, `on:click`, `on_click`), and `on:click` meant something different from Solid's.
- `For(items, lambda item: ...)` failed: rows had to take an index.
- `use_params()` returned an accessor (`use_params()()["id"]`), while `use_location()` returned an object with tracked attributes.
- `children()` shadowed the most common variable name, and the router's `resolve` collided with the async `resolve`.
- The props of a component tag (`<{Card} title={...}>`) weren't type-checked at all.
- The documentation imported names that no longer exist (`Link`, `current_path`).
- Editing a store field from a handler needed a nested function, and seeding several values without tracking needed a lambda per read.

## Design

### 1. The reactive core

- **One apply scope per effect.** An effect's apply stage runs under an owner created on its first apply and reused afterwards: before each run, `Owner._reset` cancels the previous run's tasks and disposes its children and cleanups. A run allocates nothing.
- **Re-runs apply at once when nothing can hold them.** A re-run inside a flush is deferred to the round's partition only while transitions are open or async work is live (`_track`), or while the computation has a held publication. Otherwise it applies immediately, as a first run does.
- **Straight-line reads.** `Memo._read` returns the value directly for a settled synchronous memo outside every transition, action, probe, and readiness scope, and calls `_read_slow` otherwise. A store field read takes the same shape: a plain store already read, outside transitions, actions, probes, and authoritative scopes, reads its field signal (tracked) or its committed container (untracked) without consulting `visible()`. The store setter checks for a draft callback before the ABC checks that replacement data needs.
- **Empty flushes.** A flush with nothing staged, queued, held, or pending commits any buffered DOM commands and returns, keeping the round counter and `_track` current for reads outside the flush.
- **Disposal.** The fast path covers any computation that owns nothing and has no readers, including effects whose apply scope holds nothing, and it no longer turns off while a transition is open (it schedules a flush, as the slow path does). Outside a browser, ending a commit window re-enables the collector directly.
- **Arity once.** `_arity(fn)` caches whether a function takes a positional parameter and how many, per code object, for plain functions without defaults: a lambda written once in source is the same code object every time it's created.
- **A named write protocol.** Framework modules write through `Signal._write(value)` (a staged write whose origin the scope decides), `_reveal(value)` (never held), `_commit_derived(value)` (committed now, classified by the running computation's sources), and `_commit_revealed(value)`. Write origins are private to the core again.
- **`is_pending` and first loads.** A probe no longer counts an async read that has never had a value, and `is_pending` no longer treats `NotReadyError` as pending: a first load is `Loading`'s to show.

### 2. Rendering

**SVG and MathML clone.** The template builder tracks each element's namespace while it walks the literal: fixed by an `<svg>`, `<math>`, or `foreignObject` inside the template, or inherited from the parent the template mounts under. It records each child and component slot's namespace in the plan, so the hole regions those slots create mount their content in the right namespace. A template is cloned under any parent unless an SVG or MathML name in it has capitals the HTML parser wouldn't restore (`parser_keeps_case`, using the specification's adjustment tables in `_html_rules`); such a template still expands. A template mounted under an SVG or MathML parent registers a second shape, `_NsShape`, whose `REGISTER_TPL` command carries a new eighth field, `wrap`: the kernel parses its markup inside `<svg>` or `<math>` and clones what's inside. A template whose inherited elements would end foreign content (`div`, `p`, and the other breakout tags) isn't cloned under an SVG parent. The generated mount function takes the parent's namespace (`mount(vnode, parent, anchor, ns=None)`), so one function serves every parent. The test DOM's parser tracks namespaces and restores SVG case the way a browser's does.

**Hydration.** Expanding a template while claiming server HTML leaves out its static attributes.

**Dead code.** The kernel's `REMOVE` command (nothing emitted it) is gone.

### 3. The API

**Props read expressions, not functions.** A prop read unwraps a getter the compiler made from markup, and an accessor (a signal or memo) the parent passed, unless the field is annotated callable or as `Accessor[T]`. Any other value, a plain function included, comes back as the parent passed it, whatever the field's annotation. `is_static` and `merge` follow the same rule. Outside markup, a reactive prop is an accessor: `Card(title=create_memo(lambda: user().name))`.

**`Node`.** `wybthon.Node` is the type of anything that renders. `VNode` subclasses it, and, to type checkers only, so does `Props`, so a component call, typed as its props class, is a `Node`: `-> Node`, `list[Node]`, and `children: Node` accept it. A component without props is typed as `PlainComponent`, a callable taking only `key`.

**One event spelling per layer.** On an element in markup, `onclick` is a delegated handler and `on:click` a native listener on the element, as in Solid; `onClick`, `on_click`, and other capitalizations are compile errors that name the spelling to use. In `h()` props, spreads, and component props, the Python name `on_click`. A native listener sends `LISTEN` with `direct: true`.

**Tests fail loudly.** `_warnings.log_error` calls `error_hook` when one is installed; `wybthon.testing` installs one that collects errors while a strict view is mounted and raises them (an `ExceptionGroup` for several) from `render`, from the `fire` call that caused them, and when the `with` block ends. `render(view, strict=False)` only logs. A failed query prints the markup, `screen.debug()` prints it on demand, inputs are named by their `<label>`, and the pytest plugin unmounts views a test left mounted.

**Warnings are warnings.** Dev diagnostics are issued with `warnings.warn` as `WybthonWarning`, so `pytest.warns(WybthonWarning)` and `-W error::wybthon.WybthonWarning` work; `_warnings.warning_hook` sees each one as it's issued, for an overlay or a test suite.

**Pythonic forms.** `StoreSetter.edit()` is a context manager yielding the draft; its changes stage together when the block ends, and an exception discards them. `untrack()` without a function is a context manager. A `For` or `map_array` callback that takes one parameter receives the item alone.

**Router.** `use_params()` returns `Params` and `use_search_params()` returns `(SearchParamsView, set_search)`: read-only mappings whose reads are tracked, as Solid's `useParams()` and `useSearchParams()` return reactive objects. `wybthon.router.resolve` is `match_route`.

**`wyb check`.** `wyb check [paths] [--checker mypy|pyright]` runs a type checker over a shadow copy of the project in which each component tag in markup is also written as the call it stands for, on the same line, and reports errors in those calls at the tag's line.

**The namespace.** `wybthon` exports what applications use. `h`, `hole`, `VNode`, and `Fragment` move to `wybthon.vnode`; `Owner`, `get_observer`, `create_reaction`, `map_array`, `repeat`, and `is_accessor` to `wybthon.reactivity`. `children` is `resolve_children`. `Node` and `WybthonWarning` are new.

**Documentation.** A test resolves every `wybthon` import in the documentation's code blocks and every API cross-reference, so a removed or renamed name can't linger in the docs.

## Breaking changes

| Removed or changed | Replacement |
| --- | --- |
| A prop read called a plain function (or bound method) the parent passed to a non-callable field | It returns the function; pass an accessor (`create_memo(fn)`) for a reactive prop outside markup |
| `is_pending` was `True` during a first load | `False`; the `Loading` boundary shows a first load |
| `onClick`, `on_click`, and other spellings on elements in markup | `onclick`; `on:click` for a native listener |
| `on:click` was a delegated alias | A native listener on the element |
| `onClick` in `h()` props | `on_click` |
| Dev warnings printed `[wybthon] Warning: ...` to stderr | `WybthonWarning`s through `warnings.warn` (and `_warnings.warning_hook`) |
| `wybthon.testing.render` logged errors no boundary handled | It raises them (`strict=False` to log) |
| `from wybthon import h, hole, VNode, Fragment` | `from wybthon.vnode import ...` |
| `from wybthon import Owner, get_observer, create_reaction, map_array, repeat, is_accessor` | `from wybthon.reactivity import ...` |
| `children(fn)` | `resolve_children(fn)` |
| `wybthon.router.resolve` | `wybthon.router.match_route` |
| `use_params()` returned an `Accessor[dict]` | A `Params` mapping: `use_params()["id"]` |
| `use_search_params()` returned `(Accessor[SearchParams], setter)` | `(SearchParamsView, setter)`: `search.get("page")` |
| `@component` without props was typed `Callable[[], VNode]` | `PlainComponent` (takes `key`, returns `Node`) |
| `REGISTER_TPL` had seven fields | Eight: `wrap` |
| Kernel command `REMOVE` (6) | Removed |
| Generated mount functions took `(vnode, parent, anchor)` | `(vnode, parent, anchor, ns=None)` |
| Bytecode cache tag `opt-wyb2` | `opt-wyb3` |
| Framework calls of `Signal._set(value, origin)` and `_commit_now(value, origin)` | `_write`, `_reveal`, `_commit_derived`, `_commit_revealed` |

## Alternatives considered

**A clean-room rewrite of the reactive core.** The audit's reference implementation is a fraction of the size, but the transition engine's semantics are pinned by over a thousand tests and Solid 2.0's own rulings, which keep changing in its release candidates. Restructuring the hot paths behind the existing tests took most of the cost out without putting those semantics at risk. Splitting the transition machinery into an overlay the sync graph never touches remains the next step for the core.

**Claiming a whole template instance in one hydration command.** A `CLAIM_TPL` that registers a server-rendered template's nodes in one walk, as a clone does, would bring hydration down to about one command per instance. The kernel can't tell where a slot's server content ends without markers the server doesn't write today, so it needs a change to the server's output format as well, and verification in a browser for every slot shape. Dropping static attributes is the safe third of it.

**A binary command protocol.** JSON serialization is about 6% of creating rows in CPython and the kernel's parse a small part of the browser's commit. Not worth a string table.

**Keeping `onClick`.** It's the JSX spelling, and markup in Wybthon is HTML: `onclick` is what HTML calls the attribute, and one spelling makes every template read the same.

**Unwrapping zero-argument functions in props.** That was the old rule, and it's why a callback annotated `Any` ran when read. Solid passes functions through too: only the compiler's getters make a prop reactive.

## Drawbacks and risks

- **A reused apply scope.** An owner captured with `get_owner()` in an effect's apply stage stays alive across runs; something created under it later belongs to the effect's next run instead of being disposed at once.
- **Two namespaces for a template.** A template mounted under HTML and under SVG registers two kernel templates.
- **Strict tests.** Tests that rendered failing views on purpose need `strict=False`.
- **Every compiled module recompiles**, once, because of the new cache tag.

## Testing

- The unit suite (1,175 tests, plus 1,763 documentation checks), with new tests for SVG and MathML cloning (`tests/test_svg_templates.py`), the Pythonic forms and strict testing (`tests/test_pythonic_api.py`), `wyb check` (`tests/test_check.py`), the documentation's imports and cross-references (`tests/test_docs_references.py`), the one-argument `For` row, rejected event spellings, and the native `on:click` listener.
- The typing fixtures, under mypy and pyright: component calls as `Node`, `key=` on a component without props, and one-argument rows.
- The browser suite (95 tests in Chromium on Pyodide 314.0.6), with a template mounted under an SVG parent and `For` rows of SVG elements.
- The core benchmark against the reference implementation, `benchmarks/row_bench.py`, and the hydration command count, against v0.43.0.

## Results

See [Engine v8 benchmark results](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v8.md).

## Unresolved questions

- Splitting transitions, async, and probes into an overlay the plain signal graph never consults.
- Hydrating a template instance with one claim, which needs slot markers in server output.
- Mounting a component tag without its hole and component VNodes.

## Decision

Accepted on 2026-11-07. Wybthon is pre-1.0 and has no production users yet, so the changes ship without a compatibility layer.
