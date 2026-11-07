"""Engine v7 stores: dataclass stores, shallow stores, and lazy wrapping."""

import asyncio
from dataclasses import dataclass, field

import pytest

from wybthon import For, action, create_effect, create_memo, flush, html, is_pending
from wybthon.store import StoreObject, create_projection, create_store, deep, reconcile, snapshot


@dataclass
class Todo:
    id: int
    title: str
    done: bool = False

    def toggle(self) -> None:
        self.done = not self.done

    @property
    def label(self) -> str:
        return f"{self.title} (done)" if self.done else self.title

    @property
    def slug(self) -> str:
        return self.title.lower()

    @slug.setter
    def slug(self, value: str) -> None:
        self.title = value.title()


@dataclass
class State:
    filter: str = "all"
    todos: list[Todo] = field(default_factory=list)

    def visible(self) -> list[Todo]:
        if self.filter == "all":
            return list(self.todos)
        return [todo for todo in self.todos if todo.done == (self.filter == "done")]


def _state():
    return create_store(State(todos=[Todo(1, "Write"), Todo(2, "Ship", True)]))


# ---------------------------------------------------------------------------
# Dataclass stores
# ---------------------------------------------------------------------------


def test_dataclass_store_reads_fields_as_attributes(wyb):
    state, _ = _state()
    assert state.filter == "all"
    assert state.todos[0].title == "Write"
    assert len(state.todos) == 2
    assert isinstance(state, State) and isinstance(state.todos[0], Todo)
    assert isinstance(state, StoreObject)
    assert state.todos[0] is state.todos[0]


def test_dataclass_methods_and_properties_read_through_the_store(wyb):
    state, set_state = _state()
    labels = []
    create_effect(lambda: state.todos[0].label, labels.append)
    visible = create_memo(lambda: [todo.title for todo in state.visible()])
    flush()
    assert visible() == ["Write", "Ship"]
    set_state(lambda d: d.todos[0].toggle())
    flush()
    assert labels == ["Write", "Write (done)"]
    set_state(lambda d: setattr(d, "filter", "done"))
    flush()
    assert visible() == ["Write", "Ship"]
    set_state(lambda d: d.todos[1].toggle())
    flush()
    assert visible() == ["Write"]


def test_dataclass_drafts_assign_fields_and_property_setters(wyb):
    state, set_state = _state()

    def edit(d: State) -> None:
        d.todos[0].title = "Draft"
        d.todos[1].slug = "release"
        d.todos.append(Todo(3, "Celebrate"))

    set_state(edit)
    assert state.todos[0].title == "Write"
    flush()
    assert [todo.title for todo in state.todos] == ["Draft", "Release", "Celebrate"]
    with pytest.raises(AttributeError):
        set_state(lambda d: setattr(d, "missing", 1))
    with pytest.raises(AttributeError):
        state.filter = "done"


def test_dataclass_snapshot_and_deep_return_instances(wyb):
    state, set_state = _state()
    copied = snapshot(state)
    assert copied == State(todos=[Todo(1, "Write"), Todo(2, "Ship", True)])
    assert type(copied) is State and type(copied.todos[0]) is Todo
    copied.todos[0].title = "Changed"
    assert state.todos[0].title == "Write"
    seen = []
    create_effect(lambda: deep(state.todos[1]), seen.append)
    flush()
    set_state(lambda d: d.todos[1].toggle())
    flush()
    assert seen == [Todo(2, "Ship", True), Todo(2, "Ship", False)]
    assert state == State(todos=[Todo(1, "Write"), Todo(2, "Ship", False)])


def test_dataclass_replacement_and_reconcile_keep_identities(wyb):
    state, set_state = _state()
    first = state.todos[0]
    set_state(reconcile(State(filter="open", todos=[Todo(1, "Write!"), Todo(3, "New")])))
    flush()
    assert state.filter == "open"
    assert state.todos[0] is first and first.title == "Write!"
    assert [todo.id for todo in state.todos] == [1, 3]
    set_state(State())
    flush()
    assert state.filter == "all" and len(state.todos) == 0


def test_dataclass_rows_render_with_for(wyb, root_element):
    from conftest import collect_texts

    state, set_state = _state()

    def row(todo, index):
        return html(t"<li>{todo.label}</li>")

    def texts():
        return [text for text in collect_texts(root_element.element) if text.strip()]

    root = wyb["reconciler"].render(html(t"<ul>{For(state.todos, row)}</ul>"), root_element)
    assert texts() == ["Write", "Ship (done)"]
    set_state(lambda d: d.todos[0].toggle())
    flush()
    assert texts() == ["Write (done)", "Ship (done)"]
    set_state(lambda d: d.todos.reverse())
    flush()
    assert texts() == ["Ship (done)", "Write (done)"]
    root.dispose()


