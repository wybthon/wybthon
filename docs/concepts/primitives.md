# Primitives

Wybthon uses a signals-first reactive model matching SolidJS 2.0.
Component bodies run **once**; reactivity comes from accessors read
inside *reactive holes*, memos, and effects. This page is the reference
for each primitive. [Reactivity](reactivity.md) explains how they fit
together and when the graph flushes.

## Reactive holes

A **reactive hole** is a reactive expression placed in a template as a
child, and a **binding** is one placed in an attribute. In a template,
every dynamic expression (one that calls something, reads an
attribute, or indexes) is one: the [compiler](compiler.md) turns it
into a getter. An [`Accessor`][wybthon.Accessor] or a zero-argument
function placed directly is one too. The renderer runs each inside its
own render effect, so the component body runs once while the hole
patches its region of the DOM whenever its dependencies change.

```python
from wybthon import component, create_signal, html


@component
def Demo():
    count, set_count = create_signal(0)

    def tripled():
        return f"Tripled: {count() * 3}"

    def status():
        return "danger" if count() > 5 else "ok"

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <!-- 1) A dynamic expression as a child. -->
        <p>Doubled: <span>{count() * 2}</span></p>
        <!-- 2) An accessor as a child. -->
        <p>Count: {count}</p>
        <!-- 3) A function call: one hole that makes the call. -->
        <p>{tripled()}</p>
        <!-- 4) Several expressions in text: each one is its own binding. -->
        <p>Count is {count()}, doubled {count() * 2}</p>
        <!-- 5) A reactive attribute (any attribute except events and ref). -->
        <p class={status()}>Status</p>
        <!-- 6) Part of an attribute: one binding for the whole value. -->
        <p class="badge badge-{status()}">Badge</p>
        <button onclick={increment}>+1</button>
      </div>
    """)
```

Event handlers and refs are never reactive, so `onclick={increment}`
binds the function itself. In an [`h()`][wybthon.h] tree, which the
compiler doesn't rewrite, pass an accessor or a zero-argument function
as a child or prop value (`h("p", None, count)`), and use
[`hole`][wybthon.hole] to make a hole explicitly when it needs a `key`.

A hole's expression may return a string or number (a text node), a
template or other `VNode`, a list of either (mounted as a fragment),
`None` (nothing), or another accessor (nested hole). When it returns a
template from the same literal as last time, the mounted instance is
patched slot by slot instead of replaced. A binding whose expression
makes no calls (`{props.title}`, `{row["label"]}`) first runs under a
lightweight probe, and when it reads nothing reactive, its value is
applied and no computation is allocated. Any other hole that reads
nothing reactive on its first run is dropped after that run, keeping
the DOM it produced.

Holes are ownership scopes. Use [`on_cleanup`][wybthon.on_cleanup]
inside one to register teardown that runs before each re-evaluation and
on disposal:

```python
from wybthon import on_cleanup


def subscribe(topic_name):
    handle = open_subscription(topic_name)
    on_cleanup(handle.close)
    return f"listening to {topic_name}"


def status():
    return subscribe(topic())  # re-subscribes when topic changes


html(t"<p>{status()}</p>")
```

## `create_signal`

[`create_signal`][wybthon.create_signal] returns `(getter, setter)`,
typed as `Accessor[T]` and [`Setter`][wybthon.Setter]`[T]`.

```python
from wybthon import create_signal, flush

count, set_count = create_signal(0)
set_count(5)
count()  # 0: the write is staged
flush()  # automatic in the browser
count()  # 5
set_count(lambda n: n + 1)  # functional update sees staged values
count.peek()  # 5: untracked read of the committed value
```

