from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from .dom import Element


class BaseComponent(ABC):
    def __init__(self, children: Optional[List["BaseComponent"]] = None) -> None:
        self.children = children or []

    @abstractmethod
    async def render(self) -> Element:
        pass

    async def render_children(self, parent: Element) -> None:
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

    def render(self):  # -> VNode (annotated in runtime to avoid cycle)
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
        self._cleanups.append(fn)

    # Alias for ergonomics
    on_cleanup = add_cleanup

    def _run_cleanups(self) -> None:
        while self._cleanups:
            fn = self._cleanups.pop()
            try:
                fn()
            except Exception:
                # Swallow cleanup errors to avoid breaking render pipeline
                pass
