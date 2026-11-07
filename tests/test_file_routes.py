"""File routes: a package of route modules becomes a route tree."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from wybthon import Loading, flush
from wybthon.router import api_routes, create_router, file_routes, navigate, resolve
from wybthon.testing import render, tick

FILES = {
    "__init__.py": "",
    "_layout.py": (
        "from wybthon import component, html\nfrom wybthon.router import RouteProps\n\n@component\ndef Layout(props: RouteProps):\n"
        '    return html(t"<main>{props.children}</main>")\n'
    ),
    "index.py": 'from wybthon import component, html\n\n@component\ndef Page():\n    return html(t"<h1>home</h1>")\n',
    "about.py": 'from wybthon import component, html\n\n@component\ndef Page():\n    return html(t"<h1>about</h1>")\n',
    "_helpers.py": "VALUE = 1\n",
    "notes.py": "VALUE = 'not a page'\n",
    "users/_layout.py": (
        "from wybthon import component, html\nfrom wybthon.router import RouteProps\n\n@component\ndef Layout(props: RouteProps):\n"
        '    return html(t"<section>users:{props.children}</section>")\n'
    ),
    "users/index.py": 'from wybthon import component, html\n\n@component\ndef Page():\n    return html(t"<p>all</p>")\n',
    "users/[id].py": (
        "from wybthon import component, html\nfrom wybthon.router import RouteProps\n\nseen = []\n\n"
        "def preload(args):\n    seen.append(args.params['id'])\n\n"
        "@component\ndef Page(props: RouteProps):\n    return html(t\"<p>user {props.params['id']}</p>\")\n"
    ),
    "(marketing)/pricing.py": 'from wybthon import component, html\n\n@component\ndef Page():\n    return html(t"<p>pricing</p>")\n',
    "docs/[[section]].py": (
        "from wybthon import component, html\nfrom wybthon.router import RouteProps\n\n@component\ndef Page(props: RouteProps):\n"
        "    return html(t\"<p>docs [{props.params['section']}]</p>\")\n"
    ),
    "[...404].py": 'from wybthon import component, html\n\n@component\ndef Page():\n    return html(t"<p>missing</p>")\n',
    "api/health.py": "async def GET(event):\n    return {'ok': True}\n\nasync def POST(event):\n    return None\n",
}


@pytest.fixture
def routes_package(tmp_path: Path):
    root = tmp_path / "proj"
    package = root / "fileroutes_app"
    for name, text in FILES.items():
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (package.parent / "fileroutes_app" / "__init__.py").write_text("")
    sys.path.insert(0, str(root))
    yield "fileroutes_app"
    sys.path.remove(str(root))
    for name in [name for name in sys.modules if name.startswith("fileroutes_app")]:
        del sys.modules[name]


def test_files_become_a_route_tree(routes_package: str):
    routes = file_routes(routes_package)
    assert len(routes) == 1 and routes[0].path == ""  # the root layout
    tree = routes[0].children
    paths = [route.path for route in tree]
    assert paths[:2] == ["about", ""] or set(paths[:2]) == {"about", ""}
    assert "notes" not in paths and "_helpers" not in paths
    assert paths[-1] == "*404"
    found = {route.path: route for route in tree}
    assert {child.path for child in found["users"].children} == {"", ":id"}
    assert [child.path for child in found["docs"].children] == [":section?"]
    assert resolve(routes, "/pricing") is not None
    assert resolve(routes, "/users/7")[1]["params"] == {"id": "7"}
    assert resolve(routes, "/docs")[1]["params"] == {"section": ""}
    assert resolve(routes, "/zzz")[0].path == "*404"


def test_file_route_pages_load_lazily_and_render(routes_package: str):
    navigate("/")
    flush()
    router = create_router(file_routes(routes_package))
    assert f"{routes_package}.about" not in sys.modules

    async def main() -> None:
        with render(Loading(router(), fallback="loading")) as screen:
            await tick(6)
            assert screen.text() == "home"
            navigate("/users/3")
            flush()
            await tick(6)
            assert screen.text() == "users:user 3"
            navigate("/docs/intro")
            flush()
            await tick(6)
            assert screen.text() == "docs [intro]"
            navigate("/nope")
            flush()
            await tick(6)
            assert screen.text() == "missing"
        module = sys.modules[f"{routes_package}.users._wyb__5b_id_5d_"]
        assert module.seen == ["3"]
        navigate("/")
        flush()

    asyncio.run(main())


def test_http_handlers_are_listed_with_their_paths(routes_package: str):
    found = {route.path: route for route in api_routes(routes_package)}
    assert set(found) == {"/api/health"}
    assert found["/api/health"].methods == {"GET", "POST"}
    assert callable(found["/api/health"].handler("GET"))
