"""Public reactive primitives built on the core graph.

Everything here is re-exported from `wybthon`. The functions are thin:
they construct [`Signal`][wybthon.Signal], [`Memo`][wybthon.Memo], and
[`Computation`][wybthon.reactivity.Computation] nodes from
`wybthon.reactivity._core` and register them with the active owner.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Generator
from typing import Any, Protocol, overload

from . import _core
from ._core import (
    _DEFAULT_EQUALS,
    _K_EFFECT,
    _K_RENDER,
    Accessor,
    Computation,
    Memo,
    NotReadyError,
    Owner,
    Signal,
    _changed,
    _positional_count,
    _schedule_flush,
    untrack,
)

__all__ = [
    "Setter",
    "create_signal",
    "create_memo",
    "create_effect",
    "create_render_effect",
    "on_settled",
    "on_cleanup",
    "create_root",
    "refresh",
    "resolve",
    "is_pending",
    "latest",
    "create_unique_id",
    "children",
]


class Setter[T](Protocol):
    """The write half of [`create_signal`][wybthon.create_signal].

    Call it with a new value, or with an updater `(current) -> new` for a
    functional update. Returns the value that was staged.
    """

    def __call__(self, value: T | Callable[[T], T], /) -> T: ...


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


class _WritableMemo[T](Memo[T]):
    """A derived signal that can also be written (the `create_signal(fn)` form)."""

    __slots__ = ("_pending", "_staged")

    def __init__(self, fn: Callable[..., T], *, equals: Any) -> None:
        super().__init__(fn, equals=equals)
        self._pending: Any = None
        self._staged: bool = False

    def set(self, value: T | Callable[[T], T]) -> T:
        if _core._current_observer is not None and _core._warnings.DEV_MODE:
            raise _core.WriteInScopeError(
                "Cannot write a derived signal inside a tracking scope. Write it from an event "
                "handler, an action, or the apply stage of a split create_effect."
            )
        if callable(value):
            current = self._pending if self._staged else self.peek()
            value = value(current)
        if self._staged:
            self._pending = value
        else:
            self._pending = value
            self._staged = True
            _core._staged.append(self)  # type: ignore[arg-type]
            _schedule_flush()
        return value

    def _commit(self) -> None:
        if not self._staged:
            return
        self._staged = False
        new = self._pending
        self._pending = None
        if not _changed(self._equals, self._value, new):
            return
        self._first = False
        self._value = new
        obs = self._observers
        if obs:
            for o in list(obs):
                o._stale(_core._DIRTY)


def create_signal[T](
    value: T | Callable[[], T],
    *,
    equals: Any = _DEFAULT_EQUALS,
    name: str | None = None,
) -> tuple[Accessor[T], Setter[T]]:
    """Create a reactive signal and return its `(getter, setter)` pair.

    Writes are **staged**: the setter records the new value and every
    read keeps returning the committed value until the next flush (a
    browser microtask, the end of an event handler, or an explicit
    [`flush`][wybthon.flush]). There is no `batch()`; everything
    batches.

    The setter supports **functional updates**: pass `lambda n: n + 1`
    and it receives the latest staged value, so repeated updates in one
    handler compose. To store a callable as the value, wrap it:
    `set_fn(lambda _: my_callable)`.

    **Function form.** When `value` is a zero-argument callable, the
    result is a *writable derived signal*: the getter tracks whatever
    the function reads and recomputes when those sources change, while
    the setter overrides the value until the next source change.

    Args:
        value: The initial value, or a zero-arg function for the
            derived form.
        equals: Equality policy deciding when subscribers are notified:

            - default: identity fast path, then `==`. Re-setting an
              equal value is a no-op.
            - `False`: always notify, even for equal values.
            - a callable `(old, new) -> bool`: skip notification when it
              returns `True`. Pass `lambda a, b: a is b` for
              identity-only semantics.
        name: Optional label used in dev-mode diagnostics.

    Returns:
        A `(getter, setter)` tuple. The getter is an
        [`Accessor`][wybthon.Accessor] (call it to read, `.peek()` to
        read untracked); the setter is a [`Setter`][wybthon.Setter].

    Example:
        ```python
        count, set_count = create_signal(0)
        set_count(5)
        count()                     # 0: staged, not yet visible
        flush()
        count()                     # 5
        set_count(lambda n: n + 1)  # functional update
        count.peek()                # 5 (untracked read of the committed value)

        doubled, _ = create_signal(lambda: count() * 2)   # derived form
        ```
    """
    if callable(value) and _positional_count(value) == 0:
        derived: _WritableMemo[T] = _WritableMemo(value, equals=equals)
        return derived, derived.set
    sig: Signal[T] = Signal(value, equals=equals, name=name)  # type: ignore[arg-type]
    return sig, sig.set


# ---------------------------------------------------------------------------
# Memos
# ---------------------------------------------------------------------------


@overload
def create_memo[T](
    fn: Callable[..., AsyncIterator[T]],
    *,
    equals: Any = ...,
    lazy: bool = ...,
    unobserved: Callable[[], Any] | None = ...,
    name: str | None = ...,
) -> Memo[T]: ...


@overload
def create_memo[T](
    fn: Callable[..., Awaitable[T]],
    *,
    equals: Any = ...,
    lazy: bool = ...,
    unobserved: Callable[[], Any] | None = ...,
    name: str | None = ...,
) -> Memo[T]: ...


@overload
def create_memo[T](
    fn: Callable[..., T],
    *,
    equals: Any = ...,
    lazy: bool = ...,
    unobserved: Callable[[], Any] | None = ...,
    name: str | None = ...,
) -> Memo[T]: ...


def create_memo(
    fn: Callable[..., Any],
    *,
    equals: Any = _DEFAULT_EQUALS,
    lazy: bool = False,
    unobserved: Callable[[], Any] | None = None,
    name: str | None = None,
) -> Memo[Any]:
    """Create a derived value that recomputes when its sources change.

    Memos are **pull-based**: the body runs when the memo is read after
    a tracked source changed, and observers are notified only when the
    new value differs under `equals`. If `fn` accepts a positional
    parameter it receives the previous value (`None` on the first run).

    **Async memos.** When `fn` is an `async def` (or returns an
    awaitable), the memo becomes an async computation: reading it
    before the first value raises
    [`NotReadyError`][wybthon.NotReadyError], which the nearest
    [`Loading`][wybthon.Loading] boundary turns into fallback UI. Once
    it has a value, reads during a recompute return the previous value
    (stale while revalidating); use [`is_pending`][wybthon.is_pending]
    to show a refresh hint. Reads after an `await` are tracked exactly
    like reads before it.

    **Async generators.** An `async def` body containing `yield`
    streams: each yielded value becomes the memo's new value. Use it
    to adapt sockets, subscriptions, or any async iterable.

    Args:
        fn: Zero- or one-arg callable producing the value (sync, async,
            or an async generator).
        equals: Equality policy; see [`create_signal`][wybthon.create_signal].
        lazy: When `True`, the memo disposes itself once it loses its
            last subscriber (and recomputes fresh if read again later).
            Non-lazy memos live for their owner's lifetime.
        unobserved: Optional callback fired when the memo loses its last
            subscriber; pair it with `lazy=True` for resource cleanup.
        name: Optional label used in dev-mode diagnostics.

    Returns:
        A [`Memo`][wybthon.Memo] accessor.

    Example:
        ```python
        doubled = create_memo(lambda: count() * 2)

        async def load_user():
            uid = user_id()          # tracked: refetches when it changes
            return await fetch_json(f"/api/users/{uid}")

        user = create_memo(load_user)
        ```
    """
    return Memo(fn, equals=equals, lazy=lazy, unobserved=unobserved, name=name)


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------


def create_effect(
    compute: Callable[..., Any],
    apply: Callable[..., Any] | None = None,
    *,
    defer: bool = False,
    error: Callable[[BaseException], Any] | None = None,
) -> Computation:
    """Create a side effect that re-runs when its tracked sources change.

    Effects run after the DOM has been committed, so they observe the
    updated document; the first run happens on the next flush (right
    after the component that created it has mounted), not at creation.
    Inside a component they're disposed on unmount.

    **Split form** (recommended): `compute` runs tracked and returns a
    value; `apply` runs *untracked* with `(value, prev)` and performs
    the side effect. Incidental reads inside `apply` never
    over-subscribe the effect, and signal writes belong there. `apply`
    may return a cleanup callable that runs before the next `apply` and
    on disposal.

    **Single form**: `compute` alone is both the tracking stage and the
    side effect. Signal writes inside it raise
    [`WriteInScopeError`][wybthon.WriteInScopeError] in dev mode. Use
    [`on_cleanup`][wybthon.on_cleanup] for per-run cleanup.

    If `compute` accepts a positional parameter it receives its previous
    return value (`None` on the first run). `compute` may be
    `async def`; awaits suspend the effect without blocking and reads
    after an `await` are still tracked.

    Args:
        compute: The tracked stage.
        apply: Optional untracked side-effect stage receiving
            `(value, prev)` (or just `(value,)` if it declares one
            parameter). May return a cleanup callable.
        defer: When `True`, skip the first `apply` (tracking still
            starts immediately).
        error: Optional handler receiving exceptions raised by
            `compute` (sync or async) instead of routing them to the
            nearest [`Errored`][wybthon.Errored] boundary.

    Returns:
        The underlying computation; call `.dispose()` to stop it.

    Example:
        ```python
        create_effect(count, lambda value, prev: print(prev, "->", value))

        create_effect(
            lambda: name(),
            lambda value: (timer := start_timer(value), lambda: stop_timer(timer))[1],
            defer=True,
        )
        ```
    """
    comp = Computation(compute, kind=_K_EFFECT, apply=apply, defer=defer, error=error)
    owner = _core._current_owner
    if owner is not None:
        owner._add_child(comp)
    # The first run is deferred to the effect phase of the next flush, so
    # an effect created in a component body observes the mounted DOM.
    _core._effect_queue.append(comp)
    _core._schedule_flush()
    return comp


def create_render_effect(
    compute: Callable[..., Any],
    apply: Callable[..., Any] | None = None,
    *,
    defer: bool = False,
    error: Callable[[BaseException], Any] | None = None,
) -> Computation:
    """Create an effect that runs in the **render phase**, before the DOM commit.

    Wybthon's reactive holes and prop bindings are render effects, so a
    render effect observes the DOM in the same state the framework's own
    bindings do (updates emitted, not yet committed). Prefer
    [`create_effect`][wybthon.create_effect] unless you're building a
    rendering primitive.

    Accepts the same arguments as `create_effect`.
    """
    comp = Computation(compute, kind=_K_RENDER, apply=apply, defer=defer, error=error)
    owner = _core._current_owner
    if owner is not None:
        owner._add_child(comp)
    comp._update_if_necessary()
    return comp


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def on_settled(fn: Callable[[], Any]) -> None:
    """Run `fn` once the current render has settled and committed to the DOM.

    The replacement for `on_mount`: inside a component body, `fn` runs
    after the flush that mounted the component has finished, so refs
    are assigned and the DOM is live. `fn` may return a cleanup callable,
    which runs when the owning scope is disposed (on unmount).

    Args:
        fn: Zero-arg callback. May return a cleanup callable.

    Raises:
        RuntimeError: If called outside any reactive scope.

    Example:
        ```python
        @component
        def Chart(data: Prop[list[float]]):
            canvas = Ref()

            def start():
                handle = draw(canvas.current, data.peek())
                return lambda: handle.destroy()

            on_settled(start)
            return canvas_(ref=canvas)
        ```
    """
    owner = _core._current_owner
    if owner is None:
        raise RuntimeError("on_settled() must be called inside a component or reactive scope")

    def run() -> None:
        if owner._disposed:
            return
        result = _core.run_with_owner(owner, lambda: untrack(fn))
        if callable(result):
            owner._add_cleanup(result)

    _core._settled_queue.append(run)
    _schedule_flush()


def on_cleanup(fn: Callable[[], Any]) -> None:
    """Register `fn` to run when the active scope is disposed or re-runs.

    - Inside an effect body: runs before each re-run and on disposal.
    - Inside a component body: runs when the component unmounts.
    - Inside a reactive hole or `For` row: runs when that region is
      re-evaluated or torn down.

    Raises:
        RuntimeError: If called outside any reactive scope.
    """
    owner = _core._current_owner
    if owner is None:
        raise RuntimeError("on_cleanup() must be called inside a component or reactive scope")
    owner._add_cleanup(fn)


def create_root[T](fn: Callable[[Callable[[], None]], T]) -> T:
    """Run `fn` inside a new, independent ownership root.

    Use it for long-lived reactive work that shouldn't die with the
    surrounding component (global stores, background subscriptions).

    Args:
        fn: Receives a `dispose` callable that tears the root down.

    Returns:
        Whatever `fn` returns.
    """
    root = Owner()

    def dispose() -> None:
        root.dispose()

    return _core.run_with_owner(root, lambda: fn(dispose))


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


def is_pending(fn: Callable[[], Any]) -> bool:
    """Return True while a change is in flight for the value `fn` reads.

    Evaluates `fn` in probe mode: reads of async computations report
    whether a recompute triggered by an input change is in flight
    (a quiet [`refresh`][wybthon.refresh] is silent), reads of
    optimistic values report whether an override is active, and a read
    that raises [`NotReadyError`][wybthon.NotReadyError] counts as
    pending. Tracked, so a hole using it updates as the state changes.

    ```python
    span(lambda: "Refreshing..." if is_pending(user) else "")
    ```
    """
    _core._pending_probe.append(False)
    try:
        try:
            fn()
        except NotReadyError:
            _core._pending_probe[-1] = True
        return _core._pending_probe[-1]
    finally:
        _core._pending_probe.pop()


def latest[T](fn: Callable[[], T]) -> T | None:
    """Evaluate `fn` without ever raising [`NotReadyError`][wybthon.NotReadyError].

    Not-ready async reads return their most recent value (or `None` if
    they never resolved). Use it to peek at data from outside a
    [`Loading`][wybthon.Loading] boundary.
    """
    _core._latest_depth += 1
    try:
        return fn()
    finally:
        _core._latest_depth -= 1


class _Settle[T]:
    """Awaitable that resolves when a reactive expression settles.

    The underlying future and tracking effect are created lazily on
    `await`, so a fire-and-forget [`refresh`][wybthon.refresh] costs
    nothing and works without an event loop.
    """

    __slots__ = ("_fn",)

    def __init__(self, fn: Callable[[], T]) -> None:
        self._fn = fn

    def __await__(self) -> Generator[Any, None, T]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        fn = self._fn

        def probe() -> None:
            if future.done():
                return
            try:
                value = fn()
            except NotReadyError:
                return
            except Exception as exc:
                future.set_exception(exc)
                _core._call_soon(comp.dispose)
                return
            # A quiet refresh serves the previous value while its run is in
            # flight; wait for the run to settle before resolving.
            if isinstance(fn, Computation) and fn._async is not None and fn._inflight_sig()():
                return
            future.set_result(value)
            _core._call_soon(comp.dispose)

        comp = Computation(probe, kind=_K_EFFECT, pass_prev=False)
        comp._update_if_necessary()
        if not future.done():
            _schedule_flush()
        return future.__await__()


def resolve[T](fn: Callable[[], T]) -> Awaitable[T]:
    """Return an awaitable for the next settled value of `fn()`.

    Tracks `fn` until it evaluates without raising
    [`NotReadyError`][wybthon.NotReadyError], then resolves with the
    value (or rejects with the exception `fn` raised).

    ```python
    user = create_memo(fetch_user)
    data = await resolve(user)
    ```
    """
    return _Settle(fn)


def refresh(target: Any) -> Awaitable[Any]:
    """Recompute a derived read quietly and return an awaitable for its settled value.

    "Quiet" means no pending state is reported while the run is in
    flight: [`is_pending`][wybthon.is_pending] stays `False` and
    readers keep the previous value. Use it after a server write to
    re-ask for data derived from the source of truth.

    Args:
        target: A [`Memo`][wybthon.Memo] (including async memos and
            function-form signals) or a derived store /
            projection.

    Returns:
        An awaitable resolving with the target's next settled value.
        Safe to ignore for fire-and-forget use.
    """
    hook = getattr(target, "_wyb_refresh", None)
    if hook is not None:
        hook()
        return _Settle(lambda: target)
    if isinstance(target, Memo):
        target._refresh()
        return _Settle(target)
    raise TypeError(f"refresh() expects a memo or derived store, got {target!r}")


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

_unique_id_counter: int = 0


def create_unique_id() -> str:
    """Return a process-unique id string (for `for`/`id` attribute pairs)."""
    global _unique_id_counter
    _unique_id_counter += 1
    return f"wyb-{_unique_id_counter}"


def children(fn: Callable[[], Any]) -> Memo[list[Any]]:
    """Resolve reactive children into a flat list, memoized.

    Wraps a getter that returns children (typically a `children` prop)
    and returns a memo yielding a flat list with nested lists expanded
    and `None` entries dropped.

    ```python
    from wybthon import children as resolve_children

    @component
    def Card(title: Prop[str], children: Prop[Any] = prop(None)):
        kids = resolve_children(children)
        return section(h3(title), lambda: kids())
    ```
    """

    def _resolve(val: Any) -> list[Any]:
        if val is None:
            return []
        if isinstance(val, (list, tuple)):
            out: list[Any] = []
            for item in val:
                out.extend(_resolve(item))
            return out
        return [val]

    return create_memo(lambda: _resolve(fn()))
