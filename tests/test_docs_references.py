"""Every import and API cross-reference in the documentation names something that exists."""

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted([ROOT / "README.md", *(ROOT / "docs").rglob("*.md")])
# RFCs and the changelog record history: they name APIs as they were.
PAGES = [p for p in PAGES if "rfcs" not in p.parts and p.name not in ("changelog.md", "CHANGELOG.md")]

FENCE = re.compile(r"```python\n(.*?)```", re.S)
IMPORT = re.compile(r"^\s*from (wybthon[\w.]*) import (\([^)]*\)|[^\n#]+)", re.M)
XREF = re.compile(r"\]\[(wybthon(?:\.\w+)+)\]")


def _names(spec: str) -> list[str]:
    spec = spec.strip().strip("()")
    out = []
    for part in spec.split(","):
        part = part.split("#")[0].strip()
        if part:
            out.append(part.split(" as ")[0].strip())
    return out


def _imports() -> list[tuple[str, str, str]]:
    found = []
    for page in PAGES:
        for block in FENCE.findall(page.read_text(encoding="utf-8")):
            for module, spec in IMPORT.findall(block):
                for name in _names(spec):
                    found.append((page.relative_to(ROOT).as_posix(), module, name))
    return found


def _xrefs() -> list[tuple[str, str]]:
    found = []
    for page in PAGES:
        for target in XREF.findall(page.read_text(encoding="utf-8")):
            found.append((page.relative_to(ROOT).as_posix(), target))
    return sorted(set(found))


def _resolve(target: str) -> bool:
    if target == "wybthon.symbol":  # the placeholder in the style guide's own instructions
        return True
    parts = target.split(".")
    for split in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        try:
            for attr in parts[split:]:
                obj = getattr(obj, attr)
        except AttributeError:
            return False
        return True
    return False


@pytest.mark.parametrize(("page", "module", "name"), _imports())
def test_documented_imports_exist(page, module, name):
    assert hasattr(importlib.import_module(module), name), f"{page}: from {module} import {name}"


@pytest.mark.parametrize(("page", "target"), _xrefs())
def test_cross_references_resolve(page, target):
    assert _resolve(target), f"{page}: [{target}]"
