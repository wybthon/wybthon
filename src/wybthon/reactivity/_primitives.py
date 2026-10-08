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
    is_accessor,
    untrack,
)
from ._session import SsrSource

__all__ = [
    "Setter",
    "create_owner",
    "is_disposed",
    "is_server",
    "create_signal",
    "create_memo",
    "create_effect",
    "create_tracked_effect",
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
    "ChildrenAccessor",
    "create_reaction",
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

    __slots__ = ("_pending", "_staged", "_origin")

    def __init__(self, fn: Callable[..., T], *, equals: Any) -> None:
        super().__init__(fn, equals=equals)
        self._pending: Any = None
        self._staged: bool = False
        self._origin: int = _core._O_NORMAL

    def set(self, value: T | Callable[[T], T]) -> T:
        if _core._current_observer is not None and _core._warnings.DEV_MODE and not _core._owned_write_depth:
            raise _core.WriteInScopeError(
                "Cannot write a derived signal inside a tracking scope. Write it from an event "
                "handler, an action, or the apply stage of a split create_effect."
            )
        if callable(value):
            current = self._pending if self._staged else self.peek()
            value = value(current)
        origin = _core._write_origin()
        if self._staged:
            self._pending = value
            if origin > self._origin:
                self._origin = origin
        else:
            self._pending = value
            self._staged = True
            self._origin = origin
            _core._staged.append(self)
            _schedule_flush()
        return value

    def _commit(self) -> None:
        if not self._staged:
            return
        self._staged = False
        new = self._pending
        self._pending = None
        origin = self._origin
        self._origin = _core._O_NORMAL
        old = self._value
        if not _changed(self._equals, old, new):
            return
        self._first = False
        self._value = new
        if _core._track:
            _core._record(self, old, origin)
        obs = self._observers
        if obs:
            for o in list(obs):
                o._stale(_core._DIRTY)


def create_signal[T](
    value: T | Callable[[], T],
    *,
    equals: Any = _DEFAULT_EQUALS,
    name: str | None = None,
    owned_write: bool = False,
) -> tuple[Accessor[T], Setter[T]]:
    """Create a reactive signal and return its `(getter, setter)` pair.

    Writes are **staged**: the setter records the new value and every
    read keeps returning the committed value until the next flush (a
    browser microtask, the end of an event handler, or an explicit
    [`flush`][wybthon.flush]). There is no `batch()`; everything
    batches.

    The setter supports **functional updates**: pass `lambda n: n + 1`
    and it receives the latest staged value, so repeated updates in one
    handler compose. To store a callable as the value, return it from an
    updater: `set_fn(lambda _: my_callable)`.

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
        owned_write: Allow writes from inside an owned scope (a memo,
            an effect's compute stage, or a reactive hole) without
            raising [`WriteInScopeError`][wybthon.WriteInScopeError].
            Reserve it for state that's genuinely local to that scope,
            such as a measurement a memo caches for itself.

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
    getter: Accessor[T]
    setter: Callable[..., Any]
    if callable(value) and _positional_count(value) == 0:
        derived: _WritableMemo[T] = _WritableMemo(value, equals=equals)
        getter, setter = derived, derived.set
    else:
        sig: Signal[T] = Signal(value, equals=equals, name=name)  # type: ignore[arg-type]
        getter, setter = sig, sig.set
    return getter, (_allow_owned_write(setter) if owned_write else setter)


def _allow_owned_write(setter: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap `setter` so it's exempt from the dev-mode owned-scope write check."""

    def write(value: Any) -> Any:
        _core._owned_write_depth += 1
        try:
            return setter(value)
        finally:
            _core._owned_write_depth -= 1

    return write


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
    loading_value: T = ...,
    ssr_source: SsrSource = ...,
) -> Memo[T]: ...


@overload
def create_memo[T](
    fn: Callable[..., Awaitable[T]],
    *,
    equals: Any = ...,
    lazy: bool = ...,
    unobserved: Callable[[], Any] | None = ...,
    name: str | None = ...,
    loading_value: T = ...,
    ssr_source: SsrSource = ...,
) -> Memo[T]: ...


@overload
def create_memo[T](
    fn: Callable[..., T],
    *,
    equals: Any = ...,
    lazy: bool = ...,
    unobserved: Callable[[], Any] | None = ...,
    name: str | None = ...,
    loading_value: T = ...,
    ssr_source: SsrSource = ...,
) -> Memo[T]: ...