def test_dataclass_store_holds_with_transitions(wyb):
    async def main():
        state, set_state = _state()
        gate = asyncio.Event()

        @action
        async def rename():
            set_state(lambda d: setattr(d.todos[0], "title", "Held"))
            await gate.wait()

        future = rename()
        flush()
        assert state.todos[0].title == "Write"
        assert is_pending(lambda: state.todos[0].title)
        gate.set()
        await future
        flush()
        assert state.todos[0].title == "Held"

    asyncio.run(main())


def test_dataclass_projection(wyb):
    @dataclass
    class Summary:
        open: int = 0
        done: int = 0

    state, set_state = _state()

    def summarize(d: Summary) -> None:
        d.done = sum(todo.done for todo in state.todos)
        d.open = len(state.todos) - d.done

    summary = create_projection(summarize, Summary())
    flush()
    assert (summary.open, summary.done) == (1, 1)
    set_state(lambda d: d.todos[0].toggle())
    flush()
    assert (summary.open, summary.done) == (0, 2)


# ---------------------------------------------------------------------------
# Lazy wrapping and ownership
# ---------------------------------------------------------------------------


def test_creating_a_store_wraps_nothing_until_read(wyb):
    rows = [{"id": i, "nested": {"n": i}} for i in range(1000)]
    store, set_store = create_store({"rows": rows})
    root = store._node
    assert root.raw is not None  # A shell until something reads it.
    assert store["rows"][3]["nested"]["n"] == 3
    rows_node = store["rows"]._node
    unread = rows_node._value[4]
    assert unread.raw is not None and unread._value is None
    set_store(lambda d: d["rows"][4]["nested"].update(n=40))
    flush()
    assert store["rows"][4]["nested"]["n"] == 40
    assert snapshot(store)["rows"][5] == {"id": 5, "nested": {"n": 5}}


def test_stores_never_mutate_the_data_they_were_given(wyb):
    rows = [{"id": 1, "tags": ["a"]}]
    initial = {"rows": rows}
    store, set_store = create_store(initial)

    def edit(d):
        d["rows"][0]["tags"].append("b")
        d["rows"].append({"id": 2, "tags": []})
        d["extra"] = True

    set_store(edit)
    flush()
    assert initial == {"rows": [{"id": 1, "tags": ["a"]}]}
    assert snapshot(store) == {"rows": [{"id": 1, "tags": ["a", "b"]}, {"id": 2, "tags": []}], "extra": True}


def test_large_replacement_is_wrapped_lazily(wyb):
    store, set_store = create_store({"rows": []})
    seen = []
    create_effect(lambda: len(store["rows"]), seen.append)
    flush()
    set_store(lambda d: d.update(rows=[{"id": i} for i in range(5000)]))
    flush()
    assert seen == [0, 5000]
    # Its length was read, so the list is wrapped; its 5,000 rows aren't.
    assert all(row._value is None for row in store["rows"]._node._value)
    assert store["rows"][4999]["id"] == 4999


def test_snapshot_of_unread_subtree_copies_raw_data(wyb):
    initial = {"a": {"b": [{"c": 1}]}}
    store, _ = create_store(initial)
    copied = snapshot(store)
    assert copied == initial and copied["a"] is not initial["a"]
    assert copied["a"]["b"][0] is not initial["a"]["b"][0]


# ---------------------------------------------------------------------------
# Shallow stores
# ---------------------------------------------------------------------------


def test_shallow_store_tracks_only_the_top_level(wyb):
    config, set_config = create_store({"theme": {"accent": "blue"}, "debug": False}, shallow=True)
    theme = config["theme"]
    assert type(theme) is dict and theme == {"accent": "blue"}
    seen = []
    create_effect(lambda: config["theme"]["accent"], seen.append)
    flush()
    set_config(lambda d: d.update(theme={"accent": "red"}))
    flush()
    assert seen == ["blue", "red"]
    assert config["theme"] == {"accent": "red"}


def test_shallow_list_store_holds_plain_rows(wyb):
    rows, set_rows = create_store([{"id": 1}], shallow=True)
    first = rows[0]
    assert type(first) is dict
    set_rows(lambda d: d.append({"id": 2}))
    flush()
    assert rows[0] is first and [row["id"] for row in rows] == [1, 2]


def test_shallow_derived_store(wyb):
    rows, set_rows = create_store([{"id": 1}], shallow=True)
    ids = create_memo(lambda: [row["id"] for row in rows])
    assert ids() == [1]
    set_rows(lambda d: d.__setitem__(0, {"id": 9}))
    flush()
    assert ids() == [9]
