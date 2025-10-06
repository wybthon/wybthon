from dataclasses import dataclass
from typing import List, Optional

from wybthon.router_core import resolve


@dataclass
class R:
    path: str
    children: Optional[List] = None


def test_basic_match():
    routes = [R("/"), R("/about")]
    route, info = resolve(routes, "/about")
    assert route.path == "/about"
    assert info["params"] == {}


def test_params_and_query_ignored_here():
    routes = [R("/users/:id")]
    route, info = resolve(routes, "/users/42")
    assert route.path == "/users/:id"
    assert info["params"]["id"] == "42"


def test_nested_children_match():
    routes = [R("/about", children=[R("team")])]
    route, info = resolve(routes, "/about/team")
    assert route.path == "team"
    assert info["params"] == {}


def test_wildcard_match_and_empty_tail():
    routes = [R("/docs/*")]
    route, info = resolve(routes, "/docs/guide/intro")
    assert route.path == "/docs/*"
    assert info["params"]["wildcard"] == "guide/intro"

    route2, info2 = resolve(routes, "/docs")
    assert route2.path == "/docs/*"
    # optional tail is empty when matching just "/docs"
    assert info2["params"].get("wildcard", "") in ("", None)


def test_base_path_stripping():
    routes = [R("/about"), R("/docs/*")]
    route, info = resolve(routes, "/app/docs/guide", base_path="/app")
    assert route.path == "/docs/*"
    assert info["params"]["wildcard"] == "guide"

    # base path mismatch → no match
    assert resolve(routes, "/x/docs/guide", base_path="/app") is None
