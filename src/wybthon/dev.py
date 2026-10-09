"""The `wyb` command: develop, build, and preview Wybthon projects.

A project is a directory with a `wybthon.toml` (create one with
`wyb init`). `wyb dev` builds it in development mode, serves the build,
rebuilds when a source changes, and reloads connected pages over
Server-Sent Events. `wyb build` writes a production build and
`wyb preview` serves one.

Use the [`main`][wybthon.dev.main] function for CLI entry, or call
[`serve`][wybthon.dev.serve] directly to embed the server.
"""

from __future__ import annotations

import argparse
import http.server
import importlib.metadata
import os
import socketserver
import threading
import time
import webbrowser
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

__all__ = ["serve", "main"]

_RELOAD_SCRIPT = "<script>new EventSource('/__sse').addEventListener('reload', () => location.reload());</script>"


class SSEHandler(http.server.SimpleHTTPRequestHandler):
    """Serves a development build and a `/__sse` endpoint for reload events.

    Class attributes:
        watchers: `wfile` objects of connected SSE clients.
        root: The build output directory.
        app_base: The application's base path; other paths return 404,
            and unknown paths under it serve the client shell.
    """

    watchers: list = []
    root: Path = Path.cwd()
    app_base: str = "/"

    def end_headers(self) -> None:
        """Append no-cache headers to every response to avoid stale assets."""
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        """Serve the SSE stream or a file from the build."""
        if self.path == "/__sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.watchers.append(self.wfile)
            try:
                while True:
                    time.sleep(1)
            except Exception:
                pass
            finally:
                try:
                    self.watchers.remove(self.wfile)
                except Exception:
                    pass
            return
        super().do_GET()

    def translate_path(self, path: str) -> str:
        """Map a request under the app base to the build, falling back to the client shell."""
        requested = urlsplit(path).path
        base = self.app_base.rstrip("/")
        if base and requested != base and not requested.startswith(base + "/"):
            return str(self.root / "__missing__")
        target = self.root
        for segment in requested[len(base) :].split("/"):
            if segment not in ("", ".", ".."):
                target = target / segment
        if target.is_dir():
            target = target / "index.html"
        if not target.exists() and "." not in target.name:
            target = self.root / "200.html"
        return str(target)

    @classmethod
    def notify_reload(cls) -> None:
        """Send a `reload` SSE event to every connected client."""
        for w in list(cls.watchers):
            try:
                w.write(b"event: reload\ndata: {}\n\n")
                w.flush()
            except Exception:
                try:
                    cls.watchers.remove(w)
                except ValueError:
                    pass


def _walk_files(paths: Iterable[Path]) -> Iterable[Path]:
    """Yield every file under `paths`, descending into directories recursively."""
    for p in paths:
        if p.is_dir():
            for root, _dirs, files in os.walk(p):
                for f in files:
                    yield Path(root) / f
        elif p.exists():
            yield p


