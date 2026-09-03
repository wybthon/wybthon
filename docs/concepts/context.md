# Context

Context passes values down the tree without threading props through
every level. A [`Context`][wybthon.Context] created with
[`create_context`][wybthon.create_context] is **its own provider**: call
it with a value and children to expose that value to every descendant,
and read it with [`use_context`][wybthon.use_context].

```python
from wybthon import component, create_context, use_context
from wybthon.html import div, p

Theme = create_context("light")


@component
def Label():
    theme = use_context(Theme)
    return p("Theme: ", theme)


@component
def App():
    return div(Theme("dark", Label()))   # value first, then children
```

## Providing a value

The context object is callable: `Theme(value, *children)` returns a
provider VNode. Children may be VNodes, component calls, or lists;
anything you'd pass to an element works.

```python
Theme("dark", Header(), Main())
Theme("dark", [Header(), Main()])
```

There's no separate `Provider` component and no `Theme.Provider(...)`
form.

## Reading a value

`use_context(Theme)` walks up the ownership tree from the active scope
and returns the nearest provided value. Because values live on the
ownership tree rather than a render-time stack, it works anywhere an
owner exists: component bodies, effects, memos, holes, and `For` rows.

```python
@component
def Button():
    theme = use_context(Theme)          # read once, in the body
    return button("Hi", class_=lambda: f"btn-{theme}")
```

## Defaults and `ContextNotFoundError`

`create_context(default)` declares a value to return when no provider is
above the reader. Without a default, reading outside a provider raises
[`ContextNotFoundError`][wybthon.ContextNotFoundError]:

```python
from wybthon import ContextNotFoundError, create_context, use_context

Session = create_context(name="Session")   # no default

try:
    use_context(Session)
except ContextNotFoundError:
    ...
```

Pass `name=` for readable diagnostics; it appears in the error message
and the context's `repr`.

## Live values: pass an accessor

`use_context` returns the value **exactly as provided**. A static string
stays a string; a signal or any accessor stays an accessor, so consumers
call it where they need the value and stay reactive without the
provider or the subtree re-mounting:

```python
from wybthon import Accessor, Context, component, create_context, create_signal, use_context
from wybthon.html import button, div

Theme: Context[Accessor[str]] = create_context()


@component
def ThemedButton():
    theme = use_context(Theme)
    return button("Hi", class_=lambda: f"btn-{theme()}")


@component
def App():
    theme, set_theme = create_signal("light")
    toggle = lambda e: set_theme(lambda t: "dark" if t == "light" else "light")
    return div(
        Theme(theme, ThemedButton()),
        button("Toggle", on_click=toggle),
    )
```

Provide a setter alongside the accessor when descendants need to write:

```python
Theme((theme, set_theme), App())

theme, set_theme = use_context(Theme)
```

Passing a plain value is fine when it never changes. Don't pass a
`lambda: theme()` unless you mean to; an accessor already is one.

## How it works: the ownership tree

The provider is a tiny component that stores `value` on its own
[`Owner`][wybthon.Owner]. `use_context` walks parent pointers until it
finds a scope that carries the context:

```
Root owner
└── Component (App)
    └── Provider owner        <- context map: {Theme: value}
        └── Component (Label)
            └── hole scope
                └── render effect   <- use_context(Theme) walks up from here
```

The lookup is a parent-pointer walk with no copying, so cost is
proportional to the depth between reader and provider. Nested providers
for the same context shadow outer ones because the walk finds the
nearest first:

```python
Theme("light",
    Theme("dark", Label()),   # sees "dark"
    Label(),                  # sees "light"
)
```

## Where to call `use_context`

Call it in the component body (or at the top of an effect or memo) and
close over the result. Calling it inside a hole works too, since holes
are owners under the component, but reading once in the body is clearer
and avoids repeating the walk on every re-evaluation. Context values are
also visible inside [`Show`][wybthon.Show], [`For`][wybthon.For],
[`Loading`][wybthon.Loading], and [`Portal`][wybthon.Portal] subtrees,
because those primitives mount their content under the surrounding
owner.

## Next steps

- See the [`context`](../api/context.md) API for `Context`, `create_context`, and `use_context`.
- Read [Lifecycle and ownership](lifecycle.md) for how the ownership tree works.
- Explore [Stores](stores.md) when you need a richer reactive container to share.
