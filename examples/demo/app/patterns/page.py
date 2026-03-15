from app.components.card import Card
from app.components.hello import Hello
from app.components.names_list import NamesList
from app.components.timer import Timer
from wybthon import component, div, h, h2, p


@component
def Page():
    return div(
        div(
            h2("Component Patterns"),
            p(
                "Reusable patterns: Card wrapper, stateless components, "
                "signal-based state, and lifecycle management."
            ),
            class_name="page-header",
        ),
        h(Card, {"title": "Stateless Component"}, h(Hello, {"name": "Wybthon"})),
        h(Card, {"title": "State & Derived Values"}, h(NamesList, {})),
        h(Card, {"title": "Lifecycle: Mount & Cleanup"}, h(Timer, {})),
        class_name="page",
    )
