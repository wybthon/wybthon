"""Component base classes for class-based VDOM components."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from .vdom import VNode

from .dom import Element

__all__ = ["BaseComponent", "Component"]


class BaseComponent(ABC):
    """Async component base that renders to a concrete DOM `Element`."""

    def __init__(self, children: Optional[List["BaseComponent"]] = None) -> None:
        self.children = children or []

    @abstractmethod
    async def render(self) -> Element:
        """Render this component and return its root `Element`."""

    async def render_children(self, parent: Element) -> None:
        """Render and append all child components to the given parent element."""
        for child in self.children:
            child_element = await child.render()
            parent.element.appendChild(child_element.element)


class Component:
    """Class component base for the VDOM renderer.

    Subclasses should implement `render(self) -> VNode`.
    Lifecycle hooks:
      - on_mount(self)
      - on_update(self, prev_props: dict)
      - on_unmount(self)
    """

    def __init__(self, props: Dict[str, Any]) -> None:
        self.props = props
        self._cleanups: List[Callable[[], Any]] = []

    def render(self) -> "VNode":
        raise NotImplementedError

    # Lifecycle hooks
    def on_mount(self) -> None:  # noqa: D401
        """Called after the component is first mounted."""
        pass

    def on_update(self, prev_props: Dict[str, Any]) -> None:  # noqa: D401
        """Called after props update and render diff applied."""
        pass

    def on_unmount(self) -> None:  # noqa: D401
        """Called before the component is removed from the DOM."""
        pass

    # --------------- Cleanup management ---------------
    def add_cleanup(self, fn: Callable[[], Any]) -> None:
        """Register a cleanup callback to run on unmount."""
        self._cleanups.append(fn)

    # Alias for ergonomics
    on_cleanup = add_cleanup

    def _run_cleanups(self) -> None:
        """Run and clear all registered cleanup callbacks safely."""
        while self._cleanups:
            fn = self._cleanups.pop()
            try:
                fn()
            except Exception:
                # Swallow cleanup errors to avoid breaking render pipeline
                pass