def create_memo(
    fn: Callable[..., Any],
    *,
    equals: Any = _DEFAULT_EQUALS,
    lazy: bool = False,
    unobserved: Callable[[], Any] | None = None,
    name: str | None = None,
    loading_value: Any = _core._MISSING,
    ssr_source: SsrSource = "server",
) -> Memo[Any]:
    """Create a derived value that recomputes when its sources change.

    Memos evaluate once at creation unless ``lazy=True``. Updates are
    **pull-based**: the body runs when the memo is read after
    a tracked source changed, and observers are notified only when the
    new value differs under `equals`. If `fn` accepts a positional
    parameter it receives the previous value (`None` on the first run).

    **Async memos.** When `fn` is an `async def` (or returns an
    awaitable), the memo becomes an async computation: reading it
    before the first value raises
    [`NotReadyError`][wybthon.NotReadyError], which the nearest
    [`Loading`][wybthon.Loading] boundary turns into fallback UI. Once
    it has a value, a recompute caused by an input change opens a
    **transition**: readers keep the previous value and the parts of
    the UI that depend on the changed input stay as they are until the
    new value lands, so the screen never shows a new input next to
    old data. Use [`is_pending`][wybthon.is_pending] to show a refresh
    hint and [`latest`][wybthon.latest] to read the new state early.
    Reads after an `await` are tracked exactly like reads before it.

    **Async generators.** An `async def` body containing `yield`
    streams: each yielded value becomes the memo's new value. Use it
    to adapt sockets, subscriptions, or any async iterable.

    Args:
        fn: Zero- or one-arg callable producing the value (sync, async,
            or an async generator).
        equals: Equality policy; see [`create_signal`][wybthon.create_signal].
        lazy: When `True`, the memo suspends once it loses its
            last subscriber (and recomputes fresh if read again later).
            Non-lazy memos live for their owner's lifetime.
        unobserved: Optional callback fired when the memo loses its last
            subscriber; pair it with `lazy=True` for resource cleanup.
        name: Optional label used in dev-mode diagnostics.
        loading_value: For async memos, a value to serve while the first
            run is in flight instead of raising `NotReadyError`. The
            memo is then never "not ready": it doesn't register with
            `Loading`, doesn't report pending for its first run, and
            never holds a transition on mount. Use it for
            nice-to-have data (a recommendation panel, a badge count).
        ssr_source: Where an async memo resolves when the page is
            server-rendered. `"server"` (the default) resolves it on
            the server and hydrates the browser with that value;
            `"hybrid"` does the same, then always re-runs it quietly in
            the browser; `"client"` never runs it on the server, so it
            loads after hydration. See
            [Server rendering](../concepts/server-rendering.md).

    Returns:
        A [`Memo`][wybthon.Memo] accessor.

    Example:
        ```python
        doubled = create_memo(lambda: count() * 2)

        async def load_user():
            uid = user_id()          # tracked: refetches when it changes
            return await fetch_json(f"/api/users/{uid}")

        user = create_memo(load_user)
        suggestions = create_memo(load_suggestions, loading_value=[])
        ```
    """
    if ssr_source not in ("server", "hybrid", "client"):
        raise ValueError('ssr_source must be "server", "hybrid", or "client"')
    memo = Memo(
        fn,
        equals=equals,
        lazy=lazy,
        unobserved=unobserved,
        name=name,
        loading_value=loading_value,
        ssr_source=ssr_source,
    )
    if not lazy:
        memo._update_if_necessary()
    return memo


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------


def create_effect(
    compute: Callable[..., Any],
    apply: Callable[..., Any],
    *,
    defer: bool = False,
    error: Callable[[BaseException], Any] | None = None,
) -> Computation:
    """Create a side effect that re-runs when its tracked sources change.

    Effects run after the DOM has been committed, so they observe the
    updated document; the first run happens on the next flush (right
    after the component that created it has mounted), not at creation.
    Inside a component they're disposed on unmount.

    **Split effect**: `compute` runs tracked and returns a
    value; `apply` runs *untracked* with `(value, prev)` and performs
    the side effect. Incidental reads inside `apply` never
    over-subscribe the effect, and signal writes belong there. `apply`
    may return a cleanup callable that runs before the next `apply` and
    on disposal.

    Use [`create_tracked_effect`][wybthon.create_tracked_effect] when one
    callback should combine tracking and side effects. Split effects keep
    committed resources alive while replacement data is held.

    If `compute` accepts a positional parameter it receives its previous
    return value (`None` on the first run). `compute` may be
    `async def`; awaits suspend the effect without blocking and reads
    after an `await` are still tracked.

    Args:
        compute: The tracked stage.
        apply: Untracked side-effect stage receiving
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

    Note:
        Effects don't run during a server render; see
        [`is_server`][wybthon.is_server].
    """
    if _core._server_depth:
        return _inert(compute)
    return _create_effect(compute, apply, defer=defer, error=error)


