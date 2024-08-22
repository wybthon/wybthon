from js import document, fetch
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

    async def load_html(self, url: str) -> None:
        response = await fetch(url)
        html_content = await response.text()
        self.element.innerHTML = html_content


class BaseComponent(ABC):
    def __init__(self, children: Optional[List["BaseComponent"]] = None) -> None:
        self.children = children or []

    @abstractmethod
    async def render(self) -> Element:
        pass

    async def render_children(self, parent: Element) -> None:
        for child in self.children:
            child_element = await child.render()  # Await the async render method
            parent.element.appendChild(child_element.element)


# ------------------------------------------------------------
# Wybthon example
# ------------------------------------------------------------


class AppComponent(BaseComponent):
    async def render(self) -> Element:
        el = Element("div")  # Create a div as the root container for the app

        # Render self content
        header = Element("h1")
        header.set_text("Hello, world!")
        el.element.appendChild(header.element)

        # Render children components
        await self.render_children(el)

        # Append the app root to the body
        el.append_to(Element("body", existing=True))
        return el


class ChildComponent(BaseComponent):
    async def render(self) -> Element:
        el = Element("div")
        await el.load_html("child_component.html")
        # Example of how to adjust the HTML template within Python below
        # dynamic_text = Element("span", existing=True)
        # dynamic_text.set_text("dynamic content")
        return el


async def main():
    child1 = ChildComponent()
    child2 = ChildComponent()
    app = AppComponent(children=[child1, child2])
    await app.render()
