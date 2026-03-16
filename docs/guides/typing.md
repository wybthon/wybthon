### Typing

The codebase uses type hints and aims for clarity over cleverness.

Guidelines:

- Prefer precise types on public APIs; avoid `Any`.
- Use `Optional[...]` where values can be absent.
- In Pyodide/browser interop, tolerate `Any` at boundaries but narrow types internally.

#### mypy configuration

- Config is in `mypy.ini` targeting Python 3.9. Browser shims (e.g., `js`, `pyodide`) are marked as `ignore_missing_imports`.
- Run mypy against `src`, `tests`, `examples`, `bench` per config.

#### Examples

- Reactivity API
  - `create_signal(value: T) -> tuple[Callable[[], T], Callable[[T], None]]`
  - `create_memo(fn: Callable[[], T]) -> Callable[[], T]`
  - `create_effect(fn: Callable[[], Any]) -> Computation`
  - `create_resource(fetcher: Callable[..., Awaitable[R]]) -> Resource[R]`

```python
from typing import Awaitable
from wybthon import create_signal, create_memo, create_effect, create_resource

count, set_count = create_signal(0)
double = create_memo(lambda: count() * 2)

def log() -> None:
    _ = double()  # subscribes

c = create_effect(log)  # Computation
c.dispose()             # stop updates

async def fetch_user() -> dict:
    return {"name": "Ada"}

res = create_resource(cast(Callable[[], Awaitable[dict]], fetch_user))
```

- Component typing
  - Function components: `def MyComp(props: Dict[str, Any]) -> VNode`

```python
from typing import Any, Dict
from wybthon import h, VNode

def HelloFn(props: Dict[str, Any]) -> VNode:
    return h("div", {}, f"Hello {props.get('name', 'world')}")
```

- Router types
  - `Route(path: str, component: Union[Callable[[Dict[str, Any]], VNode], type])`
  - `navigate(path: str, replace: bool = False) -> None`

```python
from typing import Any, Dict
from wybthon import Route, Router, h

routes = [
    Route(path="/", component=lambda _props: h("div", {}, "Home")),
]
```
