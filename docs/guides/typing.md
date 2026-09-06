# Typing

Wybthon requires Python 3.12 or later. Its public accessors, component decorators, actions, and collection protocols retain useful type information. Enable the bundled mypy plugin for component prop input types and TypedDict store fields:

```ini
[mypy]
plugins = wybthon.mypy_plugin
strict = True
```

The plugin runs only in mypy. Browser applications don't load it. Other type checkers can use the declared collection and accessor types, but don't receive the plugin's component signature transformations.

## Component props

```python
from wybthon import Prop, VNode, component, create_signal, p

@component
def Greeting(name: Prop[str], copies: int = 1) -> VNode:
    return p(lambda: name() * copies)

name, set_name = create_signal("Ada")
Greeting(name="Ada")
Greeting(name=name, copies=2)
Greeting(name=lambda: "Grace")
```

A `Prop[T]` accepts a plain `T`, an `Accessor[T]`, or a zero-argument expression returning `T`. Inside the component, call the prop to read it. Ordinary annotated arguments stay ordinary values. Mypy checks required props, unknown names, and incompatible types. `key` is a framework identity argument. A `Props` parameter or `**rest` deliberately permits an open prop set.

Use `literal(value)` to pass a callable as data rather than as an expression. It also disambiguates a callable value from a signal setter's updater function.

## Store schemas

```python
from typing import TypedDict
from wybthon import create_store

class Person(TypedDict):
    name: str
    age: int

initial: Person = {"name": "Ada", "age": 36}
person, write = create_store(initial)
name: str = person.name
age: int = person["age"]
write(lambda draft: setattr(draft, "name", "Grace"))
```

TypedDict fields and nested lists retain their read types. Unknown literal keys are errors. Mapping method names stay methods, so access a conflicting data key through `[]`. Dynamic string keys and `setattr` follow Python's dynamic typing rules; a TypedDict annotation isn't runtime validation.

`Store[S]` is a read-only mapping; `StoreList[T]` is a read-only sequence. Drafts expose the mutable protocols. `Accessor[T]` is readable, `Setter[T]` accepts a value or updater, and `Memo[T]` is a disposable derived accessor.

An `@action` keeps its parameters and result type. An async action returns an `asyncio.Future[T]`, including cancellation and `.pending()` on the action object.

The repository's `tests/typing` fixtures check valid calls and expected errors under strict mypy. They are part of the unit test gate.
