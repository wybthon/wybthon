"""Hydration sessions: the state shared by a server render pass and a hydrating client.

A session is active while the server renders one pass of a tree and
while the browser hydrates it. It assigns deterministic keys to the
memos and `Loading` boundaries the mount creates, carries the server's
resolved async values to the client, and holds request data (the URL)
for the server render.

Keys come from *positions*: each component, hole, list row, and branch
knows its place in the rendered tree, and a counter within that place
numbers the memos, boundaries, and ids created there. Positions don't
depend on when async data arrives, so a key means the same thing in
every server pass and in the browser. Each value also carries the
qualified name of the function that computed it, and a seed is only
applied to a memo with the same function.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

__all__ = ["Session", "ServerError", "SsrSource", "encode_state", "decode_state"]

SsrSource = Literal["server", "hybrid", "client"]


class ServerError(RuntimeError):
    """An async memo failed on the server; raised again on the client while hydrating.

    The original exception doesn't survive serialization, so the client
    sees its type name and message. An [`Errored`][wybthon.Errored]
    boundary shows the same fallback on both sides; resetting the
    boundary runs the computation again in the browser.
    """

    def __init__(self, message: str, type_name: str = "Exception") -> None:
        super().__init__(message)
        self.type_name = type_name


class Session:
    """One server render pass, or one client hydration.

    Attributes:
        mode: `"server"` or `"hydrate"`.
        url: The request URL (server passes only).
        resolve_async: Server passes only: whether async memos start.
            A synchronous render leaves them pending.
        values: Resolved async values by memo key, as
            `(value, function name)`.
        errors: Serialized async failures by memo key, as
            `(type name, message)`.
        keying: True while memos, boundaries, and ids receive keys: the
            whole server pass, and the synchronous mount of hydration.
        memos: Server passes: `(key, memo)` for every keyed memo.
        boundaries: Server passes: `(key, fragment VNode, shown signal)`
            for every `Loading` boundary.
        error_boundaries: Server passes: `(key, error signal)` for every
            `Errored` boundary.
        failed: `Errored` boundaries showing their fallback on the
            server, as `(error type name, message)` by key.
        inflight: Server passes: memos from earlier passes whose work is
            still running, by key. A memo with one of these keys waits
            instead of starting the same work again.
        after_hydration: Callbacks to run once hydration has committed.
        event: Server passes: the [`RequestEvent`][wybthon.RequestEvent]
            being rendered.
    """

    __slots__ = (
        "mode",
        "url",
        "resolve_async",
        "values",
        "errors",
        "keying",
        "memos",
        "boundaries",
        "error_boundaries",
        "failed",
        "inflight",
        "after_hydration",
        "counts",
        "event",
    )

    def __init__(
        self,
        mode: Literal["server", "hydrate"],
        *,
        url: str | None = None,
        resolve_async: bool = False,
        values: dict[str, tuple[Any, str]] | None = None,
        errors: dict[str, tuple[str, str]] | None = None,
        failed: dict[str, tuple[str, str]] | None = None,
        event: Any = None,
    ) -> None:
        self.mode = mode
        self.event = event
        self.url = url
        self.resolve_async = resolve_async
        self.values: dict[str, tuple[Any, str]] = values if values is not None else {}
        self.errors: dict[str, tuple[str, str]] = errors if errors is not None else {}
        self.keying = False
        self.memos: list[tuple[str, Any]] = []
        self.boundaries: list[tuple[str, Any, Any]] = []
        self.error_boundaries: list[tuple[str, Any]] = []
        self.failed: dict[str, tuple[str, str]] = failed if failed is not None else {}
        self.inflight: dict[str, Any] = {}
        self.after_hydration: list[Callable[[], Any]] = []
        self.counts: dict[str, int] = {}

    def next_key(self, position: str) -> str:
        """Return the next key created at `position` (memos, boundaries, and ids)."""
        counts = self.counts
        index = counts.get(position, 0)
        counts[position] = index + 1
        import hashlib

        return hashlib.blake2s(f"{position}#{index}".encode(), digest_size=6).hexdigest()

    def enter(self, position: str) -> None:
        """Restart numbering at `position` (a component body or expression re-running)."""
        self.counts[position] = 0


def encode_state(
    values: dict[str, tuple[Any, str]],
    errors: dict[str, tuple[str, str]],
    failed: dict[str, tuple[str, str]] | None = None,
) -> str:
    """Serialize resolved values, errors, and failed boundaries for a `data-wyb-state` script.

    `<` is escaped so the payload can never close its `<script>`.
    """
    payload: dict[str, Any] = {"v": {key: [value, name] for key, (value, name) in values.items()}}
    if errors:
        payload["e"] = {key: list(value) for key, value in errors.items()}
    if failed:
        payload["x"] = {key: list(value) for key, value in failed.items()}
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")


def decode_state(
    text: str | None,
) -> tuple[dict[str, tuple[Any, str]], dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """Parse a `data-wyb-state` payload into `(values, errors, failed boundaries)`."""
    if not text:
        return {}, {}, {}
    try:
        payload = json.loads(text)
    except ValueError:
        return {}, {}, {}
    values = {key: (value[0], str(value[1])) for key, value in (payload.get("v") or {}).items()}
    errors = {key: (str(value[0]), str(value[1])) for key, value in (payload.get("e") or {}).items()}
    failed = {key: (str(value[0]), str(value[1])) for key, value in (payload.get("x") or {}).items()}
    return values, errors, failed
