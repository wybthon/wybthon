"""Deliberately invalid code: each line marked `# error: <kind>` must be reported by mypy and pyright."""

from typing import TypedDict

from wybthon import Prop, Props, VNode, action, component, create_store, p


class StrictProps(Props):
    name: Prop[str]


@component
def Greeting(props: StrictProps) -> VNode:
    props.name = "x"  # error: assign-prop
    return p(props.name)


@component
def Bare() -> VNode:
    return p("bare")


Greeting()  # error: missing-prop
Greeting(name=42)  # error: wrong-type
Greeting(name="Ada", typo=True)  # error: unknown-prop
Bare(title="x")  # error: no-props
wrong: str = Greeting(name="Ada").name  # error: accessor-is-not-value


class Person(TypedDict):
    age: int


@action
def save(age: int) -> int:
    return age


save("wrong")  # error: action-arg

people, edit_people = create_store(list[Person]())
edit_people(lambda draft: draft.append({"age": "wrong"}))  # error: store-append
