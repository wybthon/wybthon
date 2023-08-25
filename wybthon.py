from js import document
from abc import ABC, abstractmethod


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
    def __init__(self) -> None:
        self.render()

    @abstractmethod
    def render(self) -> None:
        pass


class HelloWorldComponent(BaseComponent):
    def render(self) -> None:
        el = Element("h1")
        el.set_text("Hello, world!")
        el.append_to(Element("body", existing=True))