- **Writes are staged.** The setter records the value; reads keep returning the committed value until the next flush. See [Staged writes](reactivity.md#staged-writes-and-flush-timing).
- **Functional updates** receive the latest staged value, so two `set(lambda n: n + 1)` calls in one handler add two. To store a callable as the value, return it from an updater: `set_fn(lambda _: my_callable)`.
- **`equals`** decides when observers are notified. The default, [`is_equal`][wybthon.is_equal], is an identity fast path followed by `==`; `equals=False` always notifies; a callable `(old, new) -> bool` skips notification when it returns `True` (use `lambda a, b: a is b` for identity-only semantics).
- **Function form.** `create_signal(lambda: a() + b())` returns a *writable derived signal*: it tracks what the function reads, and the setter overrides the value until the next source change.

Signals created in a component body live for the component's lifetime.
There are no hook rules.

## `create_memo`

[`create_memo`][wybthon.create_memo] returns a [`Memo`][wybthon.Memo], a
read-only accessor for a derived value.

```python
from wybthon import create_memo

doubled = create_memo(lambda: count() * 2)
doubled()  # tracked read
doubled.peek()  # untracked read
```

- **Eager setup, pull-based updates.** The body evaluates at creation unless `lazy=True`. After an input changes, reads bring the memo current.
- **Glitch-free.** Reading a memo brings its sources current first, so a diamond of memos never observes a half-updated state.
- **Equality short-circuits.** Observers are notified only when the value changed under `equals`.
- **Previous value.** If the body accepts a positional parameter it receives the previous value (`None` on the first run).
- **`lazy=True`** suspends the memo once it loses its last subscriber; a later read recomputes it; **`unobserved=`** runs a callback at that moment (for resource cleanup).
- **Async bodies.** An `async def` body (or an async generator) makes the memo an async computation. See [Async and loading](async-loading.md).

## `create_deferred`

[`create_deferred`][wybthon.create_deferred] is an async memo that may
lag but never holds the rest of the UI, the counterpart of Solid 2.0's
`createDeferred`. Before its first value, readers suspend to the
nearest [`Loading`][wybthon.Loading] like any async memo. After it, a
refetch opens no transition: readers keep the last value until the new
one lands, and everything else on the screen updates without waiting.
[`is_pending`][wybthon.is_pending] reports the refetch.

```python
from wybthon import For, create_deferred, html, is_pending


async def load_rows():
    return await fetch_rows(period())


rows = create_deferred(load_rows)

html(t"<section class={'stale' if is_pending(rows) else ''}>{For(rows(), row)}</section>")
```

It takes the same options as `create_memo`. Use it for independent
widgets (dashboards, feeds, search results), where the previous answer
with a "refreshing" hint beats waiting with everything else.

## `create_effect`

[`create_effect`][wybthon.create_effect] creates a side effect that
re-runs when its tracked sources change. Effects run **after the DOM
commit** in each flush, and the first run happens on the next flush,
right after the component that created it has mounted.

Both stages are required: `compute` runs tracked and returns a
value; `apply` runs untracked with `(value, prev)` (or `(value,)`) and
performs the side effect. Writes belong in `apply`.

```python
from wybthon import create_effect

create_effect(count, lambda value, prev: print(prev, "->", value))
create_effect(lambda: (a(), b()), lambda pair: print("changed:", pair))
```

`apply` may return a cleanup callable that runs before the next `apply`
and on disposal:

```python
def start(interval_ms):
    handle = set_interval(tick, interval_ms)
    return lambda: clear_interval(handle)


create_effect(interval, start)
```

The explicit **tracked effect** `create_tracked_effect(fn)` makes `fn` both the tracking
stage and the side effect. Use [`on_cleanup`][wybthon.on_cleanup] for
per-run teardown. Writing a signal inside it raises
[`WriteInScopeError`][wybthon.WriteInScopeError] in dev mode.

Other options:

- `compute` may accept a positional parameter to receive its previous return value.
- `compute` may be `async def`; awaits suspend the effect without blocking, and reads after an `await` are still tracked.
- `defer=True` skips the first `apply` (tracking still starts).
- `error=handler` receives exceptions from `compute` instead of routing them to the nearest [`Errored`][wybthon.Errored] boundary.
- The returned `Computation` (from `wybthon.reactivity`) has `.dispose()`.

## `create_render_effect`

[`create_render_effect`][wybthon.create_render_effect] takes the same
arguments as `create_effect`, including the required `apply` stage, but
runs in the **render phase**, before the DOM commit, and its first run
happens immediately at creation. Holes and attribute bindings are render
effects. Reach for it only when building a rendering primitive;
`create_effect` is right for application code. For a single tracked
function, use [`create_tracked_effect`][wybthon.create_tracked_effect].

## `create_reaction`

[`create_reaction`][wybthon.create_reaction] separates tracking from
re-execution. It returns `track(fn)`: calling `track` runs `fn` and
subscribes to what it reads, and the first time any of those sources
changes, the effect runs once (untracked, after the DOM commit) and the
subscription ends. Call `track` again to re-arm it.

```python
from wybthon import create_reaction

track = create_reaction(lambda: print("count changed"))
track(count)  # arms the reaction
set_count(1)  # prints once on the next flush
set_count(2)  # silent until track() is called again
```

## `untrack` and `.peek()`

[`untrack`][wybthon.untrack] runs a function with tracking suppressed.
Every accessor also has `.peek()` for a single untracked read.

```python
from wybthon import create_effect, untrack

create_effect(lambda: (a(), untrack(b)), lambda pair: print(pair))  # depends on a only
count.peek()  # the same idea for one read
```

Both silence the dev-mode top-level-read warning. A prop read returns
the value, not an accessor, so `untrack(lambda: props.initial)` is the
explicit way to seed local state from a prop.

## `on_settled`

[`on_settled`][wybthon.on_settled] runs a callback once the flush that
mounted the current component has committed, so refs are assigned and
the DOM is live. It may return a cleanup that runs on unmount.

```python
from wybthon import Props, Ref, component, html, on_settled


class ChartProps(Props):
    data: list[float]


@component
def Chart(props: ChartProps):
    ref = Ref()

    def start():
        handle = draw(ref.current, props.data)
        return lambda: handle.destroy()

    on_settled(start)
    return html(t"<canvas ref={ref}></canvas>")
```

## `on_cleanup`

[`on_cleanup`][wybthon.on_cleanup] registers teardown on the active
scope:

- In a component body: runs when the component unmounts.
- In a tracked effect or compute stage: runs before recomputation and on disposal. In a split effect's apply stage: runs before the next visible apply and on disposal.
- In a hole or `For` row: runs when that region is re-evaluated or removed.

It raises `RuntimeError` outside any scope.

## `create_root`, `get_owner`, and `run_with_owner`

[`create_root`][wybthon.create_root] runs a function inside a new,
ownership root and hands it a `dispose` callable. The root belongs to its current owner; `detached=True` creates an independent lifetime. Use it for
long-lived reactive work that shouldn't die with a component, such as
global stores.

```python
from wybthon import create_effect, create_root


def setup(dispose):
    create_effect(count, lambda value: print("count", value))
    return dispose


dispose = create_root(setup)
dispose()  # tears the effect down
```

`await` drops the active owner. Capture it with
[`get_owner`][wybthon.get_owner] before suspending and restore it with
[`run_with_owner`][wybthon.run_with_owner] when creating primitives
afterwards:

```python
from wybthon import get_owner, run_with_owner


async def later():
    owner = get_owner()
    await something()
    run_with_owner(owner, lambda: create_effect(count, lambda value: print("count", value)))
```

## Typing

Every reactive read goes through [`Accessor[T]`][wybthon.Accessor]:
signal getters are [`Signal[T]`][wybthon.Signal], memos are `Memo[T]`,
and setters are `Setter[T]`. Annotate function parameters as
`Accessor[T]` when they accept any of these. A props field is a plain
annotation, so `props.title` is typed as the field's type (`str`), and
a type checker checks a component call's arguments against it. See the
[Typing guide](../guides/typing.md).

## Props helpers

- [`prop(default_factory=...)`][wybthon.prop] declares a mutable default on a [`Props`][wybthon.Props] class (the factory runs once per instance); `prop(default=...)` works too, though an ordinary default (`step: int = 1`) needs no `prop()`.
- [`merge(*sources)`][wybthon.merge] merges props instances, dicts, and zero-arg functions returning dicts into one reactive view; later sources win, and `None` is a real value.
- [`omit(source, *keys)`][wybthon.omit] returns a reactive view without the given keys, or without every key a predicate accepts (the replacement for `split_props`).
- A view reads like props: `view.title` is the tracked value, and item access (`view["title"]`) returns an accessor. Spreading a view onto an element (`<button {attrs}>`) binds each key reactively.
- [`is_static(props, key)`][wybthon.is_static] reports whether the parent passed a plain value rather than an expression, without reading or tracking anything, as Solid 2.0's `isStatic` does.
- [`children(fn)`][wybthon.children] resolves a getter for a children prop (`lambda: props.children`) into a [`ChildrenAccessor`][wybthon.ChildrenAccessor]: nested accessors are resolved, lists are flattened, and `None` and booleans are dropped. Calling it returns the single child or a list; `.to_array()` always returns a list. [`flatten(children)`][wybthon.flatten] is the unmemoized form, matching Solid 2.0's `flatten`.

```python
from wybthon import merge, omit

attrs = merge({"type": "button"}, omit(props, "label", "children"))
handlers = omit(props, lambda key: not key.startswith("on_"))
```

## `map_array`

[`map_array`][wybthon.map_array] maps a reactive list to values with a stable
owner scope per row. `keyed` selects how rows are matched, and with it
the callback shape. `For` is a native list region with the same matching
modes, and it can consume store edit records directly:

| `keyed` | Rows matched by | `fn(item, index)` receives |
| --- | --- | --- |
| `True` (default) | identity (scalars by value) | raw item, `Accessor[int]` |
| `False` | position | `Accessor[T]`, `int` |
| `key(item)` callable | key | `Accessor[T]`, `Accessor[int]` |

```python
from wybthon import create_signal, map_array

items, set_items = create_signal(["A", "B", "C"])

by_identity = map_array(items, lambda item, idx: f"{idx()}: {item}")
by_position = map_array(items, lambda item, idx: f"[{idx}] {item()}", keyed=False)
by_key = map_array(rows, lambda row, idx: f"{idx()}: {row()['title']}", keyed=lambda r: r["id"])
```

Row bodies run untracked inside the row's owner, so anything reactive
inside a row must read an accessor within a hole, memo, or effect.
`fallback=` supplies a single row for the empty list.

## `repeat`

[`repeat`][wybthon.repeat] maps an integer range to rows, each with its
own owner scope. `fn(i)` runs once per slot for `i` in
`range(start, start + count)`; growing the count maps only the new
slots, and shrinking it disposes the removed ones. The `Repeat`
region uses the same model.

```python
from wybthon import create_signal, repeat

rating, set_rating = create_signal(3)
stars = repeat(rating, lambda i: f"star {i}", start=1)
stars()  # ["star 1", "star 2", "star 3"]
```

`count` and `start` may be plain ints or accessors, and `fallback=`
supplies a single row when the count is zero.

## Selection with `create_projection`

To mark one selected row without notifying every row, derive a
projection keyed by the selection with
[`create_projection`][wybthon.create_projection]. A projection notifies
only the keys it changes, so a new selection updates the row that was
selected and the one that was deselected:

```python
from wybthon import create_projection, create_signal

selected, set_selected = create_signal(1)
is_selected = create_projection(lambda: {} if selected() is None else {selected(): True})


html(t"<li class={'active' if is_selected.get(2) else None}>Item 2</li>")
```

`is_selected.get(key)` is tracked per key and returns `None` when the
key is absent. See [Stores](stores.md) for projections in general.

## Miscellany

- [`create_unique_id`][wybthon.create_unique_id] returns a process-unique string for `id`/`for` pairs.
- [`is_accessor`][wybthon.is_accessor] reports whether a value is a reactive expression (an `Accessor` or a zero-arg function); it's the rule the renderer uses at run time to decide what becomes a hole. The compiler makes its own decision earlier, from the expression's syntax; see [The compiler](compiler.md#the-rule-dynamic-or-static).
- [`is_equal(a, b)`][wybthon.is_equal] is the default equality of signals, memos, and stores: identity, then `==`.
- [`flush`][wybthon.flush] settles the graph now. Automatic in the browser; call it in tests.

## Next steps

- Read [Reactivity](reactivity.md) for flush timing and the ownership tree.
- See [Lifecycle and ownership](lifecycle.md) for disposal order.
- Browse the [`reactivity`](../api/reactivity.md) API reference.
