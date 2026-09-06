"""Deterministic static app bundles and a production preview server."""

from __future__ import annotations

import fnmatch
import hashlib
import html
import http.server
import io
import json
import re
import shutil
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

PYODIDE_VERSION = "314.0.6"
_MARKER = "<!-- wyb:bootstrap -->"
_INDEX = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wybthon app</title></head>
<body><p id="wyb-loading" role="status">Loading...</p><div id="app"></div>
<!-- wyb:bootstrap -->
</body></html>
"""
_STARTER = '''"""A run-once component with a reactive counter."""

from wybthon import button, component, create_signal, div, h1, render


@component
def App():
    count, set_count = create_signal(0)
    return div(
        h1("My Wybthon app"),
        button(lambda: f"Count: {count()}", on_click=lambda event: set_count(lambda n: n + 1)),
    )


def main():
    return render(App(), "#app")
'''


def init_app(directory: Path) -> None:
    """Create a reviewable starter project without overwriting existing files."""
    directory = directory.resolve()
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Destination isn't empty: {directory}")
    (directory / "app").mkdir(parents=True, exist_ok=True)
    (directory / "app" / "__init__.py").write_text('"""Application package."""\n', encoding="utf-8")
    (directory / "app" / "main.py").write_text(_STARTER, encoding="utf-8")
    (directory / "index.html").write_text(_INDEX, encoding="utf-8")
    (directory / "wybthon.toml").write_text(
        f'entry = "app.main:main"\napp-dir = "app"\nbase = "/"\n'
        f'pyodide-version = "{PYODIDE_VERSION}"\npackages = []\nwheels = []\n'
        '\n[chunks]\n# charts = ["app/charts/**"]\n',
        encoding="utf-8",
    )
    (directory / "pyproject.toml").write_text(
        '[project]\nname = "wybthon-app"\nversion = "0.1.0"\nrequires-python = ">=3.12"\ndependencies = ["wybthon"]\n'
        '\n[tool.mypy]\nplugins = ["wybthon.mypy_plugin"]\n',
        encoding="utf-8",
    )
    (directory / ".gitignore").write_text("dist/\n.venv/\n__pycache__/\n.mypy_cache/\n", encoding="utf-8")
    (directory / "README.md").write_text(
        "# My Wybthon app\n\nRun `wyb dev --open` while developing.\n"
        "Run `wyb build`, then `wyb preview` to check the production output.\n\n"
        "Deploy the contents of `dist/` to a static host with an HTML fallback for client routes.\n",
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


def build_app(directory: Path, *, output: Path | None = None, base: str | None = None) -> dict[str, Any]:
    """Build source archives, explicit lazy chunks, and a pinned browser bootstrap.

    The output is replaced only after all inputs validate and a complete build
    succeeds. Existing output must contain Wybthon's build marker.
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
    entry = config.get("entry", "app.main:main")
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", entry):
        raise ValueError("entry must have the form package.module:function")
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
            compile(data, str(path), "exec")
        except SyntaxError as exc:
            raise ValueError(f"Invalid Python source at {name}:{exc.lineno}: {exc.msg}") from exc
        groups[matched[0] if matched else "application"][name] = data
    entry_path = entry.split(":")[0].replace(".", "/") + ".py"
    if entry_path not in groups["application"]:
        raise ValueError("The entry module must exist in the main application bundle")
    package = Path(__file__).parent
    runtime = {
        "wybthon/" + path.relative_to(package).as_posix(): path.read_bytes()
        for path in package.rglob("*.py")
        if path.name not in {"build.py", "dev.py", "mypy_plugin.py"}
    }
    template_path = directory / "index.html"
    template = template_path.read_text(encoding="utf-8") if template_path.exists() else _INDEX
    if template.count(_MARKER) != 1:
        raise ValueError(f"index.html must contain exactly one {_MARKER} marker")
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
        manifest = {
            "format": 1,
            "entry": entry,
            "base": base_path,
            "pyodide_url": config.get(
                "pyodide-url",
                f"https://cdn.jsdelivr.net/pyodide/v{config.get('pyodide-version', PYODIDE_VERSION)}/full/",
            ).rstrip("/")
            + "/",
            "packages": config.get("packages", []),
            "wheels": wheels,
            "runtime": _asset(staging, "runtime", _archive(runtime), "zip"),
            "application": archive_names.pop("application"),
            "chunks": archive_names,
        }
        bootstrap = _asset(staging, "bootstrap", (package / "_bootstrap.js").read_bytes(), "js")
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (staging / "index.html").write_text(
            template.replace(
                _MARKER, f'<script type="module" src="{html.escape(base_path + bootstrap, quote=True)}"></script>'
            ),
            encoding="utf-8",
        )
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
                target = directory / "index.html"
            return str(target)

        def end_headers(self) -> None:
            immutable = bool(re.search(r"/assets/[^/]+\.[a-f0-9]{16}\.(js|zip)$", urlsplit(self.path).path))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable" if immutable else "no-cache")
            super().end_headers()

    with http.server.ThreadingHTTPServer((host, port), Handler) as server:
        print(f"Preview: http://{host}:{port}{base}/", flush=True)
        server.serve_forever()
