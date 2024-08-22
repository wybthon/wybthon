from js import document
from abc import ABC, abstractmethod
from typing import List, Optional


# ------------------------------------------------------------
# Wybthon framework
# ------------------------------------------------------------


class Element:
    def __init__(self, tag: str, existing: bool = False) -> None:
        if existing:
            self.element = document.querySelector(tag)
        else:
            self.element = document.createElement(tag)

    def set_text(self, text: str) -> None:
        self.element.textContent = text

    def append_to(self, parent: "Element") -> None:
        parent.element.appendChild(self.element)


class BaseComponent(ABC):
    def __init__(self, children: Optional[List["BaseComponent"]] = None) -> None:
        self.children = children or []

    @abstractmethod
    def render(self) -> Element:
        pass

    def render_children(self, parent: Element) -> None:
        for child in self.children:
            child_element = child.render()
            parent.element.appendChild(child_element.element)


# ------------------------------------------------------------
# Wybthon example
# ------------------------------------------------------------


class AppComponent(BaseComponent):
    def render(self) -> Element:
        el = Element("div")  # Create a div as the root container for the app

        # Render self content
        header = Element("h1")
        header.set_text("Hello, world!")
        el.element.appendChild(header.element)

        # Render children components
        self.render_children(el)

        # Append the app root to the body
        el.append_to(Element("body", existing=True))
        return el


class ChildComponent(BaseComponent):
    def render(self) -> Element:
        el = Element("p")
        el.set_text("I am a child component!")
        return el


def main():
    child1 = ChildComponent()
    child2 = ChildComponent()
    app = AppComponent(children=[child1, child2])
    app.render()
