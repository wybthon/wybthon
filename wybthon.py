from js import document


class Element:
    def __init__(self, tag):
        self.element = document.createElement(tag)

    def set_text(self, text):
        self.element.textContent = text

    def append_to(self, parent):
        parent.element.appendChild(self.element)


class BodyElement(Element):
    def __init__(self):
        self.element = document.body


class BaseComponent:
    def __init__(self):
        self.render()

    def render(self):
        raise NotImplementedError(
            "render method should be implemented by subclasses")


class HelloWorldComponent(BaseComponent):
    def render(self):
        el = Element('h1')
        el.set_text('Hello, World!')
        el.append_to(BodyElement())
