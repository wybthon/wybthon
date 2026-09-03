# Primitives

Wybthon uses a signals-first reactive model matching SolidJS 2.0.
Component bodies run **once**; reactivity comes from accessors read
inside *reactive holes*, memos, and effects. This page is the reference
for each primitive. [Reactivity](reactivity.md) explains how they fit
together and when the graph flushes.

## Reactive holes

A **reactive hole** is a reactive expression (an
[`Accessor`][wybthon.Accessor] or a zero-arg function) placed in a VNode
tree, as a child or as a prop value. The reconciler runs it inside its
own render effect, so the component body runs once while the hole
patches its region of the DOM whenever its dependencies change.

```python
from wybthon import component, create_signal, hole
from wybthon.html import button, div, p, span


@component
def Demo():
    count, set_count = create_signal(0)

    return div(
        # 1) An accessor as a child.
        p("Count: ", span(count)),
        # 2) A zero-arg expression as a child.
        p(lambda: f"Doubled: {count() * 2}"),
        # 3) The explicit form, when you need a key.
        p(hole(lambda: f"Tripled: {count() * 3}", key="triple")),
        # 4) A reactive prop value (any prop except event handlers and ref).
        p("Status", class_=lambda: "danger" if count() > 5 else "ok"),
        button("+1", on_click=lambda e: set_count(lambda n: n + 1)),
    )
```

A hole's expression may return a string or number (a text node), a
`VNode`, a list of either (mounted as a fragment), `None` (nothing), or
another accessor (nested hole).

Holes are ownership scopes. Use [`on_cleanup`][wybthon.on_cleanup]
inside one to register teardown that runs before each re-evaluation and
on disposal:

```python
from wybthon import on_cleanup


def subscribe(topic_name):
    handle = open_subscription(topic_name)
    on_cleanup(handle.close)
    return f"listening to {topic_name}"


p(lambda: subscribe(topic()))   # re-subscribes when topic changes
```

## `create_signal`

[`create_signal`][wybthon.create_signal] returns `(getter, setter)`,
typed as `Accessor[T]` and [`Setter`][wybthon.Setter]`[T]`.

```python
from wybthon import create_signal, flush

count, set_count = create_signal(0)
set_count(5)
count()          # 0: the write is staged
flush()          # automatic in the browser
count()          # 5
set_count(lambda n: n + 1)   # functional update sees staged values
count.peek()     # 5: untracked read of the committed value
```

