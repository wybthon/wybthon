### wybthon.loading

::: wybthon.loading

#### What's in this module

[`Loading`][wybthon.Loading] is the async boundary. Any read of an async
computation under it that raises [`NotReadyError`][wybthon.NotReadyError]
registers that computation with the boundary, and the boundary shows
its fallback until every registered computation has a first value.
Content **stays mounted** the whole time, parked off-document, so async
memos created inside it keep running and nothing is torn down.
Revalidations never re-trigger the boundary: a memo with a value keeps
serving it (stale-while-revalidate), and [`is_pending`][wybthon.is_pending]
is the tool for inline refresh hints.

[`Reveal`][wybthon.Reveal] coordinates several `Loading` boundaries
beneath it: the order their contents appear and how many fallbacks show
at once.

| Name | Description |
| --- | --- |
| [`Loading`][wybthon.Loading] | `Loading(children, *, fallback=None, on=None)`; `children` is a VNode, callable, or list; `on` is an accessor or list of accessors to wait for as well. |
| [`Reveal`][wybthon.Reveal] | `Reveal(children, *, order="forwards", tail="visible")`; `order` is `"forwards"`, `"backwards"`, or `"together"`; `tail` is `"visible"`, `"collapsed"`, or `"hidden"`. |

```python
from wybthon import Loading, Prop, Reveal, component, create_memo, div, is_pending, p, span

@component
def UserCard(user_id: Prop[int]):
    async def load_user():
        uid = user_id()                    # tracked: refetches when it changes
        return await fetch_json(f"/api/users/{uid}")

    user = create_memo(load_user)
    return Loading(
        lambda: div(
            p(lambda: user()["name"]),
            span(lambda: "Refreshing..." if is_pending(user) else ""),
        ),
        fallback=lambda: p("Loading..."),
    )

@component
def Dashboard(settings: Prop[object]):
    return Reveal(
        [
            Loading(UserCard(user_id=1), fallback=p("Loading user...")),
            Loading(Activity(), fallback=p("Loading activity..."), on=settings),
        ],
        order="forwards",
        tail="collapsed",
    )
```

- `on=` makes the boundary wait for specific accessors even if the
  children never read them, so a layout doesn't partially render while a
  critical query is in flight.
- With `order="forwards"` contents reveal top to bottom, each waiting for
  the ones before it; `"backwards"` reverses that; `"together"` reveals
  all at once. `tail="visible"` shows every pending fallback,
  `"collapsed"` only the next one in reveal order, `"hidden"` none.
- Every boundary's content mounts immediately, so all of them load in
  parallel; `order` only controls when each is revealed. Boundaries
  nested inside another boundary coordinate with that boundary, not with
  the outer `Reveal`.

#### See also

- [`create_memo`][wybthon.create_memo] (async memos), [`latest`][wybthon.latest], [`resolve`][wybthon.resolve], [`refresh`][wybthon.refresh]
- [Error boundary](error_boundary.md): `Errored` for the failure side
- [Lazy loading](lazy.md): lazy components suspend into the nearest `Loading`
- [Concepts: Async and loading](../concepts/async-loading.md)
- [Examples: Async fetch](../examples/fetch.md)
