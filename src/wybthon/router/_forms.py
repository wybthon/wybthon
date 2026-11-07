"""`form_action` and `use_submissions`: actions with a URL, as in Solid Router 2.0.

A form action is an [`action`][wybthon.action] that a `<form>` can post
to. Put it in the form's `action` attribute:

```python
@form_action
@server_function
async def add_todo(form: FormData) -> None:
    await db.todos.add(form["title"])


html(t'<form action={add_todo} method="post"><input name="title"><button>Add</button></form>')
```

- **With Python running**, the router intercepts the submit, calls the
  action with the form's [`FormData`][wybthon.FormData], and marks the
  form `aria-busy` until the result is on screen. The call is a
  transaction like any action: `add_todo.pending()` is true meanwhile,
  [`create_optimistic`][wybthon.create_optimistic] writes revert when it
  settles, and when it completes the page's queries revalidate.
- **Before Pyodide has booted** (or with JavaScript off), the browser
  posts the form to the server function's URL. The server runs it and
  answers with a redirect: back to the page, or wherever the action
  redirected. The submission's result travels in a short-lived cookie,
  so [`use_submissions`][wybthon.router.use_submissions] shows it on the
  page that loads next.

[`bind`][wybthon.router.FormAction.bind] adds arguments ahead of the form
data (Solid's `action.with`): `action={delete_todo.bind(todo.id)}`.
"""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .. import _wire, kernel
from .. import server_functions as _sf
from .._formdata import FormData, UploadedFile
from .._warnings import log_error
from ..reactivity import _core
from ..reactivity._actions import Action
from ..reactivity._core import Accessor, Memo, Signal
from ..reactivity._session import ServerError
from ..request import get_request_event
from ..server_functions import (
    FN_PATH,
    Redirect,
    Reload,
    Respond,
    ServerFunction,
    _app_base,
    _remote,
)
from ._data import revalidate

__all__ = ["FormAction", "Submission", "form_action", "use_submissions", "FLASH_COOKIE"]

FLASH_COOKIE = "wyb_flash"
"""The cookie that carries a JavaScript-free submission's result to the next page."""

ACTION_PATH = "_wyb/action/"

# Form actions by their unbound URL path, so an intercepted submit finds its action.
_by_path: weakref.WeakValueDictionary[str, FormAction[..., Any]] = weakref.WeakValueDictionary()
_by_name: weakref.WeakValueDictionary[str, FormAction[..., Any]] = weakref.WeakValueDictionary()


@dataclass(eq=False)
class Submission:
    """A settled submission of a form action; see [`use_submissions`][wybthon.router.use_submissions].

    Attributes:
        input: The arguments the action received: bound arguments, then
            the [`FormData`][wybthon.FormData].
        result: What the action returned, when it succeeded.
        error: The exception it raised, when it failed.
        url: The URL the form posted to.
    """

    input: list[Any]
    result: Any = None
    error: BaseException | None = None
    url: str = ""
    _action: FormAction[..., Any] | None = field(default=None, repr=False)

    def clear(self) -> None:
        """Remove this submission from its action's history."""
        if self._action is not None:
            history = self._action._root()._history
            history.set(lambda items: [item for item in items if item is not self])

    def retry(self) -> Any:
        """Submit the same input again; returns the call's future."""
        if self._action is None:
            return None
        self.clear()
        return self._action._root()._submit(list(self.input))