def _inert(fn: Callable[..., Any]) -> Computation:
    """A disposed computation standing in for an effect that never runs (server rendering)."""
    comp = Computation(fn, kind=_K_EFFECT, pass_prev=False)
    comp._disposed = True
    return comp


def _create_effect(
    compute: Callable[..., Any],
    apply: Callable[..., Any],
    *,
    defer: bool = False,
    error: Callable[[BaseException], Any] | None = None,
) -> Computation:
    """Create a split effect unconditionally (framework-internal effects also run on the server)."""
    comp = Computation(compute, kind=_K_EFFECT, apply=apply, defer=defer, error=error)
    owner = _core._current_owner
    if owner is not None:
        owner._add_child(comp)
    # The first run is deferred to the effect phase of the next flush, so
    # an effect created in a component body observes the mounted DOM.
    _core._effect_queue.append(comp)
    _core._schedule_flush()
    return comp


def create_tracked_effect(
    fn: Callable[..., Any], *, error: Callable[[BaseException], Any] | None = None
) -> Computation:
    """Run a tracked callback after DOM commit, disposing its scope before each run.

    Prefer split effects for external resources: a tracked callback can run
    while async work is pending. Reads subscribe; put writes in a split effect's apply stage.
    Doesn't run during a server render.
    """
    if _core._server_depth:
        return _inert(fn)
    comp = Computation(fn, kind=_K_EFFECT, error=error)
    owner = _core._current_owner
    if owner is not None:
        owner._add_child(comp)
    _core._effect_queue.append(comp)
    _schedule_flush()
    return comp


def create_render_effect(
    compute: Callable[..., Any],
    apply: Callable[..., Any],
    *,
    defer: bool = False,
    error: Callable[[BaseException], Any] | None = None,
) -> Computation:
    """Create a split effect that runs in the **render phase**, before the DOM commit.

    Wybthon's reactive holes and prop bindings are render effects, so a
    render effect observes the DOM in the same state the framework's own
    bindings do (updates emitted, not yet committed). Prefer
    [`create_effect`][wybthon.create_effect] unless you're building a
    rendering primitive.

    Like Solid 2.0's `createRenderEffect`, it always takes a tracked
    `compute` stage and an untracked `apply` stage, with the same
    arguments as `create_effect`.
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

    Doesn't run during a server render.

    Args:
        fn: Zero-arg callback. May return a cleanup callable.

    Raises:
        RuntimeError: If called outside any reactive scope.

    Example:
        ```python
        class ChartProps(Props):
            data: Prop[list[float]]


        @component
        def Chart(props: ChartProps):
            canvas = Ref()

            def start():
                handle = draw(canvas.current, props.data.peek())
                return lambda: handle.destroy()

            on_settled(start)
            return canvas_(ref=canvas)
        ```
    """
    owner = _core._current_owner
    if owner is None:
        raise RuntimeError("on_settled() must be called inside a component or reactive scope")
    if _core._server_depth:
        return

    if isinstance(owner, Computation) and owner._apply is not None and _core._current_observer is owner:
        owner = owner._preparation()

    def run() -> None:
        if owner._disposed:
            return
        result = _core.run_with_owner(owner, lambda: untrack(fn))
        if callable(result):
            owner._add_cleanup(result)

    preparation = _core._pending_preparation(owner)
    if preparation is not None:
        preparation.callbacks.append(run)
    else:
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


def create_root[T](fn: Callable[[Callable[[], None]], T], *, detached: bool = False) -> T:
    """Run `fn` inside a root owned by the current scope unless explicitly detached.

    Use it for explicitly disposable reactive work. Pass ``detached=True``
    for global stores or subscriptions that outlive the surrounding component.

    Args:
        fn: Receives a `dispose` callable that tears the root down.
        detached: Create an independent lifetime instead of joining the current owner.

    Returns:
        Whatever `fn` returns.
    """
    root = Owner()
    if not detached and _core._current_owner is not None:
        _core._current_owner._add_child(root)

    def dispose() -> None:
        root.dispose()

    return _core.run_with_owner(root, lambda: fn(dispose))