- **Writes are staged.** The setter records the value; reads keep returning the committed value until the next flush. See [Staged writes](reactivity.md#staged-writes-and-flush-timing).
- **Functional updates** receive the latest staged value, so two `set(lambda n: n + 1)` calls in one handler add two. To store a callable as the value, wrap it: `set_fn(lambda _: my_callable)`.
- **`equals`** decides when observers are notified. The default is an identity fast path followed by `==`; `equals=False` always notifies; a callable `(old, new) -> bool` skips notification when it returns `True` (use `lambda a, b: a is b` for identity-only semantics).
- **Function form.** `create_signal(lambda: a() + b())` returns a *writable derived signal*: it tracks what the function reads, and the setter overrides the value until the next source change.

Signals created in a component body live for the component's lifetime.
There are no hook rules.

## `create_memo`

[`create_memo`][wybthon.create_memo] returns a [`Memo`][wybthon.Memo], a
read-only accessor for a derived value.

```python
from wybthon import create_memo

doubled = create_memo(lambda: count() * 2)
doubled()        # tracked read
doubled.peek()   # untracked read
```

- **Lazy and pull-based.** The body runs when the memo is read after a source changed. A memo that's never read never runs.
- **Glitch-free.** Reading a memo brings its sources current first, so a diamond of memos never observes a half-updated state.
- **Equality short-circuits.** Observers are notified only when the value changed under `equals`.
- **Previous value.** If the body accepts a positional parameter it receives the previous value (`None` on the first run).
- **`lazy=True`** disposes the memo once it loses its last subscriber; **`unobserved=`** runs a callback at that moment (for resource cleanup).
- **Async bodies.** An `async def` body (or an async generator) makes the memo an async computation. See [Async and loading](async-loading.md).

## `create_effect`

[`create_effect`][wybthon.create_effect] creates a side effect that
re-runs when its tracked sources change. Effects run **after the DOM
commit** in each flush, and the first run happens on the next flush,
right after the component that created it has mounted.

The **split form** is recommended: `compute` runs tracked and returns a
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

The **single form** `create_effect(fn)` makes `fn` both the tracking
stage and the side effect. Use [`on_cleanup`][wybthon.on_cleanup] for
per-run teardown. Writing a signal inside it raises
[`WriteInScopeError`][wybthon.WriteInScopeError] in dev mode.

Other options:

- `compute` may accept a positional parameter to receive its previous return value.
- `compute` may be `async def`; awaits suspend the effect without blocking, and reads after an `await` are still tracked.
- `defer=True` skips the first `apply` (tracking still starts).
- `error=handler` receives exceptions from `compute` instead of routing them to the nearest [`Errored`][wybthon.Errored] boundary.
- The returned [`Computation`][wybthon.Computation] has `.dispose()`.

## `create_render_effect`

[`create_render_effect`][wybthon.create_render_effect] takes the same
arguments as `create_effect` but runs in the **render phase**, before the
DOM commit, and its first run happens immediately at creation. Holes
and prop bindings are render effects. Reach for it only when building a
rendering primitive; `create_effect` is right for application code.

## `untrack` and `.peek()`

[`untrack`][wybthon.untrack] runs a function with tracking suppressed.
Every accessor also has `.peek()` for a single untracked read.

```python
from wybthon import create_effect, untrack

create_effect(lambda: (a(), untrack(b)), lambda pair: print(pair))   # depends on a only
count.peek()   # the same idea for one read
```

Both silence the dev-mode top-level-read warning, so they're the
explicit way to seed local state from a prop.

## `on_settled`

[`on_settled`][wybthon.on_settled] runs a callback once the flush that
mounted the current component has committed, so refs are assigned and
the DOM is live. It may return a cleanup that runs on unmount.

```python
from wybthon import Prop, Ref, component, on_settled
from wybthon.html import canvas


@component
def Chart(data: Prop[list[float]]):
    ref = Ref()

    def start():
        handle = draw(ref.current, data.peek())
        return lambda: handle.destroy()

    on_settled(start)
    return canvas(ref=ref)
```

## `on_cleanup`

[`on_cleanup`][wybthon.on_cleanup] registers teardown on the active
scope:

- In a component body: runs when the component unmounts.
- In an effect: runs before each re-run and on disposal.
- In a hole or `For` row: runs when that region is re-evaluated or removed.

It raises `RuntimeError` outside any scope.

## `create_root`, `get_owner`, and `run_with_owner`

[`create_root`][wybthon.create_root] runs a function inside a new,
independent ownership root and hands it a `dispose` callable. Use it for
long-lived reactive work that shouldn't die with a component, such as
global stores.

```python
from wybthon import create_effect, create_root

def setup(dispose):
    create_effect(count, lambda value: print("count", value))
    return dispose


dispose = create_root(setup)
dispose()   # tears the effect down
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

Every read goes through [`Accessor[T]`][wybthon.Accessor]: signal
getters are [`Signal[T]`][wybthon.Signal], memos are `Memo[T]`, and
component parameters are [`Prop[T]`][wybthon.Prop]. Setters are
`Setter[T]`. Annotate function parameters as `Accessor[T]` when they
accept any of these. See the [Typing guide](../guides/typing.md).

## Props helpers

- [`prop(default)`][wybthon.prop] declares a component parameter default with a `Prop[T]` type.
- [`merge(*sources)`][wybthon.merge] merges `Props`, dicts, and zero-arg functions returning dicts into one reactive mapping; later sources win, and `None` is a real value.
- [`omit(source, *keys)`][wybthon.omit] returns a reactive view without the given keys (the replacement for `split_props`).
- [`children(fn)`][wybthon.children] resolves a children prop into a memoized flat list.

```python
from wybthon import merge, omit

attrs = merge({"type": "button"}, rest)
rest_without_class = omit(props, "class_", "style")
```

## `map_array`

[`map_array`][wybthon.map_array] is the engine behind
[`For`][wybthon.For]: it maps a reactive list to rows with a stable
owner scope per row. `keyed` selects how rows are matched, and with it
the callback shape:

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

## `create_selector`

[`create_selector`][wybthon.create_selector] returns
`is_selected(key)`, a tracked boolean that notifies only the row that
was selected and the one that was deselected instead of every row:

```python
from wybthon import create_selector, create_signal

selected, set_selected = create_signal(1)
is_selected = create_selector(selected)

li("Item 2", class_=lambda: "active" if is_selected(2) else None)
```

## Miscellany

- [`create_unique_id`][wybthon.create_unique_id] returns a process-unique string for `id`/`for` pairs.
- [`is_accessor`][wybthon.is_accessor] reports whether a value is a reactive expression (an `Accessor` or a zero-arg function); it's the rule the framework uses to decide what becomes a hole.
- [`flush`][wybthon.flush] settles the graph now. Automatic in the browser; call it in tests.

## Next steps

- Read [Reactivity](reactivity.md) for flush timing and the ownership tree.
- See [Lifecycle and ownership](lifecycle.md) for disposal order.
- Browse the [`reactivity`](../api/reactivity.md) API reference.