class FormAction[**P, R]:
    """An action a form can post to; returned by [`form_action`][wybthon.router.form_action].

    Use it as a form's (or a submit button's `formaction`) attribute, or
    call it directly with the same arguments as the function it wraps.

    Attributes:
        name: The action's stable name (a server function's id).
        pending: Tracked accessor: `True` while a submission is in flight.
    """

    def __init__(self, fn: Callable[..., Awaitable[R]], name: str, *, parent: Any = None, bound: tuple[Any, ...] = ()):
        self._fn = fn
        self.name = name
        self._bound = bound
        self._parent = parent
        self.__name__ = getattr(fn, "__name__", name)
        self.__qualname__ = getattr(fn, "__qualname__", self.__name__)
        if parent is None:
            self._action: Action[..., Any] = Action(self._run)
            self._history: Signal[list[Submission]] = Signal([], name=f"submissions {name}")
            self._submit_hooks: list[tuple[_core.Owner | None, Callable[..., Any]]] = []
            self._settled_hooks: list[tuple[_core.Owner | None, Callable[[Submission], Any]]] = []
            self.pending: Accessor[bool] = self._action.pending
            _by_path[self._path()] = self
            _by_name[name] = self
        else:
            self._action = parent._action
            self._history = parent._history
            self._submit_hooks = parent._submit_hooks
            self._settled_hooks = parent._settled_hooks
            self.pending = parent.pending

    def _root(self) -> FormAction[..., Any]:
        return self._parent if self._parent is not None else self

    def _path(self) -> str:
        if isinstance(self._fn, ServerFunction):
            return FN_PATH + quote(self._fn.id, safe=":")
        return ACTION_PATH + quote(self.name, safe=":")

    @property
    def url(self) -> str:
        """What the form's `action` attribute holds: the URL a JavaScript-free post goes to."""
        base = _app_base() if not _core._server_depth else _server_base()
        address = base + self._path()
        if self._bound:
            address += "?args=" + quote(_wire.dumps(list(self._bound)))
        return address

    def __str__(self) -> str:
        # Rendering the action into a form is what makes submits reach it.
        _ensure_submit()
        return self.url

    def bind(self, *args: Any) -> FormAction[..., R]:
        """This action with `args` passed ahead of the form data (Solid's `action.with`)."""
        root = self._root()
        return FormAction(root._fn, root.name, parent=root, bound=(*self._bound, *args))

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Future[R]:
        """Run the action with these arguments (after any bound ones)."""
        return self._root()._submit([*self._bound, *args], kwargs)

    # -- hooks -----------------------------------------------------------

    def on_submit(self, fn: Callable[..., Any]) -> FormAction[P, R]:
        """Call `fn(*input)` when a submission starts, inside its transaction.

        Write optimistic state here: it reverts when the submission
        settles. The hook belongs to the calling owner and is removed
        when that owner is disposed.
        """
        self._register(self._submit_hooks, fn)
        return self

    def on_settled(self, fn: Callable[[Submission], Any]) -> FormAction[P, R]:
        """Call `fn(submission)` when a submission settles (owner-scoped, like `on_submit`)."""
        self._register(self._settled_hooks, fn)
        return self

    @staticmethod
    def _register(hooks: list[tuple[Any, Any]], fn: Callable[..., Any]) -> None:
        owner = _core._current_owner
        entry = (owner, fn)
        hooks.append(entry)
        if owner is not None:
            owner._add_cleanup(lambda: hooks.remove(entry) if entry in hooks else None)

    # -- running ---------------------------------------------------------

    def _submit(
        self, args: list[Any], kwargs: dict[str, Any] | None = None, *, native: Any = None, form_id: int | None = None
    ) -> asyncio.Future[Any]:
        if form_id is not None:
            kernel.emit((kernel.OP_SET_ATTR, form_id, "aria-busy", "true"))
        future: asyncio.Future[Any] = self._action(args, kwargs or {}, native)

        def done(result: asyncio.Future[Any]) -> None:
            if form_id is not None:
                kernel.emit((kernel.OP_SET_ATTR, form_id, "aria-busy", None))
            if result.cancelled():
                return
            error = result.exception()
            submission = Submission(
                list(args), None if error is not None else result.result(), error, self.url, self._root()
            )
            self._record(submission)

        future.add_done_callback(done)
        return future

    def _record(self, submission: Submission) -> None:
        root = self._root()
        root._history.set(lambda items: [*items[-31:], submission])
        for owner, hook in list(root._settled_hooks):
            if owner is not None and owner._disposed:
                continue
            try:
                hook(submission)
            except Exception as exc:
                log_error(f"An on_settled hook of {root.name} raised: {exc}", exc)
        _core._schedule_flush()

    async def _run(self, args: list[Any], kwargs: dict[str, Any], native: Any) -> Any:
        root = self._root()
        for owner, hook in list(root._submit_hooks):
            if owner is None or not owner._disposed:
                hook(*args, **kwargs)
        fn = root._fn
        if isinstance(fn, ServerFunction) and _remote():
            if args and isinstance(args[-1], FormData) and not kwargs:
                # A form posts its fields as a form, with bound arguments in the URL.
                form = native if native is not None else args[-1]
                return await fn._call_remote(tuple(args[:-1]), {}, "POST", form=form)
            return await fn._call_remote(tuple(args), kwargs, "POST")
        try:
            result = await fn(*args, **kwargs)
        except Redirect as response:
            result = response
        if isinstance(result, Redirect):
            revalidate(result.revalidate)
            _sf._navigate_hook(result.url, True)
            return None
        if isinstance(result, Reload | Respond):
            revalidate(result.revalidate)
            return result.value if isinstance(result, Respond) else None
        if not isinstance(fn, ServerFunction):
            # A client-side action is a mutation too: refetch the page's data.
            revalidate()
        return result

    def __repr__(self) -> str:
        return f"FormAction({self.name})"