def create_owner() -> Owner:
    """Create an ownership scope owned by the current one.

    The scope is disposed with its parent. Run code under it with
    [`run_with_owner`][wybthon.run_with_owner], and dispose it early
    with `owner.dispose()`. Pass it to `run_with_owner(None, ...)` first
    for a scope with an independent lifetime.
    """
    owner = Owner()
    if _core._current_owner is not None:
        _core._current_owner._add_child(owner)
    return owner


def is_disposed(owner: Owner) -> bool:
    """Return whether `owner` has been disposed."""
    return owner._disposed


def is_server() -> bool:
    """Return True while a server render is in progress.

    Use it to choose a data source, or to skip browser-only work, in
    code that also runs in the browser:

    ```python
    async def load_user():
        if is_server():
            return database.users.get(user_id())
        return await fetch_json(f"/api/users/{user_id()}")
    ```
    """
    return _core._server_depth > 0


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


def is_pending(fn: Callable[[], Any]) -> bool:
    """Return True while a change is in flight for the value `fn` reads.

    Evaluates `fn` in probe mode and reports whether any value it read
    is waiting on a transition:

    - a signal or memo whose new value is **held** (the batch that
      changed it is waiting for async work to land, or the write was
      made inside an [`action`][wybthon.action] that hasn't settled);
    - an async computation whose recompute is **in flight** (a quiet
      [`refresh`][wybthon.refresh] is silent);
    - a value an in-flight action declared with
      [`affects`][wybthon.affects];
    - an optimistic value with an active override;
    - a read that raises [`NotReadyError`][wybthon.NotReadyError].

    The reads are tracked like any other, so a hole using `is_pending`
    updates as the state changes, but they don't make the hole wait for
    the transition: an indicator has to show *during* the hold.

    ```python
    span(lambda: "Refreshing..." if is_pending(user) else "")
    button("Save", disabled=lambda: is_pending(lambda: store.items))
    ```
    """
    saved = _core._probe_hit
    _core._probe_hit = False
    _core._probe_depth += 1
    _core._update_slow_reads()
    try:
        try:
            fn()
        except NotReadyError:
            _core._probe_hit = True
        return _core._probe_hit
    finally:
        _core._probe_hit = saved
        _core._probe_depth -= 1
        _core._update_slow_reads()


def latest[T](fn: Callable[[], T]) -> T | None:
    """Evaluate `fn` against the newest state, without ever suspending.

    Two things differ from a plain read:

    - Not-ready async reads return their most recent value (or `None`
      if they never resolved) instead of raising
      [`NotReadyError`][wybthon.NotReadyError].
    - Values a transition holds return the **new** value being computed
      rather than the one the UI still shows. Use it when a piece of UI
      should update ahead of the rest (a header that shows the newly
      selected id while the detail pane keeps the old record).
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

    __slots__ = ("_fn", "_truthy", "_authoritative", "_timeout")

    def __init__(
        self, fn: Callable[[], T], *, truthy: bool = False, authoritative: bool = False, timeout: float | None = None
    ) -> None:
        self._fn = fn
        self._truthy = truthy
        self._authoritative = authoritative
        self._timeout = timeout

    def __await__(self) -> Generator[Any, None, T]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        fn = self._fn
        action_tx = _core._in_action
        handle: asyncio.TimerHandle | None = None

        def probe() -> None:
            if future.done():
                return
            previous_action = _core._in_action
            _core._in_action = action_tx
            _core._authoritative_depth += self._authoritative
            _core._readiness_depth += 1
            try:
                value = fn()
                if self._truthy and not value:
                    return
            except NotReadyError:
                return
            except Exception as exc:
                future.set_exception(exc)
                _core._call_soon(comp.dispose)
                return
            finally:
                _core._in_action = previous_action
                _core._authoritative_depth -= self._authoritative
                _core._readiness_depth -= 1
            future.set_result(value)
            _core._call_soon(comp.dispose)

        comp = Computation(probe, kind=_K_EFFECT, pass_prev=False)
        comp._update_if_necessary()
        if not future.done():
            if self._timeout is not None:

                def expire() -> None:
                    if not future.done():
                        future.set_exception(TimeoutError("Reactive expression timed out"))
                        comp.dispose()

                handle = loop.call_later(self._timeout, expire)
            _schedule_flush()

        async def wait() -> T:
            try:
                return await future
            finally:
                if handle is not None:
                    handle.cancel()
                comp.dispose()

        return wait().__await__()


def resolve[T](fn: Callable[[], T]) -> Awaitable[T]:
    """Return an awaitable for the next settled value of `fn()`.

    Tracks every dependency of `fn`, including cached memos, and waits
    for pending or quiet async recomputations. Streams become ready at
    their first fresh yield. Rejects when the expression raises; cancellation
    removes the temporary subscriptions.

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

    Called inside an [`action`][wybthon.action], the refreshed value
    lands into the action's transaction and reveals together with the
    action's other writes when it settles.

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
        comp = hook()

        class Refreshed:
            def __await__(self) -> Any:
                async def wait() -> Any:
                    await _Settle(comp._read)
                    return target

                return wait().__await__()

        return Refreshed()
    if isinstance(target, Memo):
        target._refresh()
        return _Settle(target)
    raise TypeError(f"refresh() expects a memo or derived store, got {target!r}")


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

