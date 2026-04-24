### Components

Wybthon uses function components exclusively, following the SolidJS model.

!!! tip "Mental model"
    A component body **runs once** during mount. Every prop is a
    **reactive accessor** (a zero-arg callable). Embed an accessor in
    the returned VNode tree to create a *reactive hole* — only that
    node updates when the prop changes. See
    [Primitives](primitives.md#reactive-holes) for the full story.

#### Function components with `@component`

The `@component` decorator turns a function into a Wybthon component.
Declare props as regular Python keyword arguments — defaults and
annotations work as you would expect:

```python
from wybthon import component, p

@component
def Hello(name="world"):
    # ``name`` is a zero-arg getter.  Passing it directly into the tree
    # creates a reactive hole — only the text node updates if the
    # parent passes a new ``name``.
    return p("Hello, ", name, "!")
```

Each parameter is bound to a **reactive accessor**:

* Pass it into the tree (`p("Hello, ", name)`) for an automatic
  reactive hole.
* Call it (`name()`) to read the current value (tracked when called
  inside an effect).
* Wrap it with [`untrack`](primitives.md#untrack) to read once
  without subscribing — useful for seeding local state from a prop.

The body of an `@component` runs **once** per mount.  There is no
re-render: the only things that update later are the holes embedded
in the tree.

```python
from wybthon import button, component, create_signal, div, p, span, untrack

@component
def Counter(initial=0):
    # ``initial`` is a getter; ``untrack`` reads the seed value
    # without subscribing.  ``count`` is the new local signal getter.
    count, set_count = create_signal(untrack(initial))

    return div(
        p("Count: ", span(count)),                       # ← reactive hole
        button("+1", on_click=lambda e: set_count(count() + 1)),
    )
```

`count` is a zero-arg accessor.  When you place it in the VNode
tree, the reconciler wraps it in its own effect so only that text
node updates — the surrounding component body does not re-run.

##### Static or getter — same call site

A child component never has to care whether the parent passed a
constant or a signal — both are unwrapped uniformly:

```python
@component
def Badge(count=0):
    # Works whether the parent passes count=7 or count=my_signal.
    return span("count: ", count)

h(Badge, {"count": 7})         # static value
h(Badge, {"count": my_signal}) # signal accessor
```

Because props are always callable, you can also pass `lambda: a() + b()`
as a prop and the child will re-evaluate it whenever ``a`` or ``b``
changes.

##### Children

`children` is a normal prop — also a reactive accessor.  Most layouts
read children once at setup, so wrap with `untrack`:

```python
from wybthon import component, h3, section, untrack, dynamic

@component
def Card(title="", children=None):
    kids = untrack(children) if callable(children) else children
    if kids is None:
        kids = []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(dynamic(lambda: title())), *kids, class_="card")
```

##### Direct calls (no `h`)

`@component` also enables a sugar form for tree authoring — calling the
component directly with kwargs returns a `VNode`:

```python
Counter(initial=5)                          # → h(Counter, {"initial": 5})
Card("child1", "child2", title="My Card")   # positional args become children
```

The component still works with `h()` as usual:

```python
from wybthon import h
h(Counter, {"initial": 5})
```

##### Proxy mode (single positional parameter)

`@component` chooses one of two binding modes by inspecting the
decorated function's signature:

| Signature shape                                          | Mode             | What the parameter receives           |
|----------------------------------------------------------|------------------|---------------------------------------|
| zero args, or any kw-args / defaults / `**kwargs`         | named-accessor   | one reactive accessor per declared name |
| **exactly one** positional-only or positional-or-keyword parameter, **no default**, no `*args`/`**kwargs` | **proxy mode**   | the entire `ReactiveProps` proxy      |

In other words: if your component looks like `def Foo(props):` (one
bare positional parameter), you get the proxy.  Anything else —
`def Foo(name="world")`, `def Foo(name, age=0)`, `def Foo(**props)`,
`def Foo()` — uses the named-accessor mode.

Proxy mode is the right choice for **generic wrappers** that don't
know their props' names ahead of time:

```python
from wybthon import component, dynamic, p

@component
def DumpProps(props):
    # ``props`` is the ReactiveProps proxy.
    # ``props.x`` → reactive accessor; ``props.x()`` → current value.
    return p(dynamic(lambda: ", ".join(f"{k}={props.value(k)!r}" for k in props)))
```

For ordinary components, prefer named accessors — they're easier to
read, type, and refactor:

```python
@component
def Hello(name="world"):    # ← named accessor: ``name`` is a getter
    return p("Hello, ", name)

@component
def Hello(props):           # ← proxy mode: ``props.name`` is the getter
    return p("Hello, ", props.name)
```

If you're in named-accessor mode and still need the proxy (for
example, to iterate keys or forward unknown props), call
[`get_props`][wybthon.get_props] from inside the body.

#### Component ownership and lifecycle

Each component instance gets a `_ComponentContext` (a subclass of
`Owner`) that participates in the reactive **ownership tree**.  This
context is the parent owner for everything created during the
component's setup phase, including the per-hole effects.

```
_ComponentContext (Counter)       ← created when Counter mounts (body runs once)
├── setup effect                  ← child of the component context (survives the body)
├── on_cleanup callback           ← registered on the component context
└── reactive holes                ← each hole has its own effect, also a child
    ├── span(count)               ← effect that updates one text node
    └── ...
```

**Setup effects** (created in the component body, before `return`) and
**reactive hole effects** are both owned by the `_ComponentContext`.
They are disposed when the component unmounts.

When a hole returns a sub-tree containing further effects (for
example a hole returning a VNode that contains its own holes), the
inner effects are owned by the hole's effect.  When the hole re-runs,
those inner effects are disposed first (so their `on_cleanup`
callbacks fire), then re-created on the next evaluation.

This distinction is automatic — no special API is needed.  The ownership
tree tracks which owner is active at the time `create_effect` or
`create_memo` is called.

```python
from wybthon import component, create_effect, create_signal, dynamic, li, ul, untrack

@component
def SearchResults(initial=""):
    # ``initial`` is a getter; ``untrack`` snapshots the seed value
    # without subscribing (and silences the destructured-prop warning).
    query, set_query = create_signal(untrack(initial))
    results, set_results = create_signal([])

    create_effect(lambda: print("query changed:", query()))

    return ul(
        dynamic(lambda: [li(r) for r in results()]),
    )
```

When a component unmounts, the reconciler calls `dispose()` on its
`_ComponentContext`, which walks the tree depth-first: hole effects,
setup effects, and cleanup callbacks are all torn down automatically.

#### Dev-mode warnings

When running outside the browser (or with `WYBTHON_DEV=1`), the
component decorator catches the most common reactive footguns:

* **Destructured prop access during setup.** Calling a prop accessor
  inside the component body without wrapping in `untrack` warns once
  per component — you almost always want to either pass the accessor
  directly into the tree (creating a hole) or `untrack(prop)` for a
  one-shot snapshot.
* **`each=plain_list`** in `For` / `Index` warns that the list will
  not update reactively.  Pass a signal accessor instead.

Warnings are silenced when the offending read happens inside an
`untrack(...)` call, so you can opt out explicitly when the static
behaviour is intentional.

#### Fragment

Use `Fragment` to group children without adding a visible wrapper element. The reconciler mounts children directly in the parent and uses **empty comment nodes** as start/end markers (not a `display: contents` wrapper), so fragments do not pollute the DOM or break CSS selectors that expect a certain element structure.

```python
from wybthon import Fragment, h1, p

@component
def PageContent():
    return Fragment(
        h1("Title"),
        p("Body text here."),
    )
```

#### `memo`

Wrap a function component with `memo` to skip re-mounts when its props
have not changed (shallow identity comparison by default):

```python
from wybthon import component, memo, h

@component
def ExpensiveList(items=None):
    its = items() or []
    return h("ul", {}, *[h("li", {}, str(i)) for i in its])

MemoList = memo(ExpensiveList)
```

Pass a custom comparison function for deeper control:

```python
MemoList = memo(ExpensiveList, are_props_equal=lambda old, new: old["items"] == new["items"])
```

!!! note "When `memo` actually helps"
    Because props are reactive and the body runs once, `memo` is only
    useful when you want to **skip re-mounting** the component on a
    prop change (for example, an expensive setup phase). Most ordinary
    components do not need it.

#### `forward_ref`

Use `forward_ref` to create a component that can receive a `ref` prop
and forward it to a child element:

```python
from wybthon import forward_ref, h

def _render(props, ref):
    return h("input", {"type": "text", "ref": ref, "class": "fancy-input"})

FancyInput = forward_ref(_render)

# Usage: h(FancyInput, {"ref": my_ref})
```

The wrapped function receives `(props, ref)` instead of `(props,)`,
and `ref` is **stripped** from props (matching React's `forwardRef`
semantics).  When no `ref` is provided, `ref` is `None`.

#### `create_portal`

Use `create_portal` to render children into a DOM node outside the
parent component's hierarchy — ideal for modals, tooltips, and overlays:

```python
from wybthon import component, create_portal, h

@component
def Modal():
    return h("div", {},
        h("p", {}, "Page content"),
        create_portal(
            h("div", {"class": "modal"}, "I appear in #modal-root!"),
            "#modal-root",
        ),
    )
```

The second argument is an `Element` or a CSS selector string.

#### Flow control

Wybthon provides SolidJS-style **reactive** flow control components.
Each creates its own reactive scope — only the relevant subtree
re-renders when the tracked condition or list changes.

Pass **getters** (signal accessors or lambdas) for conditions, lists,
children, and fallbacks so reads happen inside the flow control's own
scope rather than the parent's:

```python
from wybthon import Show, For, Index, Switch, Match

# Conditional rendering — keyed scope disposes on transition
Show(when=is_logged_in,
     children=lambda: p("Welcome!"),
     fallback=lambda: p("Please log in"))

# List rendering — per-item reactive scopes (keyed by identity)
# Item and index getters are signal-backed
For(each=items,
    children=lambda item, idx: li(item(), key=idx()))

# Index-based rendering — per-index reactive scopes
# Item getter updates in place when the value at that position changes
Index(each=items,
      children=lambda item, idx: li(f"[{idx}] {item()}"))

# Multi-branch matching (reactive)
Switch(
    Match(when=lambda: status() == "loading",
          children=lambda: p("Loading...")),
    Match(when=lambda: status() == "error",
          children=lambda: p("Error!")),
    Match(when=lambda: status() == "ready",
          children=lambda: p("Ready")),
    fallback=lambda: p("Unknown"),
)
```

`each=` requires a signal accessor (or other reactive getter) to track
list updates; passing a plain Python `list` triggers a dev warning.

See the guide for recommended patterns around props, state, children, cleanup, and context:

- Guide: [Authoring Patterns](../guides/authoring-patterns.md)
- Example: [Authoring Patterns Example](../examples/authoring-patterns.md)

## Next steps

- Read [Mental model](mental-model.md) and [Lifecycle and Ownership](lifecycle.md).
- Browse the [`component`][wybthon.component] API reference.
- Explore [Flow control][wybthon.Show] for `Show`, `For`, `Switch`, and friends.
