"""Deterministic static app bundles, prerendered pages, and a production preview server."""

from __future__ import annotations

import fnmatch
import hashlib
import html
import http.server
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from ._split import Split, split
from .compiler import compile_source

PYODIDE_VERSION = "314.0.6"
_MARKER = "<!-- wyb:bootstrap -->"
# Prerendered pages replace everything between these markers (inclusive)
# with the server-rendered markup; client-only pages keep what's there.
_APP_START = "<!-- wyb:app -->"
_APP_END = "<!-- /wyb:app -->"
_INDEX = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wybthon app</title></head>
<body><div id="app"><!-- wyb:app --><p id="wyb-loading" role="status">Loading...</p><!-- /wyb:app --></div>
<!-- wyb:bootstrap -->
</body></html>
"""
# Framework modules that never ship to the browser: build and server tools,
# and the CPython test renderer.
_SERVER_ONLY = {
    "testing.py",
    "build.py",
    "dev.py",
    "server.py",
    "_ssr.py",
    "_prerender.py",
    "_split.py",
    "_stdlib.py",
    "_http.py",
    "asgi.py",
}
_STARTER = '''"""A run-once component with a reactive counter."""

from wybthon import component, create_signal, html


@component
def App():
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div>
        <h1>My Wybthon app</h1>
        <button onclick={increment}>Count: {count()}</button>
        <p>Doubled: {count() * 2}</p>
      </div>
    """)


def app():
    """Return the root view; the bootstrap renders (or hydrates) it into the mount element."""
    return App()