def _server_base() -> str:
    from .. import server_functions

    return server_functions._base


def form_action[**P, R](fn: Callable[P, Awaitable[R]], name: str | None = None) -> FormAction[P, R]:
    """Make an async function something a `<form>` can post to.

    Usually it wraps a [server function][wybthon.server_function], which
    makes the form work before Python has booted. A client-only action
    (a plain `async def`) needs a stable `name`, since its URL must be
    the same on the server and in the browser.

    Args:
        fn: The async function; it receives any bound arguments, then the
            form's [`FormData`][wybthon.FormData].
        name: The action's name; defaults to the server function's id.

    Returns:
        A [`FormAction`][wybthon.router.FormAction].
    """
    if isinstance(fn, FormAction):
        return fn
    if isinstance(fn, ServerFunction):
        return FormAction(fn, name or fn.id)
    if name is None:
        raise TypeError("A form action that isn't a server function needs a name: form_action(fn, 'name')")
    return FormAction(fn, name)


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------


def use_submissions(
    action: FormAction[..., Any], where: Callable[[list[Any]], bool] | None = None
) -> Accessor[list[Submission]]:
    """The settled submissions of `action`, oldest first, as a tracked accessor.

    This is history, not in-flight state: use `action.pending()` and
    optimistic primitives for what a submission shows while it runs. On
    the page a JavaScript-free post returns to, it includes that post's
    submission.

    Args:
        action: The form action.
        where: Optional filter on each submission's input.
    """
    root = action._root()
    flash = _flash_for(root)

    def read() -> list[Submission]:
        items = root._history()
        if flash is not None:
            items = [flash, *items]
        return [item for item in items if where is None or where(item.input)]

    return Memo(read)


def _flash_for(action: FormAction[..., Any]) -> Submission | None:
    """The submission a JavaScript-free post left for this page, if it was this action's."""
    raw: str | None = None
    event = get_request_event()
    if event is not None:
        raw = event.cookies.get(FLASH_COOKIE)
    elif not _core._server_depth:
        raw = _browser_flash()
    if not raw:
        return None
    try:
        data = _wire.loads(unquote(raw))
    except _wire.WireError:
        return None
    if not isinstance(data, dict) or data.get("action") != action.name:
        return None
    error_data = data.get("error")
    error = (
        ServerError(str(error_data.get("message", "")), str(error_data.get("type", "Exception")))
        if error_data
        else None
    )
    form = FormData(data.get("form") or [])
    return Submission([*(data.get("args") or []), form], data.get("result"), error, data.get("url", ""), action)


_flash_cache: list[str | None] = []


def _browser_flash() -> str | None:
    """Read (once) and delete the flash cookie in the browser."""
    if _flash_cache:
        return _flash_cache[0]
    value: str | None = None
    try:
        from js import document

        for part in str(document.cookie).split(";"):
            name, _, raw = part.strip().partition("=")
            if name == FLASH_COOKIE:
                value = raw
        if value is not None:
            document.cookie = f"{FLASH_COOKIE}=; Max-Age=0; Path={_app_base()}"
    except Exception:
        value = None
    _flash_cache.append(value)
    return value


