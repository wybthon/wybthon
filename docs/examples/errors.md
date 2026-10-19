# Error handling

Catch errors raised while rendering with [`Errored`][wybthon.Errored], show a fallback, and recover with a reset callback or automatically when a route changes.

```python
from wybthon import Errored, Prop, Props, component, create_signal, html, prop, render
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

    return html(t"<p>{body}</p>")


def fallback(err, reset):
    def message():
        return f"Caught: {err()}"

    return html(t"""
      <div style="color: crimson">
        <p>{message}</p>
        <button onclick={reset}>Retry</button>
      </div>
    """)


def log_error(err):
    print("logged:", err)


@component
def App():
    fail, set_fail = create_signal(False)

    def toggle():
        set_fail(lambda v: not v)

    return html(t"""
      <div>
        <button onclick={toggle}>Toggle failure</button>
        {Errored(RiskyPanel(should_fail=fail), fallback=fallback, on_error=log_error, reset_on=current_path)}
      </div>
    """)


render(App(), "#app")
```

## How it works

- `Errored` installs an error handler on its owner scope. Errors raised in a descendant hole, component body, effect, or async memo route to the nearest boundary; sibling trees are untouched.
- Its children can be a node, as here: `RiskyPanel(...)` doesn't run until the boundary mounts it, so there's no need to wrap it in a lambda.
- `fallback` may be a node, a string, or a callable. A callable receives `(err, reset)` (or just `(err)`). `err` is an accessor for the caught exception, as in Solid 2.0, so read it inside a hole: `message` is a function placed in the template. Calling `reset()` clears the error and re-renders the children; it takes no arguments, so it works directly as a click handler.
- `on_error` is a plain callback for logging or reporting. It receives the exception itself.
- `reset_on` is an accessor whose change clears the error automatically. Passing [`current_path`][wybthon.router.current_path] from `wybthon.router` resets the boundary on every navigation, which is the usual behavior for a page-level boundary.
- Boundaries also heal on their own: the boundary remembers which reactive inputs the failing computation read, so toggling the failure off re-renders `RiskyPanel` without a click on "Retry."

## Errors in async data

An async memo that rejects raises into the boundary as well. Nest `Errored` outside `Loading` so the fallback replaces the pending UI:

```python
from wybthon import Errored, Loading, component, create_memo, html


async def load_profile():
    response = await fetch_json("/api/profile")
    if response is None:
        raise LookupError("profile not found")
    return response


def profile_failed(err, reset):
    return html(t"""
      <div>
        <p>{(lambda: str(err()))}</p>
        <button onclick={reset}>Try again</button>
      </div>
    """)


@component
def Profile():
    profile = create_memo(load_profile)

    def name():
        return profile()["name"]

    return Errored(
        Loading(html(t"<p>{name}</p>"), fallback=html(t"<p>Loading...</p>")),
        fallback=profile_failed,
    )
```

The memo keeps its error until it runs again, so to retry the request itself, call [`refresh`][wybthon.refresh] on it before `reset()`, as the [Async fetch example](fetch.md) does.

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

Event handlers run outside rendering, so an exception in an `onclick` handler is logged to the console and doesn't involve any boundary; the UI stays intact.

## Next steps

- Read the [Error Boundaries](../concepts/error-boundaries.md) concept page.
- See the [`error_boundary`][wybthon.error_boundary] API reference.
- Combine with [Loading](../concepts/async-loading.md) for async failure handling.
