"""Public typing contracts, checked with strict mypy."""

from typing import TypedDict, assert_type

from wybthon import Accessor, Prop, VNode, action, component, create_signal, create_store, literal, p


@component
def Greeting(name: Prop[str], count: int = 1) -> VNode:
    return p(lambda: name() * count)


name, _ = create_signal("Ada")
Greeting(name="Ada")
Greeting(name=name, count=2)
Greeting(name=lambda: "Ada")
Greeting(name=literal("Ada"), key="greeting")


class Person(TypedDict):
    name: str
    age: int
    items: list[str]


initial: Person = {"name": "Ada", "age": 36, "items": []}
store, write = create_store(initial)
assert_type(store.name, str)
assert_type(store["age"], int)
store.items()  # Mapping method, even when data contains an "items" key.
assert_type(store["items"][0], str)
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
assert_type(people[0].age, int)

nested, edit_nested = create_store(list[list[Person]]())
edit_nested(lambda draft: draft.append([{"name": "Ada", "age": 36, "items": []}]))
