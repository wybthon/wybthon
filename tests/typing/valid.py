"""Public typing contracts that mypy and pyright must accept with no plugin."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict, assert_type

from wybthon import (
    Accessor,
    For,
    Node,
    ParentProps,
    Props,
    Show,
    action,
    component,
    create_memo,
    create_signal,
    create_store,
    deep,
    html,
    is_static,
    prop,
    reconcile,
    snapshot,
    untrack,
)
from wybthon.router import RouteProps, SearchParams
from wybthon.vnode import VNode, h


class GreetingProps(Props):
    name: str
    count: int = prop(default=1)
    tags: list[str] = prop(default_factory=list)
    on_wave: Callable[[], None] | None = None


@component
def Greeting(props: GreetingProps) -> VNode:
    if TYPE_CHECKING:
        assert_type(props.name, str)
        assert_type(props.count, int)
        assert_type(untrack(lambda: props.tags), list[str])
        assert_type(props.on_wave, Callable[[], None] | None)
        assert_type(is_static(props, "name"), bool)
    return html(t"<p>{props.name * props.count}</p>")


name, _ = create_signal("Ada")
count = create_memo(lambda: len(name()))
Greeting(name="Ada")
Greeting(name="Ada", count=2, tags=["a"])
Greeting(name="Ada", key="greeting", on_wave=lambda: None)
Greeting(name="Ada", key=3)
# Inside a template, reactive values are checked against the field types;
# the compiler passes getters.
reactive_greeting: VNode = html(t"<div>{Greeting(name=name(), count=count())}</div>")


# A component call is a node: return it, and keep it in node lists.
def greeting_for(person: str) -> Node:
    return Greeting(name=person)


nodes: list[Node] = [Greeting(name="Ada"), html(t"<hr>")]


@component
def Divider() -> Node:
    return html(t"<hr>")


# Every component takes `key`, props or not.
Divider()
Divider(key="divider")


class SourceProps(Props):
    source: Accessor[int]
    format: Callable[[int], str] = str


@component
def Source(props: SourceProps) -> VNode:
    if TYPE_CHECKING:
        assert_type(props.source, Accessor[int])
        assert_type(props.format, Callable[[int], str])
    return html(t"<p>{props.format(props.source())}</p>")


Source(source=count)
Source(source=create_memo(lambda: 3), format=hex)


@component
def App() -> VNode:
    return html(t'<div><{Greeting} name="Ada" />{Greeting(name="Grace", count=2)}</div>')


App()


class CardProps(ParentProps):
    title: str


@component
def Card(props: CardProps) -> VNode:
    return html(t"<div><h2>{props.title}</h2>{props.children}</div>")


Card(title="Hi", children=[html(t"<p>a</p>"), html(t"<p>b</p>")])
Card(title="Hi")[html(t"<p>a</p>"), html(t"<p>b</p>")]
h("div", {"class_": "wrapper"}, Card(title="Nested"))
h("div", {"class": "x"})[h("p", None, "item syntax on elements")]


@component
def User(props: RouteProps) -> VNode:
    if TYPE_CHECKING:
        assert_type(props.params, dict[str, str])
        assert_type(props.search, SearchParams)
    return html(t"<p>{props.params['id']}</p>")


User()
User(params={"id": "1"})


class Person(TypedDict):
    name: str
    age: int
    items: list[str]


initial: Person = {"name": "Ada", "age": 36, "items": []}
store, write = create_store(initial)
# A store is typed as its own data: here, a `Person` TypedDict.
assert_type(store, Person)
assert_type(store["age"], int)
assert_type(store["items"], list[str])
write(lambda draft: draft.update({"name": "Grace"}))
write({"name": "Lin", "age": 30, "items": []})


@dataclass
class Task:
    title: str
    done: bool = False

    def toggle(self) -> None:
        self.done = not self.done


@dataclass
class Board:
    tasks: list[Task] = field(default_factory=list)


board, edit_board = create_store(Board([Task("a")]))
assert_type(board, Board)
assert_type(board.tasks[0].done, bool)


def finish(draft: Board) -> None:
    draft.tasks[0].done = True
    draft.tasks.append(Task("b"))
    draft.tasks[1].toggle()


edit_board(finish)
edit_board(Board())
edit_board(reconcile(Board([Task("c")]), key="title"))
assert_type(snapshot(board), Board)
assert_type(deep(board.tasks), list[Task])


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


class Todo(TypedDict):
    title: str
    done: bool


todos, _set_todos = create_signal([Todo(title="a", done=False)])
current: Accessor[Todo | None] = create_signal(Todo(title="b", done=True))[0]


def todo_row(todo: Todo, index: Accessor[int]) -> VNode:
    return html(t"<p>{todo['title']}{index() + 1}</p>")


For(todos, todo_row)
For(todos, lambda todo, i: html(t"<p>{todo['title']}</p>"))
For(todos, lambda todo, i: html(t"<p>{todo()['title']}{i}</p>"), keyed=False)
For(todos, lambda todo, i: html(t"<p>{todo()['title']}{i()}</p>"), keyed=lambda row: row["title"])
Show(current, lambda todo: html(t"<p>{todo()['title']}</p>"))
Show(current, lambda todo: html(t"<p>{todo['title']}</p>"), keyed=True)
Show(current, lambda: html(t"<p>shown</p>"), fallback=html(t"<p>hidden</p>"))
Show(True, html(t"<p>always</p>"))
template_node: VNode = html(t"<p class={current}>{todos}</p>")


# A row callback may take the item alone.
For(todos, lambda todo: html(t"<li>{todo['title']}</li>"))
