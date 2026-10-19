# Typing

Wybthon requires Python 3.14. Its accessors, components, actions, and stores carry type information that both pyright (including Pylance) and mypy understand with no plugin or extra configuration.

## Component props

Components declare their inputs on a [`Props`][wybthon.Props] subclass. `Props` is a [PEP 681](https://peps.python.org/pep-0681/) `dataclass_transform` base, so a type checker treats each props class as a keyword-only constructor and checks every component call against it:

```python
from collections.abc import Callable

from wybthon import Accessor, Prop, Props, VNode, component, create_signal, html, prop


class GreetingProps(Props):
    name: Prop[str]
    copies: Prop[int] = prop(default=1)
    on_wave: Callable[[], None] | None = None


@component
def Greeting(props: GreetingProps) -> VNode:
    label: Accessor[str] = props.name

    def text() -> str:
        return label() * props.copies()

    return html(t"<p>{text}</p>")


name, set_name = create_signal("Ada")
Greeting(name="Ada")
Greeting(name=name, copies=2)
Greeting(name=lambda: "Grace", on_wave=lambda: print("hi"))
```

- A `Prop[T]` field accepts a plain `T`, an `Accessor[T]`, or a zero-argument function returning `T`. Inside the component, reading the field returns an `Accessor[T]`.
- A plain field (any annotation other than `Prop[...]`) is typed as declared. `props.on_wave` is `Callable[[], None] | None`.
- A missing required prop, a value of the wrong type, and an unknown keyword are all type errors:

```python
Greeting(name=42)  # incompatible type
Greeting()  # missing "name"
Greeting(name="Ada", typo=1)  # unexpected keyword "typo"
```

At run time, dev mode raises `TypeError` for the same unknown and missing props, so code that isn't type checked still fails loudly.

### Defaults need `default=`

Write defaults as `prop(default=value)`, or `prop(default_factory=list)` for mutable values. Type checkers only recognize a field specifier's default when it's passed by keyword, so a positional `prop(0)` isn't accepted. Plain fields use ordinary defaults (`on_wave: ... = None`); `prop()` is only for `Prop[T]` fields.

### Children

[`ParentProps`][wybthon.ParentProps] declares `children: Prop[Any]`. Both the `children` keyword and item syntax are checked:

```python
from wybthon import ParentProps, Prop, VNode, component, html


class CardProps(ParentProps):
    title: Prop[str]


@component
def Card(props: CardProps) -> VNode:
    return html(t"<div><h2>{props.title}</h2>{props.children}</div>")


Card(title="Hi")[html(t"<p>a</p>"), html(t"<p>b</p>")]
Card(title="Hi", children=html(t"<p>a</p><p>b</p>"))
```

Positional children (`Card(html(t"<p>a</p>"), title="Hi")`) work at run time, but checkers reject them because the props constructor is keyword-only.

### What a component call returns

`@component` is typed so that calling a component looks like constructing its props class; that's how the checker validates the keywords. At run time the call returns a [`VNode`][wybthon.VNode]. Every child position, in a template interpolation or an element helper, accepts the props type, so this mismatch only shows if you inspect the result yourself: an `isinstance` check sees a `VNode`. A component with no parameters is typed as a function returning `VNode`.

Under `mypy --strict`, annotate component functions with `-> VNode`, as above; [`html`][wybthon.html] and the element helpers return `VNode`.

## Templates

A template's interpolations are ordinary Python expressions, so the checker sees them like any other code. What's checked depends on where a value appears:

| In a template | Checked |
| --- | --- |
| `{expression}` in any position | Statically, as ordinary code: an undefined name, a wrong attribute, or a bad call is reported. |
| `{Card(title="Hi")}` | Statically, with full prop checking, like any component call. |
| `<{Card} title="Hi">...</{Card}>` | At run time only, in dev mode: an unknown or missing prop raises `TypeError` when the template renders. |
| The HTML markup itself | At run time: markup the parser would rewrite raises [`TemplateError`][wybthon.TemplateError] the first time the template is used. |

Type checkers can't see inside the template's static text, so the attributes of a `<{Card}>` tag are strings to them. Use the call form inside an interpolation when you want the checker's help with a component's props, and the tag form when passing nested markup as children reads better.

`html()` is annotated to take a `string.templatelib.Template`, so passing a plain string is a type error, and it raises `TypeError` at run time:

```python
from wybthon import html

html("<p>Hello</p>")  # error: expected "Template", got "str"
```

## Control flow

[`For`][wybthon.For] and [`Show`][wybthon.Show] have generic overloads, so their callbacks are checked against the data you pass. With `For`, the `keyed` strategy decides which arguments are accessors:

| Call | Callback arguments |
| --- | --- |
| `For(items, fn)` (the default, `keyed=True`) | `(item: T, index: Accessor[int])` |
| `For(items, fn, keyed=False)` | `(item: Accessor[T], index: int)` |
| `For(items, fn, keyed=lambda item: ...)` | `(item: Accessor[T], index: Accessor[int])` |

```python
from typing import TypedDict

from wybthon import Accessor, For, VNode, create_signal, html


class Todo(TypedDict):
    id: int
    title: str


todos, set_todos = create_signal([Todo(id=1, title="Write docs")])


def row(todo: Todo, index: Accessor[int]) -> VNode:
    return html(t"<li>{todo['title']}</li>")


def slot(todo: Accessor[Todo], index: int) -> VNode:
    def title() -> str:
        return todo()["title"]

    return html(t"<li>{index}: {title}</li>")


For(todos, row)
For(todos, slot, keyed=False)
For(todos, lambda todo, i: html(t"<li>{todo['title']}</li>"))  # todo: Todo
For(todos, lambda todo, i: html(t"<li>{todo['titel']}</li>"))  # error: no key "titel"
```

A lambda's parameters are inferred from the overload, so the last line is reported even though nothing is annotated.

`Show` passes the truthy value to a one-argument callback as an `Accessor`, or as the value itself with `keyed=True`. Either way, `None` is narrowed away, because the branch only renders when the value is truthy:

```python
from typing import TypedDict

from wybthon import Show, create_memo, create_signal, html


class User(TypedDict):
    name: str


users, set_users = create_signal([User(name="Ada")])
user = create_memo(lambda: next(iter(users()), None))  # Memo[User | None]

Show(user, lambda u: html(t"<p>{(lambda: u()['name'])}</p>"))  # u: Accessor[User]
Show(user, lambda u: html(t"<p>{u['name']}</p>"), keyed=True)  # u: User
Show(user, html(t"<p>Signed in</p>"), fallback=html(t"<p>Sign in</p>"))
```

`Repeat`'s callback receives an `int` index. `Switch` and `Match` take their children untyped.

## Accessors, setters, and memos

- [`Accessor[T]`][wybthon.Accessor] is readable: call it for a tracked read, or `.peek()` for an untracked one.
- [`Setter[T]`][wybthon.Setter] accepts a value or an updater function `T -> T`.
- [`Memo[T]`][wybthon.Memo] is a disposable derived accessor. An `async def` passed to `create_memo` produces a `Memo` of the awaited type.

```python
from wybthon import Accessor, Memo, create_memo, create_signal

count, set_count = create_signal(0)
doubled: Memo[int] = create_memo(lambda: count() * 2)
reader: Accessor[int] = count
set_count(lambda n: n + 1)
```

## Actions

An `@action` keeps its parameters and result type. An async action returns an `asyncio.Future[T]`, which supports cancellation, and the action object has `.pending()`.

```python
from wybthon import action


@action
def save(name: str) -> int:
    return len(name)


length: int = save("Ada")
```

## Stores

`create_store` returns a [`Store[S]`][wybthon.Store] (a read-only mapping) or a [`StoreList[T]`][wybthon.StoreList] (a read-only sequence), and setters receive the matching draft type. A store keeps its schema as a type parameter, but reads of individual keys (`store.name`, `store["name"]`) are typed `Any`, because a mapping proxy can't express per-key types without a checker plugin. Annotate where you read when the type matters:

```python
from typing import TypedDict

from wybthon import create_store


class Person(TypedDict):
    name: str
    age: int


person, write = create_store(Person(name="Ada", age=36))
name: str = person.name
age: int = person["age"]
write(lambda draft: setattr(draft, "name", "Grace"))
```

Mapping method names stay methods, so read a data key that collides with one (`items`, `keys`, `get`) with `[]`. A TypedDict annotation isn't runtime validation.

## Running the checkers

No plugin is needed. A minimal configuration:

```toml
[tool.mypy]
python_version = "3.14"
strict = true

[tool.pyright]
pythonVersion = "3.14"
typeCheckingMode = "strict"
```

The repository's `tests/typing` fixtures check valid calls and expected errors (missing, mistyped, and unknown props, a mistyped `For` row, and a plain string passed to `html()`) as part of the unit test gate.

## Next steps

- Read [Components](../concepts/components.md) for the full props model, and [Templates](../concepts/templates.md) for template syntax.
- See [Authoring patterns](authoring-patterns.md) for plain fields, children, and forwarding attributes.
- Browse the [`reactivity`][wybthon.reactivity] API for `Props`, `Prop`, and `prop`.
