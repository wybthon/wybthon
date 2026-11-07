"""Trimming Pyodide's standard library to what an app imports (`wybthon._stdlib`)."""

from __future__ import annotations

import io
import json
import zipfile

from wybthon import _stdlib
from wybthon.build import build_app, init_app


def _library() -> bytes:
    files = {
        "json/__init__.py": "from .decoder import JSONDecoder\n",
        "json/decoder.py": "import re\n",
        "re/__init__.py": "import enum\n",
        "enum.py": "",
        "email/__init__.py": "",
        "email/parser.py": "import email.feedparser\n",
        "email/feedparser.py": "",
        "heapq.py": "if __name__ == '__main__':\n    import doctest\n",
        "doctest.py": "import unittest\n",
        "unittest/__init__.py": "",
        "lazy.py": "def later():\n    import email\n",
        "typing.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import email\n",
        "encodings/__init__.py": "from . import aliases\n",
        "encodings/aliases.py": "",
        "encodings/cp1250.py": "",
        "_pyodide/__init__.py": "",
        "_pyodide/docstring.py": "",
        "data/table.txt": "kept",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def test_trimming_keeps_what_is_imported_and_indexes_the_rest():
    app = [b"import json\nimport heapq\nimport lazy\nimport typing\n"]
    trimmed, rest, index = _stdlib.trim(_library(), app)
    kept = set(zipfile.ZipFile(io.BytesIO(trimmed)).namelist())
    others = set(zipfile.ZipFile(io.BytesIO(rest)).namelist())
    assert {"json/__init__.py", "json/decoder.py", "re/__init__.py", "enum.py", "heapq.py", "lazy.py"} <= kept
    assert {"_pyodide/__init__.py", "_pyodide/docstring.py", "encodings/aliases.py", "data/table.txt"} <= kept
    # Imports in functions, under TYPE_CHECKING, or behind a main guard don't count.
    assert {
        "email/__init__.py",
        "email/parser.py",
        "doctest.py",
        "unittest/__init__.py",
        "encodings/cp1250.py",
    } <= others
    assert not kept & others
    assert "email" in index and "doctest" in index and "encodings.*" in index and "json" not in index


def test_a_build_ships_the_trimmed_library_and_its_index(tmp_path, monkeypatch):
    monkeypatch.setattr(_stdlib, "fetch_stdlib", lambda url: _library())
    project = tmp_path / "project"
    init_app(project)
    manifest = build_app(project)
    assert manifest["stdlib"].startswith("assets/stdlib.") and manifest["stdlib_rest"].startswith("assets/stdlib-rest.")
    assert "email" in manifest["stdlib_rest_modules"].split()
    page = (project / "dist" / "index.html").read_text()
    assert manifest["stdlib"] in page  # preloaded
    inline = json.loads(page.split('id="wyb-manifest">', 1)[1].split("</script>", 1)[0])
    assert inline["stdlib"] == manifest["stdlib"]


def test_full_mode_and_an_unavailable_library_ship_pyodides_own(tmp_path, monkeypatch):
    project = tmp_path / "project"
    init_app(project)
    assert build_app(project)["stdlib"] is None  # the offline fixture: nothing to trim
    monkeypatch.setattr(_stdlib, "fetch_stdlib", lambda url: _library())
    config = project / "wybthon.toml"
    config.write_text('stdlib = "full"\n' + config.read_text())
    assert build_app(project)["stdlib"] is None