_unique_id_counter: int = 0


def create_unique_id() -> str:
    """Return a unique id string (for `for`/`id` attribute pairs).

    Ids created while a server render or a hydration mounts are derived
    from the component's position in the tree (`wyb-h` followed by a
    short hash), so the server and the hydrating browser agree on them.
    """
    session = _core._session
    if session is not None and session.keying:
        return f"wyb-h{_core._next_key()}"
    global _unique_id_counter
    _unique_id_counter += 1
    return f"wyb-{_unique_id_counter}"


class ChildrenAccessor(Accessor[Any]):
    """The resolved children returned by [`children`][wybthon.children].

    Calling it returns the single resolved child, or a list when there
    are several (or none); [`to_array`][wybthon.ChildrenAccessor.to_array]
    always returns a list.
    """

    __slots__ = ("_memo",)

    def __init__(self, memo: Memo[list[Any]]) -> None:
        self._memo = memo

    def __call__(self) -> Any:
        items = self._memo()
        return items[0] if len(items) == 1 else items

    def peek(self) -> Any:
        items = self._memo.peek()
        return items[0] if len(items) == 1 else items

    def to_array(self) -> list[Any]:
        """Return the resolved children as a list (tracked)."""
        return list(self._memo())


def _resolve_children(value: Any, out: list[Any]) -> None:
    if value is None or value is True or value is False:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _resolve_children(item, out)
        return
    if is_accessor(value):
        _resolve_children(value(), out)
        return
    out.append(value)


def children(fn: Callable[[], Any]) -> ChildrenAccessor:
    """Resolve a component's children once, so it can inspect or reuse them.

    Wraps a getter that returns children (typically `props.children`)
    and returns a memoized accessor. Nested lists are flattened,
    reactive children (accessors and zero-argument functions) are called
    and their results resolved, and `None` and booleans are dropped.
    This matches Solid 2.0's `children` helper.

    ```python
    from wybthon import children as resolve_children


    @component
    def Tabs(props: ParentProps):
        tabs = resolve_children(props.children)
        return nav(lambda: [li(tab) for tab in tabs.to_array()])
    ```
    """

    def resolve() -> list[Any]:
        out: list[Any] = []
        _resolve_children(fn(), out)
        return out

    return ChildrenAccessor(create_memo(resolve, equals=False))


def create_reaction(
    effect: Callable[[], Any], *, error: Callable[[BaseException], Any] | None = None
) -> Callable[[Callable[[], Any]], None]:
    """Separate tracking from re-execution: run `effect` once when tracked reads change.

    Returns `track(fn)`. Calling `track` runs `fn` and subscribes to what
    it reads; the first time any of those sources changes, `effect` runs
    (untracked, after the DOM commit) and the subscription ends. Call
    `track` again to re-arm it. Matches Solid 2.0's `createReaction`.

    ```python
    track = create_reaction(lambda: print("count changed"))
    track(lambda: count())
    ```
    """
    owner = _core._current_owner
    current: list[Computation | None] = [None]

    def track(fn: Callable[[], Any]) -> None:
        previous = current[0]
        if previous is not None:
            previous.dispose()
        armed = [False]

        def compute() -> bool:
            if armed[0]:
                return True
            fn()
            armed[0] = True
            return False

        def apply(fired: bool) -> None:
            if not fired:
                return
            comp.dispose()
            if current[0] is comp:
                current[0] = None
            effect()

        comp = Computation(compute, kind=_K_EFFECT, apply=apply, error=error, pass_prev=False)
        current[0] = comp
        if owner is not None:
            owner._add_child(comp)
        comp._update_if_necessary()

    return track
