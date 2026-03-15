### Async Fetch

Fetch data with `create_resource`.

```python
from wybthon import Suspense, h, create_resource

async def load_data(signal=None):
    # e.g., using js.fetch with AbortSignal
    return {"message": "hello"}

res = create_resource(load_data)

def Content(props):
    if res.error.get():
        return h("div", {}, f"Error: {res.error.get()}")
    return h("pre", {}, str(res.data.get()))

View = lambda props: h(
    Suspense,
    {"resource": res, "fallback": h("div", {}, "Loading..."), "keep_previous": True},
    Content({}),
)
```

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
