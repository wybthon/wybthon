"""Prerender an application's routes to HTML (run by `wyb build` in a subprocess).

A subprocess keeps each build's imports isolated: the application's
modules are imported fresh, and nothing they cache leaks into the dev
server or into the next rebuild.

Input (a JSON object on stdin): `project` (directory put first on
`sys.path`), `entry` (`module:function` returning the root view),
`base` (the URL base path), `routes` (paths within the app), `crawl`
(also render same-app links found in rendered pages), and `limit`
(the most routes to render).

Output (a JSON object on stdout): `{"pages": {route: html}}`.
"""

from __future__ import annotations

import asyncio
import html
import importlib
import inspect
import json
import re
import sys
import traceback
from typing import Any
from urllib.parse import urlsplit

_LINK = re.compile(r"<a\b[^>]*?\shref=\"([^\"]*)\"", re.IGNORECASE)


def _route_of(href: str, base: str) -> str | None:
    """Map an in-app link to a route path, or None when it leaves the app."""
    parts = urlsplit(html.unescape(href))
    if parts.scheme or parts.netloc or not parts.path.startswith("/"):
        return None
    path = parts.path
    if not (path + "/").startswith(base):
        return None
    route = "/" + path[len(base) :].lstrip("/")
    if "." in route.rsplit("/", 1)[-1]:
        return None
    return route.rstrip("/") or "/"


async def prerender(entry: str, base: str, routes: list[str], *, crawl: bool, limit: int) -> dict[str, str]:
    """Render every route (and, with `crawl`, every in-app link) to HTML."""
    from .reactivity import _core
    from .server import render_to_stream

    module_name, export = entry.split(":", 1)
    _core._server_depth += 1
    try:
        factory = getattr(importlib.import_module(module_name), export)
    finally:
        _core._server_depth -= 1
    pages: dict[str, str] = {}
    queue = [route.rstrip("/") or "/" for route in routes]
    while queue and len(pages) < limit:
        route = queue.pop(0)
        if route in pages:
            continue
        view: Any = factory
        if inspect.iscoroutinefunction(factory):
            view = await factory()
        url = base.rstrip("/") + route if route != "/" else base
        pages[route] = await render_to_stream(view, url=url)
        if crawl:
            for href in _LINK.findall(pages[route]):
                found = _route_of(href, base)
                if found is not None and found not in pages:
                    queue.append(found)
    return pages


def main() -> int:
    """Read the request from stdin, write the rendered pages to stdout."""
    request = json.loads(sys.stdin.read())
    sys.path.insert(0, request["project"])
    try:
        pages = asyncio.run(
            prerender(
                request["entry"],
                request["base"],
                request["routes"],
                crawl=bool(request.get("crawl")),
                limit=int(request.get("limit", 1000)),
            )
        )
    except ImportError as exc:
        sys.stderr.write(
            f"Prerendering imports the application in CPython and failed: {exc}\n"
            "Import browser-only modules (js, pyodide) inside functions, and guard them with "
            "wybthon.is_server().\n"
        )
        traceback.print_exc()
        return 1
    except Exception:
        traceback.print_exc()
        return 1
    sys.stdout.write(json.dumps({"pages": pages}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
