"""Actions, optimistic state, and the transaction helpers `affects` and `until`.

An [`action`][wybthon.action] wraps a mutation (usually `async def`) in
a **transaction**: the action holds a transition open for as long as it
runs, so the signals and stores it writes, and the memos it
[`refresh`][wybthon.refresh]es, land together when it settles. Values
written through [`create_optimistic`][wybthon.create_optimistic] and
[`create_optimistic_store`][wybthon.create_optimistic_store] are the
exception: they reveal immediately and revert when the transaction
settles, by which time the real data reflects the server's answer.

Process state that has to be visible *during* the action (a "saving"
flag, a disabled button) is therefore co-written optimistic state, not
a plain signal write; `action.pending` covers the common case.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable as AbcAwaitable
from collections.abc import Callable
from typing import Any, cast, overload

from . import _core
from ._core import Accessor, Computation, Memo, Owner, Signal, Transition, untrack
from ._primitives import Setter, _Settle

__all__ = ["Action", "action", "create_optimistic", "affects", "until"]


def _register_optimistic_revert(fn: Callable[[], None]) -> None:
    """Run `fn` when the current transaction settles.

    Inside an action that's the action's dependency group; otherwise the
    next transition to open adopts the callback.
    """
    tx = _core._in_action
    if tx is not None:
        tx.root().reverts.append(fn)
    else:
        _core._ambient_reverts.append(fn)


async def _await(awaitable: AbcAwaitable[Any]) -> Any:
    return await awaitable


class Action[**P, R]:
    """A wrapped mutation returned by [`action`][wybthon.action].

    Calling it invokes the wrapped function inside a transaction. The
    `pending` accessor is `True` while any invocation is in flight; it
    reveals immediately, so it's the right thing to bind a disabled
    button or a spinner to.
    """

    __slots__ = ("_fn", "_count", "pending", "__name__", "__qualname__")

    def __init__(self, fn: Callable[P, Any]) -> None:
        self._fn = fn
        self._count: Signal[int] = Signal(0)
        count = self._count
        self.pending: Accessor[bool] = _core.run_with_owner(None, lambda: Memo(lambda: count() > 0))
        """Tracked accessor: `True` while an invocation is in flight."""
        name = getattr(fn, "__name__", "action")
        self.__name__ = name
        self.__qualname__ = getattr(fn, "__qualname__", name)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        owner = _core._current_owner
        tx = _core._in_action.root() if _core._in_action is not None else _core._new_transition()
        tx.holds += 1
        prev_action = _core._in_action
        _core._in_action = tx
        try:
            result = _core.run_with_owner(owner, lambda: untrack(lambda: self._fn(*args, **kwargs)))
        except BaseException:
            tx.root().holds -= 1
            _core._schedule_flush()
            raise
        finally:
            _core._in_action = prev_action
        if not isinstance(result, AbcAwaitable):
            # A synchronous action: its writes were staged as held and
            # reveal in the flush that commits them.
            tx.root().holds -= 1
            _core._schedule_flush()
            return result

        count = self._count
        count._set(count._latest() + 1, _core._O_REVEAL)
        future: asyncio.Future[Any] = _core._event_loop().create_future()

        settled = False

        def settle() -> None:
            nonlocal settled
            if settled:
                return
            settled = True
            count._set(count._latest() - 1, _core._O_REVEAL)
            tx.root().holds -= 1
            _core._schedule_flush()

        def on_done(value: Any) -> None:
            settle()
            if not future.done():
                future.set_result(value)

        def on_error(exc: BaseException) -> None:
            settle()
            if isinstance(exc, asyncio.CancelledError):
                future.cancel()
                return
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
        task = _core._drive_coroutine(
            coro,
            owner=owner,
            observer=None,
            alive=lambda: True,
            on_done=on_done,
            on_error=on_error,
            action_tx=tx,
        )

        def cancel_task(done: asyncio.Future[Any]) -> None:
            if done.cancelled() and not task.done():
                task.cancel()

        future.add_done_callback(cancel_task)
        return cast(R, future)

    def __repr__(self) -> str:
        return f"Action({self.__name__})"


@overload
def action[**P, R](fn: Callable[P, AbcAwaitable[R]]) -> Action[P, asyncio.Future[R]]: ...


@overload
def action[**P, R](fn: Callable[P, R]) -> Action[P, R]: ...


def action(fn: Callable[..., Any]) -> Action:
    """Wrap a mutation in a transaction.

    Calling the returned [`Action`][wybthon.Action] invokes `fn` and
    holds a transition open until it settles. Inside:

    - **Plain writes stage into the transaction.** Signals and stores
      written by the action (before or after an `await`) commit to the
      graph but reveal together when the action settles, as does the
      landing of any memo it [`refresh`][wybthon.refresh]es. Reads
      inside the action see the staged values.
    - **Optimistic writes reveal now.** Values written through
      [`create_optimistic`][wybthon.create_optimistic] or
      [`create_optimistic_store`][wybthon.create_optimistic_store]
      show immediately and revert when the action settles.
    - `action.pending()` is `True` from the call until it settles;
      [`affects`][wybthon.affects] marks other values as pending, and
      [`until`][wybthon.until] waits for a condition on the
      authoritative view.

    Independent actions settle separately. Nested actions and actions that
    write shared reactive state join and publish together.

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
        shown, set_shown = create_optimistic_store(lambda: deep(todos)["items"], [])

        @action
        async def add_todo(title):
            set_shown(lambda s: s.append({"title": title, "saving": True}))
            saved = await api_create(title)
            set_todos(lambda s: s["items"].append(saved))
        ```
    """
    return Action(fn)


class _Optimistic[T](Accessor[T]):
    """Ordered optimistic operations, each owned by the submitting action."""

    __slots__ = ("_source", "_edits")

    def __init__(self, source: Callable[[], T]) -> None:
        self._source = source
        self._edits: Signal[tuple[Any, ...]] = Signal(())

    def _value(self, edits: tuple[Any, ...]) -> T:
        # Overrides publish immediately, even if their authoritative base is
        # held. Register escape edges so that it can rebase while held.
        if edits:
            _core._latest_depth += 1
        try:
            value = self._source()
        finally:
            if edits:
                _core._latest_depth -= 1
        for _, modifier in edits:
            value = modifier(value) if callable(modifier) else modifier
        return value

    def __call__(self) -> T:
        if _core._authoritative_depth:
            return self._source()
        edits = self._edits()
        if edits and _core._probe_depth:
            _core._probe_mark()
        return self._value(edits)

    def peek(self) -> T:
        return untrack(self)

    def set(self, value: T | Callable[[T], T]) -> T:
        token = object()
        edits = (*self._edits._latest(), (token, value))
        result = untrack(lambda: self._value(edits))
        self._edits._set(edits, _core._O_REVEAL)

        def revert() -> None:
            remaining = tuple(edit for edit in self._edits._latest() if edit[0] is not token)
            self._edits._set(remaining, _core._O_REVEAL)

        _register_optimistic_revert(revert)
        return result

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
    value. Writes reveal immediately, even inside an
    [`action`][wybthon.action] whose other writes are held, and the
    override reverts when the transaction it was written in settles.
    While an override is active, [`is_pending`][wybthon.is_pending]
    reports `True` for expressions that read it, and
    [`until`][wybthon.until] sees through it to the source.

    Use it both for optimistic *data* (the like count you expect the
    server to confirm) and for process *state* that must show during an
    action (a "saving" flag).

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
            await api_like()
            await refresh(likes)                # real data lands; the override reverts
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


# ---------------------------------------------------------------------------
# affects / until
# ---------------------------------------------------------------------------


def _affect_node(target: Any) -> Any:
    hook = getattr(target, "_wyb_affect_node", None)
    if hook is not None:
        return hook()
    if isinstance(target, _Optimistic):
        target = target._source
    if isinstance(target, (Signal, Computation)):
        return target
    raise TypeError(f"affects() expects signals, memos, or stores, got {target!r}")


def affects(*targets: Any) -> None:
    """Declare, inside an action, which values the action is going to change.

    Until the action settles, [`is_pending`][wybthon.is_pending] reports
    `True` for expressions that read any of `targets`, even before the
    action has written anything. Use it when the pending state should
    show on the *data* being changed rather than on the action itself,
    for example to dim a record while a save is in flight.

    Args:
        *targets: Signals, memos, or stores (a store proxy marks the
            selected subtree).

    Raises:
        RuntimeError: If called outside an action's synchronous segment.
        TypeError: For a target that isn't a reactive node or store.

    Example:
        ```python
        @action
        async def rename(user_id, name):
            affects(users)
            await api_rename(user_id, name)
            refresh(users)
        ```
    """
    tx: Transition | None = _core._in_action
    if tx is None:
        raise RuntimeError("affects() must be called inside an action")
    for target in targets:
        node = _affect_node(target)
        tx.root().affected.add(node)
        if isinstance(node, (Signal, Computation)):
            for observer in node._observers or ():
                if (observer._sources or {}).get(node, 0) & _core._R_PROBE:
                    observer._stale(_core._DIRTY)
        else:
            node._notify()
    _core._update_slow_reads()


def until[T](pred: Callable[[], T], *, timeout: float | None = None) -> _Settle[T]:
    """Return an awaitable for the settled, truthy value of `pred()`.

    `pred` is evaluated reactively against the **authoritative** view:
    optimistic overrides are invisible, so the condition observes real
    data only. Inside an action, reads see the action's own staged
    writes. A read that raises [`NotReadyError`][wybthon.NotReadyError]
    simply waits for the value.

    Args:
        pred: Zero-arg predicate.
        timeout: Optional seconds after which the awaitable rejects with
            `TimeoutError`.

    Example:
        ```python
        @action
        async def checkout(cart_id):
            order_id = await api_checkout(cart_id)
            refresh(orders)
            await until(lambda: any(o["id"] == order_id for o in orders()))
            navigate(f"/orders/{order_id}")
        ```
    """
    return _Settle(pred, truthy=True, authoritative=True, timeout=timeout)
