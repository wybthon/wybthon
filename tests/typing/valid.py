"""Public typing contracts that mypy and pyright must accept with no plugin."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict, assert_type

from wybthon import (
    Accessor,
    Children,
    For,
    Node,
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
from wybthon.router import SearchParams
from wybthon.vnode import VNode, h


@component
def Greeting(
    name: str,
    count: int = 1,
    tags: list[str] = prop(default_factory=list),
    on_wave: Callable[[], None] | None = None,
) -> VNode:
    if TYPE_CHECKING:
        assert_type(name, str)
        assert_type(count, int)
        assert_type(untrack(lambda: tags), list[str])
        assert_type(on_wave, Callable[[], None] | None)
        assert_type(is_static(name), bool)
    return html(t"<p>{name * count}</p>")


name, _ = create_signal("Ada")
count = create_memo(lambda: len(name()))
Greeting(name="Ada")
Greeting("Ada", 2)
Greeting(name="Ada", count=2, tags=["a"])
Greeting(name="Ada", on_wave=lambda: None)
# Inside a template, reactive values are checked against the parameter types;
# the compiler passes getters.
reactive_greeting: VNode = html(t"<div>{Greeting(name=name(), count=count())}</div>")


# A component call is a node: return it, and keep it in node lists.
def greeting_for(person: str) -> Node:
    return Greeting(name=person)


nodes: list[Node] = [Greeting(name="Ada"), html(t"<hr>")]


@component
def Divider() -> Node:
    return html(t"<hr>")


Divider()


@component
def Button(label: str, **attrs: object) -> Node:
    return html(t"<button {attrs}>{label}</button>")


Button(label="Save", id="save", disabled=True)


@component
def Source(source: Accessor[int], format: Callable[[int], str] = str) -> VNode:
    if TYPE_CHECKING:
        assert_type(source, Accessor[int])
        assert_type(format, Callable[[int], str])
    return html(t"<p>{format(source())}</p>")


Source(source=count)
Source(source=create_memo(lambda: 3), format=hex)


@component
def App() -> VNode:
    return html(t'<div><{Greeting} name="Ada" />{Greeting(name="Grace", count=2)}</div>')


App()


@component
def Card(title: str, children: Children = None) -> VNode:
    return html(t"<div><h2>{title}</h2>{children}</div>")


Card(title="Hi", children=[html(t"<p>a</p>"), html(t"<p>b</p>")])
Card(title="Hi")[html(t"<p>a</p>"), html(t"<p>b</p>")]
h("div", {"class_": "wrapper"}, Card(title="Nested"))
h("div", {"class": "x"})[h("p", None, "item syntax on elements")]


@component
def User(params: dict[str, str], search: SearchParams) -> VNode:
    if TYPE_CHECKING:
        assert_type(params, dict[str, str])
        assert_type(search, SearchParams)
    return html(t"<p>{params['id']}</p>")


User(params={"id": "1"}, search=SearchParams())


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