def flash_cookie(
    action_name: str, url: str, args: list[Any], form: FormData, result: Any, error: BaseException | None
) -> str:
    """The flash cookie's value for a JavaScript-free submission (server side)."""
    data: dict[str, Any] = {
        "action": action_name,
        "url": url,
        "args": args,
        "form": [[key, value] for key, value in form.items() if not isinstance(value, UploadedFile)],
    }
    if error is not None:
        data["error"] = {
            "type": error.type_name if isinstance(error, ServerError) else type(error).__name__,
            "message": str(error) if isinstance(error, ServerError) else "The server couldn't complete the request",
        }
    else:
        data["result"] = result
    try:
        text = quote(_wire.dumps(data))
    except _wire.WireError:
        data.pop("result", None)
        text = quote(_wire.dumps(data))
    if len(text) > 3500:
        data["form"] = []
        data.pop("result", None)
        text = quote(_wire.dumps(data))
    return text


# ---------------------------------------------------------------------------
# Intercepting submits
# ---------------------------------------------------------------------------


def find_action(action_url: str | None) -> tuple[FormAction[..., Any], list[Any]] | None:
    """The form action a form's `action` attribute names, and its bound arguments."""
    if not action_url:
        return None
    parts = urlsplit(action_url)
    path = unquote(parts.path)
    for prefix in (FN_PATH, ACTION_PATH):
        index = path.find("/" + prefix)
        if index >= 0:
            key = prefix + quote(path[index + 1 + len(prefix) :], safe=":")
            action = _by_path.get(key)
            if action is None:
                return None
            raw = parse_qs(parts.query).get("args", [None])[0]
            bound = _wire.loads(raw) if raw else []
            return action, list(bound) if isinstance(bound, list) else []
    return None


def _ensure_submit() -> None:
    """Route submits to form actions (once per page)."""
    if _core._server_depth:
        return
    from .. import events

    if handle_submit not in events._intercepts.get("submit", ()):
        events.intercept("submit", handle_submit)


def handle_submit(evt: Any, info: dict[str, Any]) -> None:
    """The router's default handling of a submit: run the form action it posts to."""
    found = find_action(info.get("action"))
    if found is None:
        return
    action, bound = found
    evt.prevent_default()
    native = None
    raw_event = evt.raw
    form = FormData()
    if raw_event is not None and hasattr(raw_event, "target") and not isinstance(kernel._backend, kernel.PythonBackend):
        from js import FormData as JsFormData

        submitter = getattr(raw_event, "submitter", None)
        native = (
            JsFormData.new(raw_event.target, submitter) if submitter is not None else JsFormData.new(raw_event.target)
        )
        for entry in native.entries():
            name, value = entry[0], entry[1]
            if isinstance(value, str):
                form.append(str(name), value)
            else:
                form.append(
                    str(name), UploadedFile(str(getattr(value, "name", "")), str(getattr(value, "type", "")), b"")
                )
    else:
        node = _stub_node(info.get("formId"))
        if node is not None:
            form = _stub_form_data(node, getattr(raw_event, "submitter", None) if raw_event is not None else None)
    action._submit([*bound, form], native=native, form_id=info.get("formId"))


def _stub_node(node_id: Any) -> Any:
    backend = kernel._backend
    getter = getattr(backend, "get_node", None)
    if node_id is None or getter is None:
        return None
    try:
        return getter(node_id)
    except Exception:
        return None


def _stub_form_data(form: Any, submitter: Any = None) -> FormData:
    """A test DOM form's fields, as the browser would submit them."""
    data = FormData()

    def attribute(node: Any, name: str) -> Any:
        return node.getAttribute(name) if hasattr(node, "getAttribute") else None

    def walk(node: Any) -> None:
        for child in getattr(node, "childNodes", []):
            tag = str(getattr(child, "tag", "") or "").lower()
            name = attribute(child, "name") if tag else None
            if tag in ("input", "select", "textarea") and name and attribute(child, "disabled") is None:
                kind = str(attribute(child, "type") or "text").lower()
                value = getattr(child, "value", None)
                if value is None:
                    value = attribute(child, "value") or ""
                if kind in ("checkbox", "radio"):
                    checked = getattr(child, "checked", None)
                    if checked is None:
                        checked = attribute(child, "checked") is not None
                    if checked:
                        data.append(name, str(attribute(child, "value") or "on"))
                elif kind not in ("submit", "button", "reset", "file", "image"):
                    data.append(name, str(value))
            walk(child)

    walk(form)
    if submitter is not None and attribute(submitter, "name"):
        data.append(attribute(submitter, "name"), str(attribute(submitter, "value") or ""))
    return data
