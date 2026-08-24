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
  - `create_signal(value: T, *, equals: Any = ...) -> tuple[Callable[[], T], Callable[[Union[T, Callable[[T], T]]], T]]`. The setter accepts a new value or an updater function and returns the stored value. `equals` is optional: default value equality (`==`) with identity fast-path, `True` is equivalent, `False` to always notify, or `(old, new) -> bool` "same value" predicate (use `equals=lambda a, b: a is b` for SolidJS-style identity-only semantics).
  - `create_memo(fn: Callable[[], T]) -> Callable[[], T]`. The body may also be `async def` (an async memo); annotate it `Callable[[], Awaitable[T]]` and the getter still returns `T`.
  - `create_effect(fn: Callable[..., Any], apply: Optional[Callable[..., Any]] = None) -> Computation`. The split form passes `fn`'s return value to the untracked `apply` phase.
  - The `Signal[T]` and `Computed[T]` classes remain part of the public surface for type hints (for example, `Computed[int]` for a memoized value), even though you normally construct via `create_signal` and `create_memo`.

```python
from wybthon import create_effect, create_memo, create_signal, flush

count, set_count = create_signal(0)
double = create_memo(lambda: count() * 2)

def log() -> None:
    _ = double()  # subscribes

c = create_effect(log)  # Computation
set_count(1)
flush()                 # settle scheduled effects
c.dispose()             # stop updates

async def fetch_user() -> dict:
    return {"name": "Ada"}

user = create_memo(fetch_user)  # async memo; user() -> dict once resolved
```

- Component typing
  - The `@component` decorator binds each parameter to a reactive
    accessor: ``Callable[[], T]``.  Annotate the parameter with the
    underlying value type; Wybthon's machinery handles the wrapping.

```python
from wybthon import VNode, component, h2

@component
def Hello(name: str = "world") -> VNode:
    # ``name`` is a Callable[[], str] at runtime; type it as ``str`` for
    # readability of the public API.
    return h2("Hello, ", name, "!")
```

- Router types
  - `Route(path: str, component: Union[Callable[[Dict[str, Any]], VNode], type])`
  - `navigate(path: str, replace: bool = False) -> None`

```python
from wybthon import Route, component, h2

@component
def HomePage():
    return h2("Home")

routes = [
    Route(path="/", component=HomePage),
]
```

## Next steps

- See the [Style guide](../meta/style-guide.md) for the project's docstring conventions.
- Browse the [`reactivity`][wybthon.reactivity] API for type-annotated public symbols.
- Read the [Contributing guide](../meta/contributing.md) for the local lint/typecheck workflow.
