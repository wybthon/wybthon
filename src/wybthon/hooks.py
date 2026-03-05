"""React-style hooks for function components.

Hooks let function components hold state, run side effects, and memoize
values without converting to class components.  They work by maintaining
a per-component-instance list of hook slots, accessed by call order.

**Rules of hooks** (same as React):

1. Only call hooks at the top level of a function component.
2. Do not call hooks inside loops, conditions, or nested functions.
3. Do not call hooks outside of a function component's render.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, List, Optional, Tuple, TypeVar, Union

from .reactivity import Signal, signal

__all__ = [
    "use_state",
    "use_effect",
    "use_layout_effect",
    "use_memo",
    "use_ref",
    "use_callback",
    "use_reducer",
    "HookRef",
]

T = TypeVar("T")

_hooks_stack: List["_HooksContext"] = []


class HookRef(Generic[T]):
    """Mutable container returned by ``use_ref``."""

    __slots__ = ("current",)

    def __init__(self, initial: T = None) -> None:
        self.current: T = initial


class _HooksContext:
    """Internal per-component-instance hook-state manager.

    Created once when a function component is first mounted and reused
    across every subsequent re-render of that component instance.
    """

    __slots__ = (
        "states",
        "cursor",
        "effect_queue",
        "effect_cursor",
        "layout_effect_queue",
        "layout_effect_cursor",
        "_is_mounting",
        "_props",
        "_component_fn",
    )

    def __init__(self) -> None:
        self.states: List[Any] = []
        self.cursor: int = 0
        self.effect_queue: List[dict] = []
        self.effect_cursor: int = 0
        self.layout_effect_queue: List[dict] = []
        self.layout_effect_cursor: int = 0
        self._is_mounting: bool = True
        self._props: dict = {}
        self._component_fn: Any = None

    def _run_pending_layout_effects(self) -> None:
        """Execute layout effects synchronously after DOM mutation."""
        for eff in self.layout_effect_queue:
            pending_fn = eff.get("pending")
            if pending_fn is None:
                continue
            old_cleanup = eff.get("cleanup")
            if callable(old_cleanup):
                try:
                    old_cleanup()
                except Exception:
                    pass
            try:
                result = pending_fn()
                eff["cleanup"] = result if callable(result) else None
            except Exception:
                eff["cleanup"] = None
            eff["pending"] = None

    def _run_pending_effects(self) -> None:
        """Execute effects that were scheduled during the render pass."""
        self._run_pending_layout_effects()
        for eff in self.effect_queue:
            pending_fn = eff.get("pending")
            if pending_fn is None:
                continue
            old_cleanup = eff.get("cleanup")
            if callable(old_cleanup):
                try:
                    old_cleanup()
                except Exception:
                    pass
            try:
                result = pending_fn()
                eff["cleanup"] = result if callable(result) else None
            except Exception:
                eff["cleanup"] = None
            eff["pending"] = None

    def _cleanup_all(self) -> None:
        """Run every effect cleanup (called on unmount)."""
        for eff in self.layout_effect_queue:
            cleanup = eff.get("cleanup")
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    pass
        self.layout_effect_queue.clear()
        for eff in self.effect_queue:
            cleanup = eff.get("cleanup")
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    pass
        self.effect_queue.clear()


def _push_hooks_ctx(ctx: _HooksContext) -> None:
    _hooks_stack.append(ctx)


def _pop_hooks_ctx() -> None:
    if _hooks_stack:
        _hooks_stack.pop()


def _get_hooks_ctx() -> _HooksContext:
    if not _hooks_stack:
        raise RuntimeError(
            "Hooks can only be called inside a function component during rendering. "
            "Make sure you are not calling hooks in a class component, event handler, "
            "or outside of a component."
        )
    return _hooks_stack[-1]


def _deps_changed(prev: Optional[List[Any]], nxt: Optional[List[Any]]) -> bool:
    """Return True when two dependency lists differ (or either is None)."""
    if prev is None or nxt is None:
        return True
    if len(prev) != len(nxt):
        return True
    return any(not (a is b or a == b) for a, b in zip(prev, nxt))


# ---------------------------------------------------------------------------
# Public hooks
# ---------------------------------------------------------------------------


def use_state(initial: Union[T, Callable[[], T]]) -> Tuple[T, Callable]:
    """Declare component-local state.

    Returns ``(current_value, setter)``.  The setter accepts a plain value
    **or** an updater function::

        count, set_count = use_state(0)
        set_count(5)                   # set directly
        set_count(lambda prev: prev+1) # updater
    """
    ctx = _get_hooks_ctx()
    idx = ctx.cursor
    ctx.cursor += 1

    if idx >= len(ctx.states):
        val = initial() if callable(initial) else initial
        sig: Signal[Any] = signal(val)

        def setter(value_or_fn: Any) -> None:
            if callable(value_or_fn):
                sig.set(value_or_fn(sig._value))
            else:
                sig.set(value_or_fn)

        ctx.states.append((sig, setter))

    sig, setter = ctx.states[idx]
    return sig.get(), setter


def use_effect(
    fn: Callable[[], Optional[Callable[[], Any]]],
    deps: Optional[List[Any]] = None,
) -> None:
    """Register a side-effect that runs after render.

    * ``deps=None`` — run after **every** render.
    * ``deps=[]``   — run only on **mount** (cleanup runs on unmount).
    * ``deps=[a,b]`` — run when *a* or *b* changes.

    *fn* may return a cleanup callable.
    """
    ctx = _get_hooks_ctx()
    idx = ctx.effect_cursor
    ctx.effect_cursor += 1

    if idx >= len(ctx.effect_queue):
        ctx.effect_queue.append({"deps": list(deps) if deps is not None else None, "cleanup": None, "pending": fn})
        return

    prev = ctx.effect_queue[idx]
    prev_deps = prev.get("deps")
    new_deps = list(deps) if deps is not None else None

    if not _deps_changed(prev_deps, new_deps):
        return

    ctx.effect_queue[idx] = {"deps": new_deps, "cleanup": prev.get("cleanup"), "pending": fn}


def use_memo(fn: Callable[[], T], deps: List[Any]) -> T:
    """Memoize a computed value, recomputing only when *deps* change."""
    ctx = _get_hooks_ctx()
    idx = ctx.cursor
    ctx.cursor += 1

    if idx >= len(ctx.states):
        value = fn()
        ctx.states.append({"value": value, "deps": list(deps)})
        return value

    prev = ctx.states[idx]
    if not _deps_changed(prev["deps"], deps):
        return prev["value"]

    value = fn()
    ctx.states[idx] = {"value": value, "deps": list(deps)}
    return value


def use_ref(initial: Any = None) -> HookRef:
    """Create a mutable ref object that persists across renders."""
    ctx = _get_hooks_ctx()
    idx = ctx.cursor
    ctx.cursor += 1

    if idx >= len(ctx.states):
        ref: HookRef = HookRef(initial)
        ctx.states.append(ref)

    return ctx.states[idx]


def use_callback(fn: Callable, deps: List[Any]) -> Callable:
    """Memoize a callback, returning the same reference until *deps* change."""
    return use_memo(lambda: fn, deps)


def use_reducer(
    reducer: Callable[[Any, Any], Any],
    initial_state: Any,
    init: Optional[Callable[[Any], Any]] = None,
) -> Tuple[Any, Callable[[Any], None]]:
    """Manage state with a reducer function.

    Returns ``(state, dispatch)``.  Call ``dispatch(action)`` to run
    ``reducer(current_state, action)`` and update the component.

    The optional *init* function lazily computes the initial state as
    ``init(initial_state)`` on the first render.
    """
    ctx = _get_hooks_ctx()
    idx = ctx.cursor
    ctx.cursor += 1

    if idx >= len(ctx.states):
        val = init(initial_state) if init is not None else initial_state
        sig: Signal[Any] = signal(val)

        def dispatch(action: Any) -> None:
            sig.set(reducer(sig._value, action))

        ctx.states.append((sig, dispatch, reducer))

    sig_stored, dispatch_stored, _ = ctx.states[idx]
    return sig_stored.get(), dispatch_stored


def use_layout_effect(
    fn: Callable[[], Optional[Callable[[], Any]]],
    deps: Optional[List[Any]] = None,
) -> None:
    """Register an effect that fires synchronously after DOM mutations.

    Same API as ``use_effect`` but guaranteed to run before the browser
    repaints.  Use for DOM measurements and synchronous visual updates.

    * ``deps=None`` — run after **every** render.
    * ``deps=[]``   — run only on **mount**.
    * ``deps=[a,b]`` — run when *a* or *b* changes.

    *fn* may return a cleanup callable.
    """
    ctx = _get_hooks_ctx()
    idx = ctx.layout_effect_cursor
    ctx.layout_effect_cursor += 1

    if idx >= len(ctx.layout_effect_queue):
        ctx.layout_effect_queue.append(
            {"deps": list(deps) if deps is not None else None, "cleanup": None, "pending": fn}
        )
        return

    prev = ctx.layout_effect_queue[idx]
    prev_deps = prev.get("deps")
    new_deps = list(deps) if deps is not None else None

    if not _deps_changed(prev_deps, new_deps):
        return

    ctx.layout_effect_queue[idx] = {"deps": new_deps, "cleanup": prev.get("cleanup"), "pending": fn}
