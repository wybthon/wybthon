# Error boundaries

[`Errored`][wybthon.Errored] catches errors raised while rendering its
subtree and shows a fallback in its place, leaving sibling trees
untouched. It's the recommended way to surface unexpected errors
without crashing the whole app.

```python
from wybthon import Errored, component
from wybthon.html import button, div, p


@component
def Failing():
    raise RuntimeError("boom")


def fallback(err, reset):
    return div(
        p(f"Oops: {err}"),
        button("Try again", on_click=lambda e: reset()),
        class_="error",
    )


view = Errored(lambda: Failing(), fallback=fallback)
```

`children` may be a VNode, a zero-arg callable, or a list of either.
Passing a callable defers building the subtree until the boundary
mounts, which is what you want when the children can raise.

## What gets caught

The boundary installs an error handler on its owner scope. Errors from
any of these route to the nearest enclosing boundary:

- A component body raising during mount.
- A hole's expression or a reactive prop binding raising when it (re-)evaluates.
- An effect's compute stage raising, unless the effect has its own `error=` handler.
- An async memo rejecting: the error is stored and re-raised when the memo is read, so it surfaces in the hole that reads it.
- An [`action`][wybthon.action] raising: routed to the boundary that was active when the action was called, and re-raised to the awaiter.

The nearest boundary wins. An inner `Errored` handles errors from its
own subtree; only errors outside it reach the outer one:

```python
Errored(
    lambda: div(
        Sidebar(),
        Errored(lambda: RiskyPanel(), fallback=lambda err: p("Panel failed")),
    ),
    fallback=lambda err: p("Page failed"),
)
```

## Fallback shapes

`fallback` may be:

- a `VNode` or a string, shown as is;
- a callable `(error) -> VNode`;
- a callable `(error, reset) -> VNode`, where `reset()` clears the error and re-renders the children;
- omitted, in which case the boundary renders the text "Something went wrong."

A callable fallback runs each time an error is caught, so it can inspect
the exception:

```python
def describe(err, reset):
    if isinstance(err, PermissionError):
        return p("You don't have access to this.")
    return div(p(str(err)), button("Retry", on_click=lambda e: reset()))
```

## Resetting

Call the `reset` argument from the fallback, or pass `reset_on=`: an
accessor (or plain value) whose change clears the current error
automatically. Coupling a boundary to the current route is the usual
pattern, so navigating away from a broken page recovers on its own:

```python
from wybthon import Errored, current_path

Errored(lambda: Outlet(), fallback=lambda err: p("This page failed"), reset_on=current_path)
```

Resetting re-renders the children. If the cause hasn't been fixed, the
error is caught again and the fallback returns.

### Automatic healing

A boundary also resets on its own when any **input the failing
computation read** changes. The boundary records the signals behind
the memo or hole that raised (the `user_id` a fetch read, the store
path a hole formatted) and watches them; a change to one of them is a
new situation, so the boundary re-renders the children without you
wiring `reset_on=`. A fetch that failed for user 3 heals when the user
picks user 4, and an async memo that errored heals when its inputs
change and the retry succeeds. Explicit `reset()` and `reset_on=` still
work for causes the graph can't see, such as a network that came back.

## Observing errors with `on_error`

Pass `on_error=` to be notified when the boundary catches something, for
logging or monitoring. It runs in addition to showing the fallback:

```python
Errored(lambda: Dashboard(), fallback="Dashboard unavailable", on_error=report_to_monitoring)
```

## Effects with their own handler

[`create_effect`][wybthon.create_effect] accepts `error=`. Exceptions
raised by the compute stage (sync or async) go to that handler instead
of the nearest boundary, so a failing background effect doesn't take
down the UI around it:

```python
from wybthon import create_effect

create_effect(
    lambda: save_draft(draft()),
    lambda result: set_status("saved"),
    error=lambda exc: set_status(f"save failed: {exc}"),
)
```

## Event handlers are not routed

Like SolidJS, Wybthon runs event handlers outside rendering. An
exception in an `on_click` handler is logged to the console (with a
traceback in dev mode); the boundary isn't involved and the UI stays
intact. Handle expected failures inside the handler, or move the work
into an [`action`][wybthon.action], whose errors *are* routed to the
boundary captured at call time.

## Pairing with `Loading`

`Errored` handles errors; [`Loading`][wybthon.Loading] handles
not-ready state. Wrap async regions with both, `Errored` on the outside
so a rejected fetch inside the loading content still has a fallback:

```python
from wybthon import Errored, Loading
from wybthon.html import p

Errored(
    lambda: Loading(lambda: UserCard(), fallback=p("Loading...")),
    fallback=lambda err, reset: div(p(f"Could not load: {err}"), button("Retry", on_click=lambda e: reset())),
)
```

## Next steps

- See the [`error_boundary`](../api/error_boundary.md) API reference.
- Read [Async and loading](async-loading.md) for async error handling.
- Walk through the [Error boundary example](../examples/errors.md).
