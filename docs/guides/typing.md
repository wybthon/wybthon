# Typing

Wybthon ships with type hints (`py.typed`) and uses Python 3.12's PEP 695 syntax for generics: `class Accessor[T]`, `def create_signal[T](...)`, `type Validator = ...`. This guide covers the types you'll write in application code and how the project runs mypy.

## The core types

| Type | What it is | Where you get one |
| --- | --- | --- |
| [`Accessor[T]`][wybthon.Accessor] | A zero-argument callable returning `T`, with `.peek()`. The base of every reactive read. | Any signal getter, memo, or prop. Use it in signatures that accept "something reactive". |
| [`Setter[T]`][wybthon.Setter] | The write half of a signal: accepts `T` or `(T) -> T` and returns the staged value. | `create_signal` |
| [`Signal[T]`][wybthon.Signal] | The concrete accessor returned by `create_signal` for a plain value. | `create_signal` (usually typed as `Accessor[T]`) |
| [`Memo[T]`][wybthon.Memo] | A read-only derived accessor. | `create_memo`, `children` |
| [`Prop[T]`][wybthon.Prop] | The accessor bound to one component parameter. | Every parameter of a `@component` function |
| [`Props`][wybthon.Props] | A read-only mapping of name to `Prop`. | Components that declare a single `props` parameter |
| [`Computation`][wybthon.Computation] | An effect handle with `.dispose()`. | `create_effect`, `create_render_effect` |
| [`Action`][wybthon.Action] | A callable mutation with a `.pending` accessor. | `action` |
| [`Context[T]`][wybthon.Context] | A callable context token. | `create_context` |
| [`VNode`][wybthon.VNode] | The virtual node every helper and component call returns. | `div(...)`, `h(...)`, `MyComponent(...)` |
| [`Field[T]`][wybthon.Field], [`Validator`][wybthon.Validator] | Form field state; a `(value) -> str | None` validator. | `form_state`, `required`, and friends |

## Signals and memos

```python
from wybthon import Accessor, Computation, Memo, Setter, create_effect, create_memo, create_signal, flush

count: Accessor[int]
set_count: Setter[int]
count, set_count = create_signal(0)

doubled: Memo[int] = create_memo(lambda: count() * 2)


def log(value: int, prev: int | None) -> None:
    print(prev, "->", value)


effect: Computation = create_effect(doubled, log)
set_count(1)
flush()
effect.dispose()


async def fetch_user() -> dict[str, str]:
    return {"name": "Ada"}


user: Memo[dict[str, str]] = create_memo(fetch_user)   # async memo; user() -> dict once resolved
```

Signatures worth knowing:

- `create_signal(value: T, *, equals=..., name=None) -> tuple[Accessor[T], Setter[T]]`. `equals` is the default policy, `False`, or `(old, new) -> bool`.
- `create_memo(fn: Callable[..., T], *, equals=..., lazy=False, unobserved=None, name=None) -> Memo[T]`. When `fn` is `async def`, annotate it as returning `Awaitable[T]`; the memo's read type is still `T`.
- `create_effect(compute, apply=None, *, defer=False, error=None) -> Computation`. `apply` receives `(value, prev)` or `(value,)` and may return a cleanup callable.

## Components and props

Annotate each parameter as `Prop[T]` and declare its default with [`prop`][wybthon.prop], which has the type `Prop[T]`. A plain default (`count=0`) works at runtime but is a type mismatch against `Prop[int]`.

```python
from wybthon import Prop, VNode, component, h2, prop


@component
def Hello(name: Prop[str] = prop("world"), excited: Prop[bool] = prop(False)) -> VNode:
    return h2("Hello, ", name, lambda: "!" if excited() else ".")
```

Callers pass `T` or `Accessor[T]` for a `Prop[T]` parameter; the [`Component`][wybthon.Component] object's `__call__` accepts `**props: Any`, so mypy doesn't check call sites against the signature. Keep the prop types on the definition for documentation and for the body.

