# Error handling

Catch errors raised while rendering with [`Errored`][wybthon.Errored], show a fallback, and recover with a reset callback or automatically when a route changes.

```python
from wybthon import Errored, Prop, Props, button, component, create_signal, div, p, prop, render
from wybthon.router import current_path


class RiskyPanelProps(Props):
    should_fail: Prop[bool] = prop(default=False)


@component
def RiskyPanel(props: RiskyPanelProps):
    # A hole that raises routes the error to the nearest Errored boundary.
    def body():
        if props.should_fail():
            raise RuntimeError("the panel exploded")
        return "Everything is fine."

    return p(body)


def fallback(err, reset):
    return div(
        p("Caught: ", lambda: str(err())),
        button("Retry", on_click=reset),
        style={"color": "crimson"},
    )


@component
def App():
    fail, set_fail = create_signal(False)

    return div(
        button("Toggle failure", on_click=lambda: set_fail(lambda v: not v)),
        Errored(
            lambda: RiskyPanel(should_fail=fail),
            fallback=fallback,
            on_error=lambda err: print("logged:", err),
            reset_on=current_path,
        ),
    )


render(App(), "#app")
```

## How it works

- `Errored` installs an error handler on its owner scope. Errors raised in a descendant hole, component body, effect, or async memo route to the nearest boundary; sibling trees are untouched.
- `fallback` may be a VNode, a string, or a callable. A callable receives `(err, reset)` (or just `(err)`). `err` is an accessor for the caught exception, as in Solid 2.0, so read it with `err()` inside a hole. Calling `reset()` clears the error and re-renders the children; it takes no arguments, so it works directly as a click handler.
- `on_error` is a plain callback for logging or reporting. It receives the exception itself.
- `reset_on` is an accessor whose change clears the error automatically. Passing [`current_path`][wybthon.router.current_path] from `wybthon.router` resets the boundary on every navigation, which is the usual behavior for a page-level boundary.
- Boundaries also heal on their own: the boundary remembers which reactive inputs the failing computation read, so toggling the failure off re-renders `RiskyPanel` without a click on "Retry."

## Errors in async data

An async memo that rejects raises into the boundary as well. Nest `Errored` outside `Loading` so the fallback replaces the pending UI:

```python
from wybthon import Errored, Loading, button, component, create_memo, div, p


async def load_profile():
    response = await fetch_json("/api/profile")
    if response is None:
        raise LookupError("profile not found")
    return response


@component
def Profile():
    profile = create_memo(load_profile)
    return Errored(
        lambda: Loading(lambda: p(lambda: profile()["name"]), fallback=p("Loading...")),
        fallback=lambda err, reset: div(p(lambda: str(err())), button("Try again", on_click=reset)),
    )
```

## Errors in effects

[`create_effect`][wybthon.create_effect] accepts an `error=` handler that receives exceptions from its compute stage instead of routing them to the boundary:

```python
from wybthon import create_effect

create_effect(
    lambda: parse(raw_input()),
    lambda parsed: show(parsed),
    error=lambda exc: print("parse failed:", exc),
)
```

Event handlers run outside rendering, so an exception in an `on_click` handler is logged to the console and doesn't involve any boundary; the UI stays intact.

## Next steps

- Read the [Error Boundaries](../concepts/error-boundaries.md) concept page.
- See the [`error_boundary`][wybthon.error_boundary] API reference.
- Combine with [Loading](../concepts/async-loading.md) for async failure handling.
