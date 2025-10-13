from typing import Any, Callable, Dict, List, Optional, Union

from js import document, fetch

__all__ = ["Element", "Ref"]


class Element:
    def __init__(self, tag: Optional[str] = None, existing: bool = False, node: Any = None) -> None:
        self._event_listeners: List[Dict[str, Any]] = []
        if node is not None:
            self.element = node
        else:
            if existing:
                if tag is None:
                    raise ValueError("When existing=True, provide a CSS selector in 'tag'.")
                self.element = document.querySelector(tag)
            else:
                if tag is None:
                    raise ValueError("Provide a tag name when creating a new element.")
                self.element = document.createElement(tag)

    def set_text(self, text: str) -> None:
        self.element.textContent = text

    def append_to(self, parent: "Element") -> None:
        parent.element.appendChild(self.element)

    def append(self, child: Union["Element", str]) -> None:
        if isinstance(child, Element):
            self.element.appendChild(child.element)
        else:
            self.element.appendChild(document.createTextNode(child))

    def remove(self) -> None:
        if self.element.parentNode is not None:
            self.element.parentNode.removeChild(self.element)

    async def load_html(self, url: str) -> None:
        response = await fetch(url)
        html_content = await response.text()
        self.element.innerHTML = html_content

    def set_html(self, html: str) -> None:
        self.element.innerHTML = html

    # --------------- Attributes ---------------
    def set_attr(self, name: str, value: Union[str, int, float, bool]) -> None:
        # Text nodes don't support setAttribute; fall back to nodeValue
        if hasattr(self.element, "setAttribute"):
            self.element.setAttribute(name, str(value))
        else:
            if name in ("nodeValue", "text"):
                self.element.nodeValue = str(value)
            else:
                # Ignore unsupported attributes on text nodes
                pass

    def get_attr(self, name: str) -> Optional[str]:
        value = self.element.getAttribute(name)
        return value if value is not None else None

    def remove_attr(self, name: str) -> None:
        self.element.removeAttribute(name)

    # --------------- Styles ---------------
    def set_style(self, styles: Optional[Dict[str, Union[str, int]]] = None, **style_kwargs: Union[str, int]) -> None:
        style_obj = self.element.style
        if styles:
            for key, value in styles.items():
                style_obj.setProperty(key, str(value))
        for key, value in style_kwargs.items():
            style_obj.setProperty(key, str(value))

    # --------------- Classes ---------------
    def add_class(self, *class_names: str) -> None:
        for name in class_names:
            self.element.classList.add(name)

    def remove_class(self, *class_names: str) -> None:
        for name in class_names:
            self.element.classList.remove(name)

    def toggle_class(self, class_name: str, force: Optional[bool] = None) -> None:
        if force is None:
            self.element.classList.toggle(class_name)
        else:
            self.element.classList.toggle(class_name, bool(force))

    def has_class(self, class_name: str) -> bool:
        return bool(self.element.classList.contains(class_name))

    # --------------- Events ---------------
    def on(self, event_type: str, handler: Callable[[Any], Any], *, options: Optional[Dict[str, Any]] = None) -> None:
        try:
            from pyodide.ffi import create_proxy
        except Exception:  # pragma: no cover

            def create_proxy(fn: Callable[[Any], Any]) -> Any:
                return fn

        proxy = create_proxy(handler)
        if options is None:
            self.element.addEventListener(event_type, proxy)
        else:
            self.element.addEventListener(event_type, proxy, options)
        self._event_listeners.append({"type": event_type, "proxy": proxy, "handler": handler, "options": options})

    def off(self, event_type: Optional[str] = None, handler: Optional[Callable[[Any], Any]] = None) -> None:
        remaining: List[Dict[str, Any]] = []
        for rec in self._event_listeners:
            match_type = (event_type is None) or (rec["type"] == event_type)
            match_handler = (handler is None) or (rec["handler"] == handler)
            if match_type and match_handler:
                self.element.removeEventListener(rec["type"], rec["proxy"])
            else:
                remaining.append(rec)
        self._event_listeners = remaining

    def cleanup(self) -> None:
        for rec in self._event_listeners:
            self.element.removeEventListener(rec["type"], rec["proxy"])
        self._event_listeners.clear()

    # --------------- Query helpers ---------------
    @classmethod
    def query(cls, selector: str, within: Optional["Element"] = None) -> Optional["Element"]:
        ctx = within.element if within is not None else document
        node = ctx.querySelector(selector)
        if node is None:
            return None
        return cls(node=node)

    @classmethod
    def query_all(cls, selector: str, within: Optional["Element"] = None) -> List["Element"]:
        ctx = within.element if within is not None else document
        nodes = ctx.querySelectorAll(selector)
        return [cls(node=n) for n in nodes]

    def find(self, selector: str) -> Optional["Element"]:
        node = self.element.querySelector(selector)
        return Element(node=node) if node is not None else None

    def find_all(self, selector: str) -> List["Element"]:
        nodes = self.element.querySelectorAll(selector)
        return [Element(node=n) for n in nodes]

    # --------------- Refs ---------------
    def attach_ref(self, ref: "Ref") -> None:
        ref.current = self


class Ref:
    def __init__(self) -> None:
        self.current: Optional[Element] = None
