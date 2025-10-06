### wybthon.router

::: wybthon.router

#### API

- `class Route(path: str, component, children: Optional[List[Route]] = None)`
- `class Router(routes: List[Route], base_path: str = "", not_found: Optional[Component|function] = None)`
- `function Link({to: str, children, base_path?: str, replace?: bool, class_active?: str})`
- `function navigate(path: str, replace: bool = False)`
- `signal current_path` – reactive signal with current `path + search`

Notes:
- Wildcard path segment `*` captures the rest of the path into `params["wildcard"]`.
- Trailing `/*` also matches the base segment; e.g. `/docs/*` matches `/docs` and `/docs/guide`.
- Nested routes use `children` and resolve to the most specific match.
  - `Link` automatically adds an active CSS class (default: `"active"`) when its `href` matches the current pathname. Customize with `class_active`. Use `replace=True` to avoid pushing a new history entry.
