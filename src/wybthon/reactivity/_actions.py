"""Actions and optimistic state.

An [`action`][wybthon.action] wraps a mutation (usually `async def`) so
the graph knows while it's in flight. Values written through
[`create_optimistic`][wybthon.create_optimistic] and
[`create_optimistic_store`][wybthon.create_optimistic_store] stay
applied while any action is in flight and revert automatically when the
last one settles, by which time the real data (a store the action
reconciled, or a memo it [`refresh`][wybthon.refresh]ed) reflects the
server's answer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable as AbcAwaitable
from collections.abc import Callable
from typing import Any, overload

from .._warnings import log_error
from . import _core
from ._core import _MISSING, Accessor, Memo, Owner, Signal, untrack
from ._primitives import Setter

__all__ = ["Action", "action", "create_optimistic"]

# Number of in-flight actions. When it drops to zero every registered
# optimistic revert runs.
_inflight: int = 0
_reverts: list[Callable[[], None]] = []


def _register_optimistic_revert(fn: Callable[[], None]) -> None:
    _reverts.append(fn)


def _on_action_settled() -> None:
    global _inflight
    _inflight -= 1
    if _inflight <= 0:
        _inflight = 0
        reverts = list(_reverts)
        _reverts.clear()
        for fn in reverts:
            try:
                fn()
            except Exception as exc:
                log_error(f"Optimistic revert raised: {exc}", exc)
    _core._schedule_flush()


async def _await(awaitable: AbcAwaitable[Any]) -> Any:
    return await awaitable


class Action:
    """A wrapped mutation returned by [`action`][wybthon.action].

    Calling it invokes the wrapped function. The `pending` accessor is
    `True` while any invocation is in flight.
    """

    __slots__ = ("_fn", "_count", "pending", "__name__", "__qualname__")

    def __init__(self, fn: Callable[..., Any]) -> None:
        self._fn = fn
        self._count: Signal[int] = Signal(0)
        count = self._count
        self.pending: Accessor[bool] = _core.run_with_owner(None, lambda: Memo(lambda: count() > 0))
        """Tracked accessor: `True` while an invocation is in flight."""
        name = getattr(fn, "__name__", "action")
        self.__name__ = name
        self.__qualname__ = getattr(fn, "__qualname__", name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        owner = _core._current_owner
        result = _core.run_with_owner(owner, lambda: untrack(lambda: self._fn(*args, **kwargs)))
        if not isinstance(result, AbcAwaitable):
            return result

        global _inflight
        _inflight += 1
        count = self._count
        count._set(count._latest() + 1)
        future: asyncio.Future[Any] = _core._event_loop().create_future()

        def settle() -> None:
            count._set(count._latest() - 1)
            _on_action_settled()

        def on_done(value: Any) -> None:
            settle()
            if not future.done():
                future.set_result(value)

        def on_error(exc: BaseException) -> None:
            settle()
            scope: Owner | None = owner
            while scope is not None:
                handler = scope._error_handler
                if handler is not None:
                    try:
                        handler(exc, None)
                    except Exception:
                        pass
                    break
                scope = scope._parent
            if not future.done():
                if isinstance(exc, Exception):
                    future.set_exception(exc)
                else:
                    raise exc

        coro = result if asyncio.iscoroutine(result) else _await(result)
        # Run synchronously up to the first ``await`` so optimistic writes
        # made at the top of the action apply immediately.
        _core._drive_coroutine(coro, owner=owner, observer=None, alive=lambda: True, on_done=on_done, on_error=on_error)
        return future

    def __repr__(self) -> str:
        return f"Action({self.__name__})"


def action(fn: Callable[..., Any]) -> Action:
    """Wrap a mutation so the graph can track its in-flight state.

    Calling the returned [`Action`][wybthon.Action] invokes `fn`; when
    `fn` returns an awaitable it's scheduled as a task and the action
    counts as **in flight** until it settles. While any action is in
    flight, `action.pending()` is `True` and values written through
    [`create_optimistic`][wybthon.create_optimistic] or
    [`create_optimistic_store`][wybthon.create_optimistic_store] stay
    applied; they revert when the last action settles.

    Errors route to the nearest [`Errored`][wybthon.Errored] boundary
    captured at call time and re-raise to the awaiter, so
    `await my_action(...)` behaves like a normal call.

    Args:
        fn: The mutation; sync or `async def`.

    Returns:
        A callable `Action` with a tracked `.pending` accessor.

    Example:
        ```python
        todos, set_todos = create_store({"items": []})
        shown, set_shown = create_optimistic_store(lambda: snapshot(todos)["items"], [])

        @action
        async def add_todo(title):
            set_shown(lambda s: s.append({"title": title, "saving": True}))
            saved = await api_create(title)
            set_todos(lambda s: s.items.append(saved))
        ```
    """
    return Action(fn)


class _Optimistic[T](Accessor[T]):
    """Accessor returned by `create_optimistic`: an override that shadows a source."""

    __slots__ = ("_source", "_override")

    def __init__(self, source: Callable[[], T]) -> None:
        self._source = source
        self._override: Signal[Any] = Signal(_MISSING)

    def __call__(self) -> T:
        ov = self._override()
        if ov is not _MISSING:
            if _core._pending_probe:
                _core._pending_probe[-1] = True
            return ov
        return self._source()

    def peek(self) -> T:
        ov = self._override.peek()
        if ov is not _MISSING:
            return ov
        return untrack(self._source)

    def _revert(self) -> None:
        self._override._set(_MISSING)

    def set(self, value: T | Callable[[T], T]) -> T:
        if callable(value):
            current = self._override._latest()
            if current is _MISSING:
                current = untrack(self._source)
            value = value(current)
        self._override._set(value)
        _register_optimistic_revert(self._revert)
        return value

    def _label(self) -> str:
        return "an optimistic value"


@overload
def create_optimistic[T](source: Accessor[T]) -> tuple[Accessor[T], Setter[T]]: ...


@overload
def create_optimistic[T](source: Callable[[], T]) -> tuple[Accessor[T], Setter[T]]: ...


@overload
def create_optimistic[T](source: T) -> tuple[Accessor[T], Setter[T]]: ...


def create_optimistic(source: Any) -> tuple[Accessor[Any], Setter[Any]]:
    """Create a value whose writes are **optimistic**.

    Reads return the override while one is active, else the source
    value. Overrides revert automatically when every in-flight
    [`action`][wybthon.action] has settled. While an override is
    active, [`is_pending`][wybthon.is_pending] reports `True` for
    expressions that read it.

    Args:
        source: A zero-arg accessor to shadow, or a plain initial value.

    Returns:
        A `(getter, setter)` pair like [`create_signal`][wybthon.create_signal].

    Example:
        ```python
        likes = create_memo(fetch_like_count)          # async source
        shown, set_shown = create_optimistic(likes)     # shadows it

        @action
        async def like():
            set_shown(lambda n: (n or 0) + 1)   # instant UI
            await api_like()                    # reverts to real data on settle
            refresh(likes)
        ```
    """
    if callable(source) and _core._positional_count(source) == 0:
        getter: Callable[[], Any] = source
    else:
        static = source

        def getter() -> Any:
            return static

    opt: _Optimistic[Any] = _Optimistic(getter)
    return opt, opt.set
