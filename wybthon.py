from js import document


class Element:
    def __init__(self, tag: str) -> None:
        self.element = document.createElement(tag)

    def set_text(self, text: str) -> None:
        self.element.textContent = text

    def append_to(self, parent: 'Element') -> None:
        parent.element.appendChild(self.element)


class BodyElement(Element):
    def __init__(self) -> None:
        self.element = document.body


class BaseComponent:
    def __init__(self) -> None:
        self.render()

    def render(self) -> None:
        raise NotImplementedError(
            "render method should be implemented by subclasses")


class HelloWorldComponent(BaseComponent):
    def render(self) -> None:
        el = Element('h1')
        el.set_text('Hello, World!')
        el.append_to(BodyElement())
