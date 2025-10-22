"""Simple threaded dev server with live-reload via Server-Sent Events (SSE)."""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import threading
import time
import webbrowser
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit


class SSEHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that serves files and a /__sse endpoint for reload events."""

    watchers = []  # type: ignore[var-annotated]
    root: Path = Path.cwd()
    mounts: list[tuple[str, Path]] = []

    def end_headers(self) -> None:  # noqa: D401 - ensure dev assets are never cached
        # Add aggressive no-store headers to avoid stale assets during development
        # This applies to all responses (including directory listings and static files).
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):  # noqa: N802
        if self.path == "/__sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            # Register this client
            self.watchers.append(self.wfile)
            try:
                # Keep open until client disconnects
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
        return super().do_GET()

    # Map request path to filesystem path honoring mounts, falling back to root
    def translate_path(self, path: str) -> str:  # noqa: D401 - behavior explained in doc above
        return str(translate_request_path(path, self.root, self.mounts))

    @classmethod
    def notify_reload(cls) -> None:
        """Notify connected SSE clients to reload by sending a reload event."""
        dead: list = []
        for w in list(cls.watchers):
            try:
                w.write(b"event: reload\n")
                w.write(b"data: {}\n\n")
                w.flush()
            except Exception:
                dead.append(w)
        for d in dead:
            try:
                cls.watchers.remove(d)
            except Exception:
                pass


def _walk_files(paths: Iterable[Path]) -> Iterable[Path]:
    """Yield all files under the provided paths, descending into directories."""
    for p in paths:
        if p.is_dir():
            for root, _dirs, files in os.walk(p):
                for f in files:
                    yield Path(root) / f
        elif p.exists():
            yield p


def _sanitize_segments(path: str) -> list[str]:
    """Split path and drop empty/dot-dot segments to prevent traversal."""
    # Strip query/fragment and split; drop unsafe segments
    p = urlsplit(path).path
    parts = [seg for seg in p.split("/") if seg not in ("", ".", "..")]
    return parts


def translate_request_path(path: str, root: Path, mounts: list[tuple[str, Path]]) -> Path:
    """Translate a URL path to a filesystem path using mounts, with fallback to root.

    Longest-prefix match wins. Prevents directory traversal by dropping dangerous segments.
    """
    # Sort mounts by longest prefix to ensure the most specific mount wins
    sorted_mounts = sorted(mounts or [], key=lambda m: len(m[0]), reverse=True)
    request_path = urlsplit(path).path
    for prefix, base in sorted_mounts:
        if prefix == "/":
            continue  # handled as fallback below
        if request_path == prefix or request_path.startswith(prefix + "/"):
            rel = request_path[len(prefix) :]
            segments = _sanitize_segments(rel)
            fp = base
            for seg in segments:
                fp = fp / seg
            return fp
    # Fallback to root
    segments = _sanitize_segments(request_path)
    fp = root
    for seg in segments:
        fp = fp / seg
    return fp


def parse_mounts(mount_args: Iterable[str], base_dir: Path) -> list[tuple[str, Path]]:
    """Parse --mount arguments of the form "/prefix=path".

    - Prefix must start with "/"; if omitted, it will be added
    - Paths are resolved relative to base_dir if not absolute
    - Duplicate prefixes are allowed; last one wins via order (we keep all, sorted later)
    """
    mounts: list[tuple[str, Path]] = []
    for raw in mount_args:
        if "=" not in raw:
            # Treat as root mount
            prefix, raw_path = "/", raw
        else:
            prefix, raw_path = raw.split("=", 1)
        prefix = prefix.strip() or "/"
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        path = Path(raw_path.strip())
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        mounts.append((prefix, path))
    return mounts


def serve(
    directory: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    watch: Iterable[str] = ("src", "examples"),
    mounts: Iterable[str] | None = None,
    open_browser: bool = False,
    open_path: str | None = None,
) -> None:
    """Run a static dev server with auto-reload for the given directory."""
    os.chdir(directory)
    SSEHandler.root = Path(directory)
    handler_cls = SSEHandler
    # Configure static mounts
    handler_cls.mounts = parse_mounts(mounts or [], Path(directory))

    class ThreadingReuseTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        # Handle each request in a separate thread so long-lived SSE connections
        # do not block concurrent static file requests during development.
        daemon_threads = True
        allow_reuse_address = True

    def watcher() -> None:
        mtimes: dict[Path, float] = {}
        roots = [Path(w) for w in watch]
        while True:
            changed = False
            for f in _walk_files(roots):
                try:
                    m = f.stat().st_mtime
                except Exception:
                    continue
                prev = mtimes.get(f)
                if prev is None:
                    mtimes[f] = m
                elif m > prev:
                    mtimes[f] = m
                    changed = True
            if changed:
                handler_cls.notify_reload()
            time.sleep(0.5)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()

    # Try to bind desired port; if busy, fall back to next available up to +20
    candidates = [port] if port and port > 0 else [0]
    if port and port > 0:
        candidates += list(range(port + 1, port + 21))

    httpd = None
    bound_port = None
    last_err = None
    for p in candidates:
        try:
            httpd = ThreadingReuseTCPServer((host, p), handler_cls)
            bound_port = httpd.server_address[1]
            break
        except OSError as e:
            last_err = e
            continue
    if httpd is None:
        raise last_err if last_err is not None else OSError("Failed to bind server")

    url = f"http://{host}:{bound_port}"
    print("\nWybthon Dev Server")
    print("===================")
    print(f"Directory: {Path(directory).resolve()}")
    print(f"Host:      {host}")
    print(f"Port:      {bound_port}")
    if port and bound_port != port:
        print(f"(requested port {port} was busy; using {bound_port})")
    # Show mounts and watch list for quick visibility
    if handler_cls.mounts:
        print("Mounts:")
        for prefix, pth in handler_cls.mounts:
            print(f"  {prefix} -> {pth}")
    else:
        print(f"Mounts:\n  / -> {Path(directory).resolve()}")
    if watch:
        try:
            watch_list = ", ".join(str(Path(w)) for w in watch)
        except Exception:
            watch_list = ", ".join(map(str, watch))
        print(f"Watching: {watch_list}")
    print(f"\nServing at: {url}")

    # Optionally open a browser tab
    if open_browser:
        # Heuristic default path if not provided
        selected_path = open_path
        base = Path(directory)
        try:
            if not selected_path:
                if (base / "index.html").exists():
                    selected_path = "/"
                elif (base / "examples" / "demo" / "index.html").exists():
                    selected_path = "/examples/demo/"
                else:
                    selected_path = "/"
        except Exception:
            selected_path = selected_path or "/"
        try:
            webbrowser.open(url + (selected_path or "/"))
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the `wyb` development server."""
    parser = argparse.ArgumentParser(prog="wyb", description="Wybthon dev server")
    sub = parser.add_subparsers(dest="cmd")
    pdev = sub.add_parser("dev", help="Start dev server with auto-reload")
    pdev.add_argument("--dir", default=str(Path(__file__).resolve().parents[2]), help="Root dir to serve")
    pdev.add_argument("--host", default="127.0.0.1")
    pdev.add_argument("--port", type=int, default=8000)
    pdev.add_argument("--watch", nargs="*", default=["src", "examples"])
    pdev.add_argument(
        "--mount",
        action="append",
        default=[],
        help="Mount additional static paths as /prefix=path. Can be repeated.",
    )
    pdev.add_argument("--open", action="store_true", help="Open a browser to the server URL")
    pdev.add_argument("--open-path", default=None, help="Path to open (e.g. /examples/demo/)")

    args = parser.parse_args(argv)
    if args.cmd == "dev":
        serve(
            args.dir,
            host=args.host,
            port=args.port,
            watch=args.watch,
            mounts=args.mount,
            open_browser=args.open,
            open_path=args.open_path,
        )
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