'''


_SERVER_FILES: dict[str, str] = {
    "app/__init__.py": '"""Application package."""\n',
    "app/main.py": """\"\"\"The app's router and its root layout.\"\"\"

from wybthon import ParentProps, component, html
from wybthon.router import create_router, file_routes

router = create_router(file_routes("app.routes"))


@component
def Shell(props: ParentProps):
    return html(t\"\"\"
      <header><nav><a href="/">Todos</a> <a href="/about">About</a></nav></header>
      <main>{props.children}</main>
    \"\"\")


def app():
    \"\"\"Return the root view; the server renders it per request and the browser hydrates it.\"\"\"
    return router(root=Shell)
""",
    "app/todos.py": """\"\"\"The todo list's data: a query to read it and a form action to change it.\"\"\"

from dataclasses import dataclass

from wybthon import FormData, server_function
from wybthon.router import form_action, query


@dataclass
class Todo:
    id: int
    title: str


@query
@server_function
async def list_todos() -> list[Todo]:
    from app.server import store

    return [Todo(id, title) for id, title in store.todos()]


@form_action
@server_function
async def add_todo(form: FormData) -> None:
    from app.server import store

    title = str(form.get("title", "")).strip()
    if title:
        store.add(title)
""",
    "app/server/__init__.py": '"""Server-only modules: they never reach the browser."""\n',
    "app/server/store.py": """\"\"\"A stand-in for a database: todos kept in the server's memory.\"\"\"

_todos: list[tuple[int, str]] = [(1, "Read the Wybthon docs")]


def todos() -> list[tuple[int, str]]:
    return list(_todos)


def add(title: str) -> None:
    _todos.append((len(_todos) + 1, title))
""",
    "app/routes/index.py": """\"\"\"/: the todo list, read with a query and added to with a form action.\"\"\"

from wybthon import For, Loading, component, create_memo, html

from app.todos import add_todo, list_todos


@component
def Page():
    todos = create_memo(lambda: list_todos())

    def row(todo, _index):
        return html(t"<li>{todo.title}</li>")

    return html(t\"\"\"
      <section>
        <h1>Todos</h1>
        {Loading(html(t"<ul>{For(todos(), row)}</ul>"), fallback=html(t"<p>Loading...</p>"))}
        <form action={add_todo} method="post">
          <input name="title" placeholder="Something to do" required>
          <button disabled={add_todo.pending()}>Add</button>
        </form>
      </section>
    \"\"\")
""",
    "app/routes/about.py": """\"\"\"/about: a page with no data.\"\"\"

from wybthon import component, html


@component
def Page():
    return html(t"<h1>About</h1><p>Rendered on the server, then hydrated in the browser.</p>")
""",
    "app/routes/[...404].py": """\"\"\"Any other URL: a 404 page.\"\"\"

from wybthon import component, html, http_status


@component
def Page():
    http_status(404)
    return html(t"<h1>Not found</h1>")
""",
}


def init_app(directory: Path, *, server: bool = False) -> None:
    """Create a reviewable starter project without overwriting existing files.

    With `server`, the starter is a full-stack app: file routes, a query
    and a form action backed by server functions, and `server = true`.
    """
    directory = directory.resolve()
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Destination isn't empty: {directory}")
    (directory / "app").mkdir(parents=True, exist_ok=True)
    if server:
        for name, text in _SERVER_FILES.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    else:
        (directory / "app" / "__init__.py").write_text('"""Application package."""\n', encoding="utf-8")
        (directory / "app" / "main.py").write_text(_STARTER, encoding="utf-8")
    (directory / "index.html").write_text(_INDEX, encoding="utf-8")
    common = (
        f'entry = "app.main:app"\nmount = "#app"\napp-dir = "app"\nbase = "/"\n'
        f'pyodide-version = "{PYODIDE_VERSION}"\npackages = []\nwheels = []\n'
    )
    if server:
        config = (
            common
            + "# Render pages per request and serve server functions (`wyb dev`, `wyb serve`).\n"
            + "server = true\n"
            + "# Modules that never reach the browser.\n"
            + 'server-only = ["app/server/**"]\n'
        )
    else:
        config = (
            common
            + "# Routes rendered to static HTML at build time; the browser hydrates them.\n"
            + 'prerender = ["/"]\ncrawl = true\n'
        )
    (directory / "wybthon.toml").write_text(
        config + '\n[chunks]\n# charts = ["app/charts/**"]\n',
        encoding="utf-8",
    )
    (directory / "pyproject.toml").write_text(
        '[project]\nname = "wybthon-app"\nversion = "0.1.0"\nrequires-python = ">=3.14"\ndependencies = ["wybthon"]\n',
        encoding="utf-8",
    )
    (directory / ".gitignore").write_text("dist/\n.venv/\n__pycache__/\n.mypy_cache/\n", encoding="utf-8")
    deploy = (
        "Run `wyb build`, then `wyb serve` to run the production server, or serve it with any ASGI server:\n"
        "`WYBTHON_PROJECT=. uvicorn --factory wybthon.asgi:create_app`.\n"
        if server
        else "Run `wyb build`, then `wyb preview` to check the production output.\n\n"
        "Deploy the contents of `dist/` to a static host with an HTML fallback for client routes.\n"
    )
    (directory / "README.md").write_text(
        "# My Wybthon app\n\nRun `wyb dev --open` while developing.\n" + deploy,
        encoding="utf-8",
    )


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def _asset(output: Path, stem: str, data: bytes, suffix: str) -> str:
    digest = hashlib.sha256(data).hexdigest()[:16]
    name = f"assets/{stem}.{digest}.{suffix}"
    (output / name).write_bytes(data)
    return name


def build_app(
    directory: Path, *, output: Path | None = None, base: str | None = None, dev: bool = False
) -> dict[str, Any]:
    """Build source archives, explicit lazy chunks, and a pinned browser bootstrap.

    The output is replaced only after all inputs validate and a complete build
    succeeds. Existing output must contain Wybthon's build marker. A
    production build (the default) turns dev mode off before the
    application imports; `wyb dev` builds with `dev=True`.
    """
    directory = directory.resolve()
    config_path = directory / "wybthon.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    app = (directory / config.get("app-dir", "app")).resolve()
    if not app.is_relative_to(directory) or not app.is_dir():
        raise ValueError("app-dir must name a directory inside the project")
    destination = (output or directory / "dist").resolve()
    if (
        destination == directory
        or directory.is_relative_to(destination)
        or destination == app
        or destination.is_relative_to(app)
    ):
        raise ValueError("The build output must be separate from the project and application sources")
    if destination.exists() and any(destination.iterdir()) and not (destination / ".wyb-build").is_file():
        raise ValueError("Refusing to replace an output directory without a .wyb-build marker")
    entry = config.get("entry", "app.main:app")
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", entry):
        raise ValueError("entry must have the form package.module:function")
    mount = config.get("mount", "#app")
    if not isinstance(mount, str) or not mount.strip():
        raise ValueError("mount must be a CSS selector")
    routes = config.get("prerender", [])
    if not isinstance(routes, list) or any(not isinstance(r, str) or not r.startswith("/") for r in routes):
        raise ValueError("prerender must be a list of paths starting with /")
    crawl = bool(config.get("crawl", False))
    if not isinstance(config.get("snapshot", True), bool):
        raise ValueError("snapshot must be true or false")
    base_path = base if base is not None else config.get("base", "/")
    if (
        not base_path.startswith("/")
        or urlsplit(base_path).netloc
        or urlsplit(base_path).query
        or urlsplit(base_path).fragment
        or ".." in base_path.split("/")
    ):
        raise ValueError("base must be an absolute URL path")
    base_path = base_path.rstrip("/") + "/"
    wheels = config.get("wheels", [])
    if any("==" not in requirement and not requirement.split("#")[0].endswith(".whl") for requirement in wheels):
        raise ValueError("Wheel requirements must use exact versions or explicit wheel URLs")
    server = config.get("server", False)
    if not isinstance(server, bool):
        raise ValueError("server must be true or false")
    server_only = config.get("server-only", [])
    if not isinstance(server_only, list) or any(not isinstance(pattern, str) for pattern in server_only):
        raise ValueError("server-only must be a list of glob patterns")
    routes_dir = _routes_dir(directory, app, config)
    groups: dict[str, dict[str, bytes]] = {"application": {}}
    chunk_patterns = config.get("chunks", {})
    for name in chunk_patterns:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in {"application", "runtime", "bootstrap"}:
            raise ValueError(f"Invalid chunk name: {name}")
        groups[name] = {}
    for path in sorted(app.rglob("*")):
        if not path.is_file() or path.suffix != ".py":
            continue
        if not path.resolve().is_relative_to(directory):
            raise ValueError(f"Source escapes the project: {path}")
        name = path.relative_to(directory).as_posix()
        matched = [
            chunk
            for chunk, patterns in chunk_patterns.items()
            if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)
        ]
        if len(matched) > 1:
            raise ValueError(f"Source belongs to multiple chunks: {name}")
        data = path.read_bytes()
        try:
            compile_source(data, str(path))
        except SyntaxError as exc:
            raise ValueError(f"Invalid Python source at {name}:{exc.lineno}: {exc.msg}") from exc
        if any(fnmatch.fnmatchcase(name, pattern) for pattern in server_only):
            # Server-only modules never reach the browser.
            if not server:
                raise ValueError(f"{name} is server-only, which needs server = true in wybthon.toml")
            continue
        browser = browser_source(data, is_route=routes_dir is not None and path.resolve().is_relative_to(routes_dir))
        if browser.functions and not server:
            raise ValueError(
                f"{name} defines server functions ({', '.join(browser.functions)}), "
                "which need a server: set server = true in wybthon.toml"
            )
        groups[matched[0] if matched else "application"][name] = browser.source.encode("utf-8")
    entry_path = entry.split(":")[0].replace(".", "/") + ".py"
    if entry_path not in groups["application"]:
        raise ValueError("The entry module must exist in the main application bundle")
    package = Path(__file__).parent
    runtime = {
        "wybthon/" + path.relative_to(package).as_posix(): path.read_bytes()
        for path in package.rglob("*.py")
        if path.name not in _SERVER_ONLY or path.parent != package
    }
    runtime["wybthon/_kernel.js"] = (package / "_kernel.js").read_bytes()
    target_python = _pyodide_python(config.get("pyodide-version", PYODIDE_VERSION))
    bytecode = config.get("bytecode", True) and target_python == sys.version_info[:2]
    if bytecode:
        runtime.update(_bytecode(runtime, "/wybthon-app", application=False))
        for name, files in list(groups.items()):
            groups[name] = {**files, **_bytecode(files, "/wybthon-app")}
    template_path = directory / "index.html"
    template = template_path.read_text(encoding="utf-8") if template_path.exists() else _INDEX
    if template.count(_MARKER) != 1:
        raise ValueError(f"index.html must contain exactly one {_MARKER} marker")
    pages: dict[str, str] = {}
    if routes:
        if template.count(_APP_START) != 1 or template.count(_APP_END) != 1:
            raise ValueError(f"Prerendering needs exactly one {_APP_START} ... {_APP_END} region in index.html")
        pages = _prerender(directory, entry, base_path, routes, crawl=crawl)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wyb-build-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        (staging / "assets").mkdir()
        public = directory / "public"
        if public.exists():
            for source in public.rglob("*"):
                if source.is_file():
                    if not source.resolve().is_relative_to(public.resolve()):
                        raise ValueError("Public assets must stay inside public/")
                    target = staging / source.relative_to(public)
                    if target.parts[len(staging.parts)] == "assets":
                        raise ValueError("public/assets is reserved for generated assets")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
        archive_names = {name: _asset(staging, name, _archive(files), "zip") for name, files in groups.items()}
        pyodide_url = (
            config.get(
                "pyodide-url",
                f"https://cdn.jsdelivr.net/pyodide/v{config.get('pyodide-version', PYODIDE_VERSION)}/full/",
            ).rstrip("/")
            + "/"
        )
        stdlib_assets = _trimmed_stdlib(staging, config, pyodide_url, directory, runtime, groups)
        manifest = {
            "format": 1,
            "entry": entry,
            "mount": mount,
            "dev": dev,
            "base": base_path,
            "bytecode": bool(bytecode),
            "server": server,
            "prerendered": sorted(pages),
            "pyodide_url": pyodide_url,
            "stdlib": stdlib_assets[0],
            "stdlib_rest": stdlib_assets[1],
            "stdlib_rest_modules": stdlib_assets[2],
            "packages": config.get("packages", []),
            "wheels": wheels,
            "runtime": _asset(staging, "runtime", _archive(runtime), "zip"),
            "application": archive_names.pop("application"),
            "chunks": archive_names,
        }
        manifest["snapshot"] = _snapshot_key(manifest, config)
        bootstrap = _asset(staging, "bootstrap", (package / "_bootstrap.js").read_bytes(), "js")
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        page = template.replace(_MARKER, _boot_tags(manifest, base_path, bootstrap))
        # The client-only shell: the fallback for routes that weren't prerendered.
        (staging / "200.html").write_text(page, encoding="utf-8")
        (staging / "index.html").write_text(page, encoding="utf-8")
        if pages:
            start, end = page.index(_APP_START), page.index(_APP_END) + len(_APP_END)
            for route, markup in pages.items():
                target = staging / route.strip("/") / "index.html"
                if not target.resolve().is_relative_to(staging.resolve()):
                    raise ValueError(f"Prerender route escapes the output: {route}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(page[:start] + markup + page[end:], encoding="utf-8")
        (staging / ".wyb-build").write_text("1\n", encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="wyb-previous-", dir=destination.parent) as backup_dir:
            backup = Path(backup_dir) / "previous"
            if destination.exists():
                destination.rename(backup)
            try:
                staging.rename(destination)
            except BaseException:
                if backup.exists():
                    backup.rename(destination)
                raise
    return manifest


def _trimmed_stdlib(
    staging: Path,
    config: dict[str, Any],
    pyodide_url: str,
    directory: Path,
    runtime: dict[str, bytes],
    groups: dict[str, dict[str, bytes]],
) -> tuple[str | None, str | None, str | None]:
    """Write the trimmed standard library and the rest, and index the rest; `None`s ship Pyodide's own."""
    mode = config.get("stdlib", "trim")
    if mode not in ("trim", "full"):
        raise ValueError('stdlib must be "trim" or "full"')
    if mode == "full" or config.get("packages") or config.get("wheels"):
        # Packages and wheels import standard library modules the build can't see.
        return None, None, None
    from . import _snapshot
    from ._stdlib import fetch_stdlib, trim

    url = pyodide_url if urlsplit(pyodide_url).scheme else str((directory / "public" / pyodide_url).resolve()) + "/"
    stdlib = fetch_stdlib(url)
    if stdlib is None:
        print("wyb build: couldn't fetch Pyodide's standard library to trim it; shipping it whole", file=sys.stderr)
        return None, None, None
    sources = [data for name, data in runtime.items() if name.endswith(".py")]
    sources += [data for files in groups.values() for name, data in files.items() if name.endswith(".py")]
    trimmed, rest, index = trim(stdlib, sources, extra=_snapshot._STDLIB)
    return _asset(staging, "stdlib", trimmed, "zip"), _asset(staging, "stdlib-rest", rest, "zip"), " ".join(index)


def _routes_dir(directory: Path, app: Path, config: dict[str, Any]) -> Path | None:
    """The file routes directory, when the project has one."""
    configured = config.get("routes")
    if configured is not None and not isinstance(configured, str):
        raise ValueError("routes must name a directory inside the application directory")
    path = (directory / configured).resolve() if configured else app / "routes"
    if configured and (not path.is_relative_to(app) or not path.is_dir()):
        raise ValueError("routes must name a directory inside the application directory")
    return path if path.is_dir() else None


def browser_source(data: bytes, *, is_route: bool = False) -> Split:
    """A module's source as the browser gets it, with its server-only code removed."""
    from importlib.util import decode_source

    return split(decode_source(data), handlers=is_route)


def _snapshot_key(manifest: dict[str, Any], config: dict[str, Any]) -> str | None:
    """The key a boot snapshot is cached under, or `None` when the build doesn't use one.

    A snapshot holds the runtime with the framework imported, not the
    application, so it stays valid across application rebuilds (every
    `wyb dev` reload restores it) and changes only with the runtime
    archive or the Pyodide release. Builds that load Pyodide packages or
    wheels boot normally: those live in the virtual file system, which a
    memory snapshot doesn't hold.
    """
    if not config.get("snapshot", True) or manifest["packages"] or manifest["wheels"]:
        return None
    from . import __version__

    material = json.dumps(
        [1, __version__, manifest["pyodide_url"], manifest["runtime"], manifest.get("stdlib")], separators=(",", ":")
    )
    return hashlib.sha256(material.encode()).hexdigest()[:20]


def _boot_tags(manifest: dict[str, Any], base_path: str, bootstrap: str) -> str:
    """The tags that start the application, replacing the bootstrap marker.

    The manifest is inlined so the bootstrap needn't fetch it, and preload
    hints start downloading the runtime and both source archives while the
    page parses, instead of after the bootstrap has run.
    """
    pyodide_url = manifest["pyodide_url"]
    if not urlsplit(pyodide_url).scheme:
        pyodide_url = base_path + pyodide_url.removeprefix("./")
    hints = [f'<link rel="modulepreload" href="{html.escape(pyodide_url + "pyodide.mjs", quote=True)}" crossorigin>']
    for archive in (manifest["runtime"], manifest["application"], manifest.get("stdlib")):
        if archive is None:
            continue
        href = html.escape(base_path + archive, quote=True)
        hints.append(f'<link rel="preload" href="{href}" as="fetch" crossorigin>')
    inline = json.dumps(manifest, separators=(",", ":")).replace("</", "<\\/")
    return (
        "\n".join(hints)
        + f'\n<script type="application/json" id="wyb-manifest">{inline}</script>'
        + f'\n<script type="module" src="{html.escape(base_path + bootstrap, quote=True)}"></script>'
    )


def _pyodide_python(version: str) -> tuple[int, int] | None:
    """The Python version a Pyodide release runs, when it's known."""
    major = version.split(".", 1)[0]
    if major.isdigit() and int(major) >= 300:
        return (3, int(major) - 300)
    return {"0.26": (3, 12), "0.27": (3, 12), "0.28": (3, 13), "0.29": (3, 13)}.get(".".join(version.split(".")[:2]))


def _bytecode(files: dict[str, bytes], root: str, *, application: bool = True) -> dict[str, bytes]:
    """Unchecked-hash bytecode (PEP 552) for each module, so the browser skips compiling it.

    The interpreter imports ``__pycache__/<module>.<tag>.pyc`` without
    comparing it to the source, so the archive's timestamps don't
    matter. Application modules go through Wybthon's compiler first,
    so a page never compiles a template, and the import hook uses this
    bytecode as is. Only valid when this interpreter's version matches
    the browser runtime's; the caller checks.
    """
    from importlib._bootstrap_external import _code_to_hash_pyc  # type: ignore[attr-defined]
    from importlib.util import source_hash

    tag = sys.implementation.cache_tag
    compiled: dict[str, bytes] = {}
    for name, data in files.items():
        if not name.endswith(".py"):
            continue
        filename = f"{root}/{name}"
        code = compile_source(data, filename) if application else compile(data, filename, "exec", dont_inherit=True)
        folder, _, filename = name.rpartition("/")
        target = (
            f"{folder}/__pycache__/{filename[:-3]}.{tag}.pyc" if folder else f"__pycache__/{filename[:-3]}.{tag}.pyc"
        )
        compiled[target] = bytes(_code_to_hash_pyc(code, source_hash(data), checked=False))
    return compiled


def _prerender(directory: Path, entry: str, base: str, routes: list[str], *, crawl: bool) -> dict[str, str]:
    """Render `routes` in a fresh interpreter; returns route -> container markup."""
    request = json.dumps({"project": str(directory), "entry": entry, "base": base, "routes": routes, "crawl": crawl})
    result = subprocess.run(
        [sys.executable, "-m", "wybthon._prerender"],
        input=request,
        capture_output=True,
        text=True,
        cwd=directory,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"Prerendering failed:\n{result.stderr.strip()}")
    pages: dict[str, str] = json.loads(result.stdout)["pages"]
    return pages


def preview(directory: Path, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve a built app with its base path, client-route fallback, and cache policy."""
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    base = manifest.get("base", "/").rstrip("/")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            requested = unquote(urlsplit(path).path)
            if base and requested != base and not requested.startswith(base + "/"):
                return str(directory / "__missing__")
            relative = requested[len(base) :].lstrip("/")
            target = (directory / relative).resolve()
            if not target.is_relative_to(directory) or any(part.startswith(".") for part in Path(relative).parts):
                return str(directory / "__missing__")
            if target.is_dir():
                target /= "index.html"
            if not target.exists() and "." not in Path(relative).name:
                target = directory / "200.html"
            return str(target)

        def end_headers(self) -> None:
            immutable = bool(re.search(r"/assets/[^/]+\.[a-f0-9]{16}\.(js|zip)$", urlsplit(self.path).path))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable" if immutable else "no-cache")
            super().end_headers()

    with http.server.ThreadingHTTPServer((host, port), Handler) as server:
        print(f"Preview: http://{host}:{port}{base}/", flush=True)
        server.serve_forever()
