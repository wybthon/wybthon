"""Deliberately invalid calls; the regression test checks diagnostics."""

from typing import TypedDict

from wybthon import Prop, VNode, action, component, create_store, p


@component
def Greeting(name: Prop[str]) -> VNode:
    return p(name)


Greeting(name=42)
Greeting()
Greeting(name="Ada", typo=True)


class Person(TypedDict):
    age: int


initial: Person = {"age": 36}
store, _ = create_store(initial)
wrong: str = store.age
missing = store["typo"]


@action
def save(age: int) -> int:
    return age


save("wrong")

people, edit_people = create_store(list[Person]())
edit_people(lambda draft: draft.append({"age": "wrong"}))
