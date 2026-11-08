"""Hot module replacement for `wyb dev` (RFC 0006).

When an application module changes, `wyb dev` sends its new source to
connected pages instead of reloading them. `apply` runs the module's new
code in its existing namespace and patches what other code holds:

- An `@component` keeps its identity: the old `Component` object takes
  the new body, so every module that imported it renders the new code.
- A plain function keeps its identity too, when its new code fits its
  closure: its code object is swapped in place.

Then every mounted instance of a component from a changed module (or from
a module that imported one) runs its body again in place, with the same
props. The rest of the page, and state that lives outside those
components (stores, module-level signals in modules that didn't change),
stays as it was. As with Solid's hot reloading, the remounted components'
own local state starts over.

Anything this can't do in place (a module that renders at import time, a
change that fails to compile or run, an instance that rendered nothing)
makes `apply` return False, and the page reloads instead.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import kernel, reconciler
from ._warnings import log_error
from .component import Component
from .reactivity import _core

__all__ = ["enable", "apply"]

# Mounted component instances: context id -> (VNode, context, parent id, namespace).
_live: dict[int, tuple[Any, Any, int, str | None]] = {}

# True while a changed module's new code runs.
_reloading = False


class _Unsupported(Exception):
    """A change that can't be applied in place; the page reloads instead."""


def _track(vnode: Any, ctx: Any, parent_id: int, ns: str | None) -> None:
    key = id(ctx)
    _live[key] = (vnode, ctx, parent_id, ns)
    ctx._add_cleanup(lambda: _live.pop(key, None))


def enable() -> None:
    """Start recording mounted components (called by `wyb dev`'s page before the application imports)."""
    reconciler._hot_track = _track


def _check_render() -> None:
    """Called by `render` and `hydrate`: a module that renders when it's imported can't be replaced in place."""
    if _reloading:
        raise _Unsupported("the module renders when it's imported")


def _drop_bytecode(path: Path) -> None:
    """Remove compiled bytecode for `path`, which would otherwise shadow its new source."""
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for compiled in cache.glob(path.stem + ".*.pyc"):
            try:
                compiled.unlink()
            except OSError:
                pass


def _patch_function(old: types.FunctionType, new: types.FunctionType) -> bool:
    """Give `old` the code of `new`, keeping its identity; False when their closures differ."""
    if old.__code__.co_freevars != new.__code__.co_freevars or (old.__closure__ is None) != (new.__closure__ is None):
        return False
    old.__code__ = new.__code__
    old.__defaults__ = new.__defaults__
    old.__kwdefaults__ = new.__kwdefaults__
    old.__annotations__ = new.__annotations__
    old.__doc__ = new.__doc__
    old.__dict__.update(new.__dict__)
    return True


def _rerun(module: types.ModuleType) -> list[Component]:
    """Run a module's new source in its namespace; returns the components that changed."""
    global _reloading
    from .compiler import compile_source

    filename = getattr(module, "__file__", None)
    if not filename or not filename.endswith(".py"):
        raise _Unsupported(f"{module.__name__} has no source file")
    path = Path(filename)
    _drop_bytecode(path)
    code = compile_source(path.read_bytes(), filename)
    namespace = module.__dict__
    previous = dict(namespace)
    _reloading = True
    try:
        exec(code, namespace)
    finally:
        _reloading = False
    changed: list[Component] = []
    for name, value in list(namespace.items()):
        old = previous.get(name)
        if old is None or old is value:
            continue
        if type(old) is Component and type(value) is Component:
            old.fn = value.fn
            old._props_class = None
            old._resolved = False
            for attribute in ("__doc__", "__wrapped__", "__annotations__"):
                if hasattr(value, attribute):
                    setattr(old, attribute, getattr(value, attribute))
            namespace[name] = old
            changed.append(old)
        elif (
            type(old) is types.FunctionType
            and type(value) is types.FunctionType
            and old.__module__ == module.__name__
            and _patch_function(old, value)
        ):
            namespace[name] = old
    return changed


def _dependents(names: set[str]) -> set[str]:
    """Application modules that hold a module, or something defined in one, from `names`.

    Only modules of the same top-level packages are considered: the
    framework and the standard library never import application code.
    """
    packages = {name.split(".", 1)[0] for name in names}
    found: set[str] = set()
    for name, module in list(sys.modules.items()):
        if name in names or module is None or name.split(".", 1)[0] not in packages:
            continue
        for value in list(vars(module).values()):
            owner = value.__name__ if type(value) is types.ModuleType else getattr(value, "__module__", None)
            if owner in names:
                found.add(name)
                break
    return found


def apply(modules: list[str], files: Sequence[str] = ()) -> bool:
    """Replace `modules` in place and remount what renders them; False when the page should reload.

    `files` are the changed sources' paths. Their compiled bytecode is
    removed whether or not their modules have been imported: a build's
    bytecode is used as is, so a module imported after this update would
    otherwise load its old code.
    """
    for file in files:
        _drop_bytecode(Path(file))
    try:
        names = {name for name in modules if name in sys.modules}
        if not names:
            return True
        for name in sorted(names):
            _rerun(sys.modules[name])
        # Release the replaced code objects the probe cache remembers.
        _core._escaped_code.clear()
        affected = names | _dependents(names)
        targets = []
        for vnode, ctx, parent_id, ns in list(_live.values()):
            comp = vnode.tag
            fn = comp.fn if type(comp) is Component else comp
            if getattr(fn, "__module__", None) in affected and not ctx._disposed:
                targets.append((vnode, ctx, parent_id, ns))
        # Remount the outermost affected instances only: an inner one is
        # remounted with its parent. Decide before remounting anything, since
        # remounting a parent detaches its old children.
        chosen = {id(ctx) for _vnode, ctx, _parent, _ns in targets}
        outermost = []
        for target in targets:
            owner = target[1]._parent
            while owner is not None and id(owner) not in chosen:
                owner = owner._parent
            if owner is None:
                outermost.append(target)
        for vnode, _ctx, parent_id, ns in outermost:
            if not reconciler._hot_remount(vnode, parent_id, ns):
                raise _Unsupported("a changed component rendered nothing to replace")
        _core.flush()
        kernel.commit()
        return True
    except Exception as exc:
        log_error(f"Hot update failed, reloading: {exc}", exc if not isinstance(exc, _Unsupported) else None)
        return False
