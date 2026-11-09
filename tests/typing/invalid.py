"""Deliberately invalid code: each line marked `# error: <kind>` must be reported by mypy and pyright."""

from dataclasses import dataclass
from typing import TypedDict

from wybthon import Accessor, For, Show, action, component, create_signal, create_store, html
from wybthon.vnode import VNode


@component
def Greeting(name: str) -> VNode:
    wrong: Accessor[str] = name  # error: value-is-not-accessor
    return html(t"<p>{wrong}</p>")


@component
def Bare() -> VNode:
    return html(t"<p>bare</p>")


name, _ = create_signal("Ada")
Greeting()  # error: missing-prop
Greeting(name=42)  # error: wrong-type
Greeting(name="Ada", typo=True)  # error: unknown-prop
Bare(title="x")  # error: no-props
Greeting(name=name)  # error: accessor-is-not-value
html(t"<div>{Greeting(name=len(name()))}</div>")  # error: template-call
Greeting(name="Ada", key="k")  # error: no-key


class Person(TypedDict):
    age: int


@action
def save(age: int) -> int:
    return age


save("wrong")  # error: action-arg

people, edit_people = create_store(list[Person]())
edit_people(lambda draft: draft.append({"age": "wrong"}))  # error: store-append


@dataclass
class Task:
    title: str
    done: bool = False


board, edit_board = create_store(Task("a"))
_done: str = board.done  # error: store-field


class Todo(TypedDict):
    title: str


todos, _set_todos = create_signal([Todo(title="a")])
current, _set_current = create_signal(Todo(title="b"))
For(todos, lambda todo, i: html(t"<p>{todo['titel']}</p>"))  # error: for-row
Show(current, lambda todo: html(t"<p>{todo['title']}</p>"))  # error: show-branch
html("<p>not a t-string</p>")  # error: html-arg
