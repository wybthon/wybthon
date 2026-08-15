"""Application runtime, owned render mounts, and lifecycle diagnostics.

Each ``Runtime`` owns its container mounts instead of relying on process-wide
renderer registries. The default ``wybthon.render`` entry point uses one
runtime, while tests, embedded widgets, and multi-document applications may
create isolated runtimes explicitly.
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING, Any, Dict, Optional, Type

from .reactivity import Owner

if TYPE_CHECKING:
    from .dom import Element

__all__ = ["MountHandle", "Runtime", "create_runtime"]


class MountHandle:
    """Owned application mount returned by ``render``.

    Attributes:
        element: Container element receiving the rendered tree.
        container_id: Kernel node ID of ``element``.
        disposed: Whether the mount and all owned reactive work have been
            disposed.
    """

    __slots__ = ("element", "container_id", "_runtime", "_root_owner", "_mounted", "disposed")

    def __init__(self, runtime: "Runtime", element: "Element", root_owner: Owner) -> None:
        self.element = element
        self.container_id = element.node_id
        self._runtime = runtime
        self._root_owner = root_owner
        self._mounted: Any = None
        self.disposed = False

    def update(self, vnode: Any) -> "MountHandle":
        """Patch this mount with ``vnode`` and return the same handle."""
        if self.disposed:
            raise RuntimeError("can't update a disposed Wybthon mount")
        from .reconciler import _update_handle

        _update_handle(self, vnode)
        return self

    def dispose(self) -> None:
        """Unmount the tree and dispose every owner and async task."""
        if self.disposed:
            return
        from .reconciler import _dispose_handle

        _dispose_handle(self)

    def __enter__(self) -> "MountHandle":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.dispose()


class Runtime:
    """Isolated collection of application mounts and renderer state."""

    __slots__ = ("_mounts",)

    def __init__(self) -> None:
        self._mounts: Dict[int, MountHandle] = {}

    def render(self, vnode: Any, container: Any) -> MountHandle:
        """Mount or patch ``vnode`` in ``container``.

        Re-rendering into a container already owned by this runtime updates
        and returns its existing handle.
        """
        from .reconciler import _coerce_container, _create_handle

        element = _coerce_container(container)
        existing = self._mounts.get(element.node_id)
        if existing is not None and not existing.disposed:
            return existing.update(vnode)
        handle = _create_handle(self, element, vnode)
        self._mounts[element.node_id] = handle
        return handle

    def dispose(self) -> None:
        """Dispose all mounts owned by this runtime."""
        for handle in list(self._mounts.values()):
            handle.dispose()

    def stats(self) -> Dict[str, int]:
        """Return live mount, mounted-node, owner, and task counts."""
        from .reconciler import _mounted_node_count

        mounted_nodes = sum(_mounted_node_count(handle._mounted) for handle in self._mounts.values())
        owners = sum(_owner_count(handle._root_owner) for handle in self._mounts.values())
        tasks = sum(_task_count(handle._root_owner) for handle in self._mounts.values())
        return {
            "mounts": len(self._mounts),
            "mounted_nodes": mounted_nodes,
            "owners": owners,
            "tasks": tasks,
        }

    def _forget(self, handle: MountHandle) -> None:
        current = self._mounts.get(handle.container_id)
        if current is handle:
            del self._mounts[handle.container_id]


def _owner_count(owner: Owner) -> int:
    children = owner._children.values() if owner._children else ()
    return 1 + sum(_owner_count(child) for child in children)


def _task_count(owner: Owner) -> int:
    count = len(owner._tasks) if owner._tasks else 0
    children = owner._children.values() if owner._children else ()
    return count + sum(_task_count(child) for child in children)


def create_runtime() -> Runtime:
    """Create an isolated Wybthon application runtime."""
    return Runtime()
