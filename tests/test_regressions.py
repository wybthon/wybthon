"""Regression tests for reported issues."""

from __future__ import annotations

import warnings
from pathlib import Path

import wybthon
import wybthon_pytest
from wybthon import action, component, create_effect, html
from wybthon.testing import render


@action
async def save() -> int:
    return 1


@component
def SavesOnMount():
    create_effect(lambda: None, lambda _value, _previous: save())
    return html(t"<b>x</b>")


def test_actions_outside_a_running_loop_dont_warn():
    # wybthon/wybthon#46: `_event_loop` used `asyncio.get_event_loop_policy`,
    # deprecated in Python 3.14 and removed in 3.16.
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        with render(SavesOnMount()) as screen:
            assert screen.text() == "x"


def test_the_pytest_plugin_never_compiles_wybthons_own_modules():
    # wybthon/wybthon#44: installed from a wheel, pytest rewrites the plugin's
    # whole distribution, and compiling `wybthon.compiler` while it imported
    # was circular.
    package = Path(wybthon.__file__).parent
    assert wybthon_pytest._is_wybthon_module(package / "compiler.py")
    assert wybthon_pytest._is_wybthon_module(str(package / "router" / "_router.py"))
    assert not wybthon_pytest._is_wybthon_module(Path(__file__))
    assert not wybthon_pytest._is_wybthon_module(None)
