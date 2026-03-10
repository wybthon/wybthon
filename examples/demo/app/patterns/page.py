from app.components.card import Card
from app.components.names_list import NamesList
from app.components.timer import Timer
from wybthon import component, div, h


@component
def Page():
    return div(
        h(Card, {"title": "State & Derived"}, h(NamesList, {})),
        h(Card, {"title": "Cleanup"}, h(Timer, {})),
    )