def serve(
    directory: str | Path = ".",
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = False,
    open_path: str | None = None,
) -> None:
    """Build a project in development mode, serve it, and rebuild on change.

    Args:
        directory: The project directory (containing `wybthon.toml`).
        host: Bind host.
        port: Preferred port. If busy, the server tries the next 20
            ports before failing.
        open_browser: When `True`, open a browser tab to the app after
            binding.
        open_path: Path to open instead of the app's base path.

    Raises:
        ValueError: `directory` isn't a Wybthon project.
    """
    import tomllib

    from .build import build_app

    project = Path(directory).resolve()
    config_path = project / "wybthon.toml"
    if not config_path.exists():
        raise ValueError(f"{project} has no wybthon.toml; create a project with `wyb init`")
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    def rebuild() -> None:
        manifest = build_app(project, dev=True)
        SSEHandler.app_base = manifest["base"]
        for page in (project / "dist").rglob("*.html"):
            page.write_text(page.read_text(encoding="utf-8").replace("</body>", _RELOAD_SCRIPT + "</body>"))

    rebuild()
    SSEHandler.root = project / "dist"
    watch = [project / name for name in (config.get("app-dir", "app"), "public", "index.html", "wybthon.toml")]

    class ThreadingReuseTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        """Threaded TCP server so long-lived SSE clients don't block requests."""

        daemon_threads = True
        allow_reuse_address = True

    def watcher() -> None:
        def scan() -> dict[Path, int]:
            result = {}
            for path in _walk_files(watch):
                if "__pycache__" not in path.parts:
                    try:
                        result[path] = path.stat().st_mtime_ns
                    except OSError:
                        pass
            return result

        mtimes = scan()
        while True:
            time.sleep(0.5)
            current = scan()
            if current != mtimes:
                mtimes = current
                try:
                    rebuild()
                except Exception as exc:
                    print(f"Build failed: {exc}", flush=True)
                    continue
                SSEHandler.notify_reload()

    threading.Thread(target=watcher, daemon=True).start()

    candidates = [port] if port and port > 0 else [0]
    if port and port > 0:
        candidates += list(range(port + 1, port + 21))
    httpd = None
    last_err: OSError | None = None
    for candidate in candidates:
        try:
            httpd = ThreadingReuseTCPServer((host, candidate), SSEHandler)
            break
        except OSError as exc:
            last_err = exc
    if httpd is None:
        raise last_err if last_err is not None else OSError("Failed to bind server")
    bound_port = httpd.server_address[1]
    url = f"http://{host}:{bound_port}"
    print("\nWybthon Dev Server")
    print("===================")
    print(f"Project:  {project}")
    if port and bound_port != port:
        print(f"(requested port {port} was busy; using {bound_port})")
    print(f"Watching: {', '.join(str(path.relative_to(project)) for path in watch)}")
    print(f"\nServing at: {url}{SSEHandler.app_base}")
    if open_browser:
        try:
            webbrowser.open(url + (open_path or SSEHandler.app_base))
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for `wyb`.

    Args:
        argv: Optional argument list (defaults to `sys.argv[1:]`).

    Returns:
        Process exit code: `0` on success, non-zero on usage errors.
    """
    parser = argparse.ArgumentParser(prog="wyb", description="Wybthon development and production tools")
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {importlib.metadata.version('wybthon')}",
        help="Show version and exit",
    )
    sub = parser.add_subparsers(dest="cmd")
    pdev = sub.add_parser("dev", help="Build in development mode, serve, and reload on change")
    pdev.add_argument("--dir", default=".", help="Project directory (containing wybthon.toml)")
    pdev.add_argument("--host", default="127.0.0.1", help="Bind address")
    pdev.add_argument("--port", type=int, default=8000, help="Port to bind")
    pdev.add_argument("--open", action="store_true", help="Open a browser to the app")
    pdev.add_argument("--open-path", default=None, help="Path to open instead of the app's base path")

    pinit = sub.add_parser("init", help="Create a starter project")
    pinit.add_argument("directory", nargs="?", default=".")
    pbuild = sub.add_parser("build", help="Write a production build")
    pbuild.add_argument("--dir", default=".", help="Project directory")
    pbuild.add_argument("--out", default=None, help="Output directory (default: <dir>/dist)")
    pbuild.add_argument("--base", default=None, help="Base URL path the app is served from")
    ppreview = sub.add_parser("preview", help="Serve a production build")
    ppreview.add_argument("--dir", default="dist", help="Build directory")
    ppreview.add_argument("--host", default="127.0.0.1", help="Bind address")
    ppreview.add_argument("--port", type=int, default=8000, help="Port to bind")

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 1
    from .build import build_app, init_app, preview

    try:
        if args.cmd == "init":
            init_app(Path(args.directory))
            print(f"Created {Path(args.directory).resolve()}")
        elif args.cmd == "build":
            build_app(Path(args.dir), output=Path(args.out) if args.out else None, base=args.base)
            print(f"Built {Path(args.out or Path(args.dir) / 'dist').resolve()}")
        elif args.cmd == "preview":
            preview(Path(args.dir), host=args.host, port=args.port)
        else:
            serve(args.dir, host=args.host, port=args.port, open_browser=args.open, open_path=args.open_path)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
