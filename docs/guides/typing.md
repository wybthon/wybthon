# Typing

Wybthon requires Python 3.14. Its accessors, components, actions, and stores carry type information that both pyright (including Pylance) and mypy understand with no plugin or extra configuration.

## Component props

Components declare their inputs on a [`Props`][wybthon.Props] subclass with plain annotations. `Props` is a [PEP 681](https://peps.python.org/pep-0681/) `dataclass_transform` base, so a type checker treats each props class as a keyword-only constructor and checks every component call against it:

```python
from collections.abc import Callable

from wybthon import Node, Props, component, create_signal, html, prop


class GreetingProps(Props):
    name: str
    copies: int = 1
    tags: list[str] = prop(default_factory=list)
    on_wave: Callable[[], None] | None = None


@component
def Greeting(props: GreetingProps) -> Node:
    def wave() -> None:
        if props.on_wave is not None:
            props.on_wave()

    return html(t"<p onclick={wave}>{props.name * props.copies}</p>")


name, set_name = create_signal("Ada")
Greeting(name="Ada")
Greeting(name="Ada", copies=2, on_wave=lambda: print("hi"))
html(t"<div>{Greeting(name=name(), copies=2)}</div>")
```

- Inside the component, a field reads as its annotation: `props.name` is a `str`, and `props.copies` is an `int`. The read is tracked, so `{props.name * props.copies}` updates when either changes.
- A caller passes values of the declared types. In a template, `{Greeting(name=name())}` type-checks as `name: str`, and the compiler still passes a getter, so the prop stays reactive. In Python code outside a template, `Greeting(name=name)` passes the accessor itself, which works at run time (the read unwraps it) but is a type error, because an `Accessor[str]` isn't a `str`.
- A missing required prop, a value of the wrong type, and an unknown keyword are all type errors:

```python
Greeting(name=42)  # incompatible type
Greeting()  # missing "name"
Greeting(name="Ada", typo=1)  # unexpected keyword "typo"
```

At run time, dev mode raises `TypeError` for the same unknown and missing props, so code that isn't type checked still fails loudly.

### Callable fields

A field annotated as callable, with `Callable[...]` or [`Accessor[T]`][wybthon.Accessor], alone or in a union with `None`, is returned exactly as the parent passed it. That's how callbacks work: reading `props.on_wave` never calls it, so `props.on_wave()` calls the parent's function. Every other field unwraps an accessor the parent passes, so a field that should hold a function must be annotated as one.

Annotate a field `Accessor[T]` when the component needs the accessor itself, for example to hand it to `For`:

```python
from wybthon import Accessor, For, Node, Props, component, html


class TagListProps(Props):
    items: Accessor[list[str]]


def tag(item: str, index: Accessor[int]) -> Node:
    return html(t"<li>{item}</li>")


@component
def TagList(props: TagListProps) -> Node:
    items = props.items  # the accessor itself
    return html(t"<ul>{For(items, tag)}</ul>")
```

Reading a callable field returns what the parent passed without calling it, so reading it once at the top of the body freezes nothing. The parent passes the accessor by name, `{TagList(items=tags)}`; an expression such as `tags()` would hand the component a getter, which every read unwraps, even for a callable field.

### Defaults

Defaults work as in a dataclass (`copies: int = 1`, `on_wave: ... = None`). Use [`prop(default_factory=list)`][wybthon.prop] for a mutable value; the factory runs once per component instance. `prop(default=value)` also works, but type checkers only recognize a field specifier's default when it's passed by keyword, so a positional `prop(0)` isn't accepted.

### Children

[`ParentProps`][wybthon.ParentProps] declares `children: Any`. Both the `children` keyword and item syntax are checked:

```python
from wybthon import Node, ParentProps, component, html


class CardProps(ParentProps):
    title: str


@component
def Card(props: CardProps) -> Node:
    return html(t"<div><h2>{props.title}</h2>{props.children}</div>")


Card(title="Hi")[html(t"<p>a</p>"), html(t"<p>b</p>")]
Card(title="Hi", children=html(t"<p>a</p><p>b</p>"))
```

Positional children (`Card(html(t"<p>a</p>"), title="Hi")`) work at run time, but checkers reject them because the props constructor is keyword-only.

### What a component call returns

`@component` is typed so that calling a component looks like constructing its props class; that's how the checker validates the keywords. To a type checker every props class is a [`Node`][wybthon.Node], the type of anything that renders, so a component call can be returned from a function annotated `-> Node`, kept in a `list[Node]`, or passed as children. At run time the call returns a [`VNode`][wybthon.vnode.VNode], which is a `Node` too. A component with no parameters is typed as a callable that takes only `key` and returns a `Node`.

Under `mypy --strict`, annotate component functions with `-> Node`; [`html`][wybthon.html] returns a `Node` as well.

## Templates

A template's interpolations are ordinary Python expressions, so the checker sees them like any other code, before the compiler turns the dynamic ones into getters. What's checked depends on where a value appears:

| In a template | Checked |
| --- | --- |
| `{expression}` in any position | Statically, as ordinary code: an undefined name, a wrong attribute, or a bad call is reported. |
| `{Card(title=user().name)}` | Statically, with full prop checking, like any component call. The checker sees `user().name` as a `str`; the compiler passes a getter. |
| `<{Card} title={user().name}>...</{Card}>` | The expression `user().name` is checked as code. A plain checker run doesn't check it against `Card`'s props, but [`wyb check`](#checking-tag-props-with-wyb-check) does. Without it, an unknown or missing prop raises `TypeError` at run time, in dev mode, when the template renders. |
| The HTML markup itself | When the module is compiled: markup the parser would rewrite is a `SyntaxError` with the file and line (or a [`TemplateError`][wybthon.TemplateError] for a template compiled at run time). |

Type checkers can't see inside the template's static text, so on their own they don't check a component tag's attributes against its props class. Run them through `wyb check` (below) to check tags too, or use the call form inside an interpolation; use the tag form when passing nested markup as children reads better.

`html()` is annotated to take a `string.templatelib.Template`, so passing a plain string is a type error, and it raises `TypeError` at run time:

```python
from wybthon import html

html("<p>Hello</p>")  # error: expected "Template", got "str"
```

### Checking tag props with `wyb check`

`wyb check` runs mypy or pyright on your project and checks every component tag's props as if the tag were a call:

```bash
wyb check                      # mypy on the current directory
wyb check app tests --checker pyright
```

For each `html(t"...")` call, it checks a call such as `Card(title=user().name, children=...)` per component tag, with each attribute as a keyword: a static value as its string, a bare attribute as `True`, an `{expression}` as itself, an attribute that mixes text and interpolations as a `str`, and a spread as `**expression`. Content between the tags is passed as `children`, so a component whose props have no `children` field is reported. Each error in a tag is reported at the tag's line, among the checker's other errors:

```text
app/pages.py:12: error: in <{Card}>: Unexpected keyword argument "bogus" for "CardProps"  [call-arg]
app/pages.py:14: error: in <{Card}>: Missing named argument "title" for "CardProps"  [call-arg]
```

The command exits with status 1 when there are errors and 2 when the checker isn't installed. It reads your project's checker configuration (`mypy.ini`, `setup.cfg`, `pyproject.toml`, or `pyrightconfig.json` in the current directory), and it skips `.venv`, `dist`, `build`, and hidden directories. Under mypy's defaults, the body of an unannotated function isn't checked, so neither are the tags in it.

A few tags aren't checked as calls: built-ins imported from Wybthon (`Show`, `For`, `Loading`, `Portal`, `Link`, and the rest), contexts made with `create_context`, and a plain function in the same module that takes the props dictionary instead of keywords.

## Control flow

[`For`][wybthon.For] and [`Show`][wybthon.Show] have generic overloads, so their callbacks are checked against the data you pass. With `For`, the `keyed` strategy decides which arguments are accessors:

| Call | Callback arguments |
| --- | --- |
| `For(items, fn)` (the default, `keyed=True`) | `(item: T, index: Accessor[int])` |
| `For(items, fn, keyed=False)` | `(item: Accessor[T], index: int)` |
| `For(items, fn, keyed=lambda item: ...)` | `(item: Accessor[T], index: Accessor[int])` |

```python
from typing import TypedDict

from wybthon import Accessor, For, Node, create_signal, html


class Todo(TypedDict):
    id: int
    title: str


todos, set_todos = create_signal([Todo(id=1, title="Write docs")])


def row(todo: Todo, index: Accessor[int]) -> Node:
    return html(t"<li>{todo['title']}</li>")


def slot(todo: Accessor[Todo], index: int) -> Node:
    return html(t"<li>{index}: {todo()['title']}</li>")


For(todos, row)
For(todos, slot, keyed=False)
For(todos, lambda todo, i: html(t"<li>{todo['title']}</li>"))  # todo: Todo
For(todos, lambda todo, i: html(t"<li>{todo['titel']}</li>"))  # error: no key "titel"
html(t"<ul>{For(todos(), row)}</ul>")  # in a template, the compiler passes a getter
```

A lambda's parameters are inferred from the overload, so the fourth call is reported even though nothing is annotated. In a template, `For(todos(), row)` checks the same way: the checker sees a `list[Todo]`.

`Show` passes the truthy value to a one-argument callback as an `Accessor`, or as the value itself with `keyed=True`. Either way, `None` is narrowed away, because the branch only renders when the value is truthy:

```python
from typing import TypedDict

from wybthon import Show, create_memo, create_signal, html


class User(TypedDict):
    name: str


users, set_users = create_signal([User(name="Ada")])
user = create_memo(lambda: next(iter(users()), None))  # Memo[User | None]

Show(user, lambda u: html(t"<p>{u()['name']}</p>"))  # u: Accessor[User]
Show(user, lambda u: html(t"<p>{u['name']}</p>"), keyed=True)  # u: User
Show(user, html(t"<p>Signed in</p>"), fallback=html(t"<p>Sign in</p>"))
```

The callback's type comes from `when`, so pass the accessor itself (`Show(user, ...)`) when the callback takes the value. `{Show(user(), panel)}` works the same at run time, but a checker sees a plain `User | None` there and accepts only a zero-argument callback or a node.

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

A store is typed as its own data. `create_store(initial)` returns `tuple[T, StoreSetter[T]]`, where `T` is the type of `initial`: a dataclass, a `TypedDict`, `list[Row]`, or any other type you give it. Reads check against your own annotations, with no checker plugin:

```python
from dataclasses import dataclass, field
from typing import assert_type

from wybthon import create_store, deep, reconcile, snapshot


@dataclass
class Task:
    title: str
    done: bool = False

    def toggle(self) -> None:
        self.done = not self.done


@dataclass
class Board:
    tasks: list[Task] = field(default_factory=list)


board, edit = create_store(Board([Task("Write docs")]))
assert_type(board, Board)
assert_type(board.tasks[0].done, bool)


def finish(draft: Board) -> None:
    draft.tasks[0].toggle()
    draft.tasks.append(Task("Ship it"))


edit(finish)
edit(Board())
edit(reconcile(Board([Task("Review")]), key="title"))
assert_type(snapshot(board), Board)
assert_type(deep(board.tasks), list[Task])
```

The setter accepts a `Callable[[T], object]` (a draft callback), replacement data of type `T`, or a [`reconcile`][wybthon.reconcile] result, so a draft callback is checked like any function taking a `Board`. [`snapshot`][wybthon.snapshot] and [`deep`][wybthon.deep] return the type they're given, and [`create_projection(fn, initial)`][wybthon.create_projection] is typed as `initial`'s type.

For a dict store, give the initial data a `TypedDict` type. Read and write it with subscripts, since dict stores have no attribute access:

```python
from typing import TypedDict, assert_type

from wybthon import create_store


class Person(TypedDict):
    name: str
    age: int


initial: Person = {"name": "Ada", "age": 36}
person, write = create_store(initial)
assert_type(person, Person)
assert_type(person["age"], int)
write(lambda draft: draft.update({"name": "Grace"}))
```

An empty list store takes its item type from the constructor: `create_store(list[Person]())`. The static type is your data's type, but the runtime view is a store: a dict store is a [`Store`][wybthon.Store] (a `Mapping`, not a `dict`), a list store is a [`StoreList`][wybthon.StoreList] (a `Sequence`), and a dataclass store is a [`StoreObject`][wybthon.StoreObject] that `isinstance` reports as your dataclass. A `TypedDict` annotation isn't runtime validation.

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

The repository's `tests/typing` fixtures check valid calls and expected errors (missing, mistyped, and unknown props, an accessor passed where a value is declared, a mistyped component call inside a template, a mistyped `For` row, and a plain string passed to `html()`) as part of the unit test gate.

## Next steps

- Read [Components](../concepts/components.md) for the full props model, and [Templates](../concepts/templates.md) for template syntax.
- See [Authoring patterns](authoring-patterns.md) for callbacks, children, and forwarding attributes.
- Browse the [`reactivity`][wybthon.reactivity] API for `Props`, `ParentProps`, and `prop`, and [The compiler](../concepts/compiler.md) for what happens to template expressions.
