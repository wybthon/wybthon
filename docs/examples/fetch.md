### Async Fetch

Fetch data with `create_resource`.

```python
from wybthon import Suspense, component, dynamic, h, create_resource

async def load_data(signal=None):
    # e.g., using js.fetch with AbortSignal
    return {"message": "hello"}

res = create_resource(load_data)

@component
def Content():
    def render():
        if res.error:
            return h("div", {}, f"Error: {res.error}")
        return h("pre", {}, str(res()))

    return dynamic(render)

view = Suspense(
    fallback=h("div", {}, "Loading..."),
    children=lambda: h(Content, {}),
)
```

Reading `res()` inside the boundary is what wires it to `Suspense`;
while the resource is pending, the boundary shows the fallback
automatically.

#### With source signal

Automatically refetch when a source signal changes:

```python
from wybthon import create_resource, create_signal

user_id, set_user_id = create_signal(1)

async def load_user(signal=None):
    resp = await js.fetch(f"/api/users/{user_id()}")
    return await resp.json()

# Changing user_id triggers a refetch
res = create_resource(user_id, load_user)
```

## Next steps

- Read [Suspense and Lazy Loading](../concepts/suspense-lazy.md).
- See [`create_resource`][wybthon.create_resource] for the resource lifecycle.
- Browse the [Error boundary example](errors.md) for failure-state UI.