For `**rest`, annotate as `**rest: Prop[Any]`; for a whole-mapping component, annotate the single parameter as `Props`:

```python
from typing import Any

from wybthon import Prop, Props, VNode, button, component, div, merge, prop


@component
def Button(variant: Prop[str] = prop("solid"), **rest: Prop[Any]) -> VNode:
    return button(**merge({"type": "button"}, rest), class_=lambda: f"btn-{variant()}")


@component
def Panel(props: Props) -> VNode:
    return div(props.children, class_=props.class_)
```

Component return types are `VNode` in the common case. A body may also return `str`, `list`, `None`, or an accessor; use `Any` for those.

## Context

`create_context` is generic over the provided value. Declare the type when the value is an accessor so `use_context` returns something you can call:

```python
from wybthon import Accessor, Context, create_context, create_signal, use_context

Theme: Context[Accessor[str]] = create_context()

theme, set_theme = create_signal("light")
provider = Theme(theme, "...")          # provider VNode

current: Accessor[str] = use_context(Theme)
```

## Router and forms

```python
from wybthon import Field, Prop, Route, VNode, Validator, component, form_state, h2, required


@component
def User(params: Prop[dict[str, str]], query: Prop[dict[str, str]]) -> VNode:
    return h2("User ", lambda: params()["id"])


routes: list[Route] = [Route("/users/:id", User)]

fields: dict[str, Field[str]] = form_state({"name": ""})
rules: dict[str, list[Validator]] = {"name": [required()]}
```

`Route` is a dataclass: `Route(path: str, component: Any, children: list[Route])`, with `children` defaulting to an empty list. `navigate(path: str, *, replace: bool = False) -> None`.

## Stores

Store proxies are dynamic (attribute and item access resolve at runtime), so they're typed as `Any`. Wrap access in small typed functions when you want checking:

```python
from wybthon import create_store, snapshot

store, set_store = create_store({"count": 0, "user": {"name": "Ada"}})


def user_name() -> str:
    return str(store.user.name)


def data() -> dict[str, object]:
    return dict(snapshot(store))
```

## mypy configuration

The project's `mypy.ini` targets Python 3.12 and checks `src`, `tests`, and `benchmarks`:

```ini
[mypy]
python_version = 3.12
ignore_missing_imports = True
warn_redundant_casts = True
warn_unused_ignores = True
warn_return_any = False
strict_optional = False
pretty = True
files = src, tests, benchmarks
exclude = (?x)(^tests/e2e/app/)

[mypy-js]
ignore_missing_imports = True
```

- Browser shims (`js`, `pyodide`) are unavailable in CPython, so missing imports are ignored.
- The E2E fixture app under `tests/e2e/app/` is Pyodide-runtime code with absolute `app.*` imports and is excluded.
- `strict_optional` is off, which matches the framework's convention of `None` defaults for optional props.

Run it with `uv run mypy` from the repository root. For your own app, the same settings are a reasonable starting point; add `strict = True` if you want mypy to insist on annotations everywhere.

## Guidelines

- Prefer precise types on public APIs; avoid `Any` except at the Pyodide boundary, where JS proxies are untyped.
- Use `X | None` rather than `Optional[X]`, and builtin generics (`list[str]`, `dict[str, int]`).
- Type parameters that accept any reactive read as `Accessor[T]`; type component parameters as `Prop[T]`.
- In event handlers, annotate the argument as [`DomEvent`][wybthon.DomEvent] to get completions for `e.target.value`, `e.key`, and `e.prevent_default()`.

## Next steps

- See the [Style guide](../meta/style-guide.md) for the project's docstring conventions.
- Browse the [`reactivity`][wybthon.reactivity] API for type-annotated public symbols.
- Read the [Contributing guide](../meta/contributing.md) for the local lint and typecheck workflow.
