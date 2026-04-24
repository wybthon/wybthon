"""Lightweight DOM wrapper utilities for Pyodide/browser environments.

This module exposes a thin Pythonic facade over the browser's DOM API,
designed to feel familiar to JavaScript developers while integrating
cleanly with Wybthon's reactive renderer:

- [`Element`][wybthon.Element] wraps a single DOM node and offers
  ergonomic helpers for attributes, classes, styles, events, and
  queries.
- [`Ref`][wybthon.Ref] is a mutable container used by the renderer to
  hand out a reference to a mounted element.

The wrapper deliberately mirrors familiar DOM property names (e.g.
`value`, `checked`, `files`) so that event handlers can read state
exactly as they would in JavaScript:

```python
def on_input(e):
    name(e.target.value)
```

See Also:
    - [Hello-world tutorial](../getting-started.md)
    - [Forms guide](../concepts/forms.md)
"""

from typing import Any, Callable, Dict, List, Optional, Union

from js import document, fetch

__all__ = ["Element", "Ref"]


class Element:
    """Thin wrapper around a DOM node with convenience methods.

    `Element` can be constructed in three ways:

    - With a tag name to create a brand-new node
      (`Element("div")`).
    - With a CSS selector and `existing=True` to wrap an existing
      node (`Element("#root", existing=True)`).
    - With an opaque `node` value to wrap a node returned by another
      API (used internally by query helpers).

    The wrapper proxies common form-input properties (`value`,
    `checked`, `files`) so handlers can read state from
    `e.target.value` exactly as in React or SolidJS.
    """

    def __init__(self, tag: Optional[str] = None, existing: bool = False, node: Any = None) -> None:
        """Create a new element, wrap an existing one, or wrap a raw node.

        Args:
            tag: Tag name (`"div"`) or, when `existing=True`, a CSS
                selector identifying the node to wrap.
            existing: If `True`, query the document for `tag` instead
                of creating a new element.
            node: Raw underlying DOM node to wrap. When provided,
                `tag` and `existing` are ignored.

        Raises:
            ValueError: If neither `node` nor a usable `tag` is
                provided.
        """
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

    @property
    def value(self) -> Any:
        """Current value of an `<input>`, `<textarea>`, or `<select>`."""
        return getattr(self.element, "value", None)

    @value.setter
    def value(self, new_value: Any) -> None:
        """Set the underlying DOM `value`, ignoring elements that do not support it."""
        try:
            self.element.value = new_value
        except Exception:
            pass

    @property
    def checked(self) -> bool:
        """Checked state of a checkbox or radio input."""
        return bool(getattr(self.element, "checked", False))

    @checked.setter
    def checked(self, flag: bool) -> None:
        """Set the underlying `checked` state, ignoring unsupported elements."""
        try:
            self.element.checked = bool(flag)
        except Exception:
            pass

    @property
    def files(self) -> Any:
        """`FileList` for file inputs (`<input type="file">`), or `None`."""
        return getattr(self.element, "files", None)

    def set_text(self, text: str) -> None:
        """Replace the text content of this element."""
        self.element.textContent = text

    def append_to(self, parent: "Element") -> None:
        """Append this element to `parent`."""
        parent.element.appendChild(self.element)

    def append(self, child: Union["Element", str]) -> None:
        """Append an `Element` or a text string as a child node."""
        if isinstance(child, Element):
            self.element.appendChild(child.element)
        else:
            self.element.appendChild(document.createTextNode(child))

    def remove(self) -> None:
        """Detach this element from its parent (no-op if already detached)."""
        if self.element.parentNode is not None:
            self.element.parentNode.removeChild(self.element)

    async def load_html(self, url: str) -> None:
        """Fetch HTML from `url` and assign it to `innerHTML`.

        Args:
            url: URL to fetch via the browser's `fetch` API.
        """
        response = await fetch(url)
        html_content = await response.text()
        self.element.innerHTML = html_content

    def set_html(self, html: str) -> None:
        """Replace this element's content with the provided HTML string.

        Caution:
            This bypasses the renderer's diffing and does **not**
            sanitize input. Avoid passing untrusted HTML.
        """
        self.element.innerHTML = html

    def set_attr(self, name: str, value: Union[str, int, float, bool]) -> None:
        """Set an attribute on this element, with text-node fallbacks.

        Args:
            name: Attribute name (or `nodeValue`/`text` for text nodes).
            value: Attribute value; coerced to `str`.
        """
        if hasattr(self.element, "setAttribute"):
            self.element.setAttribute(name, str(value))
        else:
            if name in ("nodeValue", "text"):
                self.element.nodeValue = str(value)
            else:
                pass

    def get_attr(self, name: str) -> Optional[str]:
        """Return the attribute value for `name`, or `None` when absent."""
        value = self.element.getAttribute(name)
        return value if value is not None else None

    def remove_attr(self, name: str) -> None:
        """Remove an attribute from this element."""
        self.element.removeAttribute(name)

    def set_style(self, styles: Optional[Dict[str, Union[str, int]]] = None, **style_kwargs: Union[str, int]) -> None:
        """Set CSS properties using a dict and/or keyword arguments.

        Args:
            styles: Optional mapping of CSS property name to value.
            **style_kwargs: Additional CSS properties (last write wins
                if a key appears in both).
        """
        style_obj = self.element.style
        if styles:
            for key, value in styles.items():
                style_obj.setProperty(key, str(value))
        for key, value in style_kwargs.items():
            style_obj.setProperty(key, str(value))

    def add_class(self, *class_names: str) -> None:
        """Add one or more CSS classes to this element."""
        for name in class_names:
            self.element.classList.add(name)

    def remove_class(self, *class_names: str) -> None:
        """Remove one or more CSS classes from this element."""
        for name in class_names:
            self.element.classList.remove(name)

    def toggle_class(self, class_name: str, force: Optional[bool] = None) -> None:
        """Toggle a CSS class, optionally forcing on/off.

        Args:
            class_name: Class to toggle.
            force: Pass `True` to ensure the class is added, `False`
                to ensure it is removed; `None` toggles based on the
                current state.
        """
        if force is None:
            self.element.classList.toggle(class_name)
        else:
            self.element.classList.toggle(class_name, bool(force))

    def has_class(self, class_name: str) -> bool:
        """Return `True` if the element currently has the given class."""
        return bool(self.element.classList.contains(class_name))

    def on(self, event_type: str, handler: Callable[[Any], Any], *, options: Optional[Dict[str, Any]] = None) -> None:
        """Add an event listener and track it for later cleanup.

        Listeners attached through `on` are remembered and removed by
        [`off`][wybthon.Element.off] or
        [`cleanup`][wybthon.Element.cleanup]. The handler is wrapped in
        a Pyodide proxy so it can be released on removal.

        Args:
            event_type: DOM event name (e.g. `"click"`, `"input"`).
            handler: Callback invoked with the DOM event object.
            options: Optional `addEventListener` options
                (e.g. `{"capture": True}`).
        """
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
        """Remove matching event listeners previously attached via `on`.

        Args:
            event_type: If given, only remove listeners of this type.
            handler: If given, only remove listeners with this exact
                callback identity.

        When both arguments are `None`, all tracked listeners are
        removed.
        """
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
        """Remove all tracked event listeners from this element."""
        for rec in self._event_listeners:
            self.element.removeEventListener(rec["type"], rec["proxy"])
        self._event_listeners.clear()

    @classmethod
    def query(cls, selector: str, within: Optional["Element"] = None) -> Optional["Element"]:
        """Query a single element by CSS selector.

        Args:
            selector: CSS selector string.
            within: Optional parent `Element` to scope the query to.
                Defaults to `document`.

        Returns:
            The first matching `Element`, or `None` if no node matches.
        """
        ctx = within.element if within is not None else document
        node = ctx.querySelector(selector)
        if node is None:
            return None
        return cls(node=node)

    @classmethod
    def query_all(cls, selector: str, within: Optional["Element"] = None) -> List["Element"]:
        """Query all matching elements by CSS selector.

        Args:
            selector: CSS selector string.
            within: Optional parent `Element` to scope the query to.
                Defaults to `document`.

        Returns:
            A list of wrapped `Element` instances (possibly empty).
        """
        ctx = within.element if within is not None else document
        nodes = ctx.querySelectorAll(selector)
        return [cls(node=n) for n in nodes]

    def find(self, selector: str) -> Optional["Element"]:
        """Return the first matching descendant `Element`, or `None`."""
        node = self.element.querySelector(selector)
        return Element(node=node) if node is not None else None

    def find_all(self, selector: str) -> List["Element"]:
        """Return all matching descendant elements as a list."""
        nodes = self.element.querySelectorAll(selector)
        return [Element(node=n) for n in nodes]

    def attach_ref(self, ref: "Ref") -> None:
        """Store this element on `ref.current`."""
        ref.current = self


class Ref:
    """Mutable container holding a reference to an [`Element`][wybthon.Element].

    Instantiate with `Ref()` and pass to elements via the `ref=` prop. After
    mount, `ref.current` points at the wrapped element; after unmount, it
    is reset to `None`.

    Example:
        ```python
        from wybthon import Ref, on_mount
        from wybthon.html import input_

        input_ref = Ref()

        def focus_on_mount():
            on_mount(lambda: input_ref.current and input_ref.current.element.focus())

        input_(type="text", ref=input_ref)
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty ref pointing at `None`."""
        self.current: Optional[Element] = None
