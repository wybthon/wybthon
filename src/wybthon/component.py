"""Component base class for class-based VDOM components."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List

if TYPE_CHECKING:
    from .vdom import VNode

__all__ = ["Component"]


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
