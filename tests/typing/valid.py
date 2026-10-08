"""Public typing contracts that mypy and pyright must accept with no plugin."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypedDict, assert_type

from wybthon import (
    Accessor,
    ParentProps,
    Prop,
    Props,
    VNode,
    action,
    component,
    create_memo,
    create_signal,
    create_store,
    div,
    h2,
    p,
    prop,
)
from wybthon.router import QueryParams, RouteProps


class GreetingProps(Props):
    name: Prop[str]
    count: Prop[int] = prop(default=1)
    tags: Prop[list[str]] = prop(default_factory=list)
    on_wave: Callable[[], None] | None = None


@component
def Greeting(props: GreetingProps) -> VNode:
    if TYPE_CHECKING:
        assert_type(props.name, Accessor[str])
        assert_type(props.count(), int)
        assert_type(props.tags.peek(), list[str])
        assert_type(props.on_wave, Callable[[], None] | None)
    return p(lambda: props.name() * props.count())


name, _ = create_signal("Ada")
count = create_memo(lambda: len(name()))
Greeting(name="Ada")
Greeting(name=name, count=2)
Greeting(name=lambda: "Ada", count=count, tags=["a"])
Greeting(name="Ada", key="greeting", on_wave=lambda: None)
Greeting(name="Ada", key=3)


@component
def App() -> VNode:
    return div(Greeting(name="Ada"), Greeting(name="Grace", count=2))


App()


class CardProps(ParentProps):
    title: Prop[str]


@component
def Card(props: CardProps) -> VNode:
    return div(h2(props.title), props.children)


Card(title="Hi", children=[p("a"), p("b")])
Card(title="Hi")[p("a"), p("b")]
div(Card(title="Nested"), class_="wrapper")
div(class_="x")[p("item syntax on elements")]


@component
def User(props: RouteProps) -> VNode:
    if TYPE_CHECKING:
        assert_type(props.params(), dict[str, str])
        assert_type(props.query(), QueryParams)
    return p(lambda: props.params()["id"])


User()
User(params={"id": "1"})


class Person(TypedDict):
    name: str
    age: int
    items: list[str]


initial: Person = {"name": "Ada", "age": 36, "items": []}
store, write = create_store(initial)
store.items()  # Mapping method, even when data contains an "items" key.
store_name: Any = store.name
write(lambda draft: setattr(draft, "name", "Grace"))


@action
def save(name: str) -> int:
    return len(name)


assert_type(save("Ada"), int)
state: Accessor[str] = name

people, edit_people = create_store(list[Person]())
edit_people(lambda draft: draft.append({"name": "Ada", "age": 36, "items": []}))
edit_people(lambda draft: draft.extend([{"name": "Grace", "age": 40, "items": []}]))
edit_people(lambda draft: draft.insert(0, {"name": "Lin", "age": 30, "items": []}))
if TYPE_CHECKING:
    assert_type(people[0], Person)
    assert_type(people[0]["age"], int)

nested, edit_nested = create_store(list[list[Person]]())
edit_nested(lambda draft: draft.append([{"name": "Ada", "age": 36, "items": []}]))
