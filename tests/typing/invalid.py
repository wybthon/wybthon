"""Deliberately invalid code: each line marked `# error: <kind>` must be reported by mypy and pyright."""

from typing import TypedDict

from wybthon import Accessor, For, Props, Show, VNode, action, component, create_signal, create_store, html


class StrictProps(Props):
    name: str


@component
def Greeting(props: StrictProps) -> VNode:
    props.name = "x"  # error: assign-prop
    return html(t"<p>{props.name}</p>")


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
wrong: Accessor[str] = Greeting(name="Ada").name  # error: value-is-not-accessor


class Person(TypedDict):
    age: int


@action
def save(age: int) -> int:
    return age


save("wrong")  # error: action-arg

people, edit_people = create_store(list[Person]())
edit_people(lambda draft: draft.append({"age": "wrong"}))  # error: store-append


class Todo(TypedDict):
    title: str


todos, _set_todos = create_signal([Todo(title="a")])
current, _set_current = create_signal(Todo(title="b"))
For(todos, lambda todo, i: html(t"<p>{todo['titel']}</p>"))  # error: for-row
Show(current, lambda todo: html(t"<p>{todo['title']}</p>"))  # error: show-branch
html("<p>not a t-string</p>")  # error: html-arg
