"""Serve a repository checkout for the browser benchmark page.

The benchmark page (`benchmarks/app/index.html`) loads the framework's
sources straight from `src/wybthon`, so a comparison can run any two
checkouts side by side without building either. `/__manifest?dir=...`
lists the files to load: Python modules plus the JavaScript kernel.

Usage: python benchmarks/_serve.py --root /path/to/checkout --port 8000
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def handler_for(root: Path) -> type[http.server.SimpleHTTPRequestHandler]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, *args):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):  # noqa: N802
            parsed = urlsplit(self.path)
            if parsed.path != "/__manifest":
                return super().do_GET()
            relative = parse_qs(parsed.query).get("dir", [""])[0]
            target = (root / relative).resolve()
            if not target.is_relative_to(root) or not target.is_dir():
                self.send_error(404)
                return
            files = sorted(
                str(Path(dirpath, name).relative_to(target))
                for dirpath, _dirs, names in os.walk(target)
                for name in names
                if name.endswith(".py") or name == "_kernel.js"
            )
            body = json.dumps(files).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    with Server(("127.0.0.1", args.port), handler_for(args.root.resolve())) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
