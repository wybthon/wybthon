"""Guard decorated call signatures and schema-aware store reads."""

import subprocess
import sys
from pathlib import Path


def test_public_typing_contracts():
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "mypy", "--strict", "--no-pretty", "--follow-imports=silent"]
    positive = subprocess.run(command + ["tests/typing/valid.py"], cwd=root, capture_output=True, text=True)
    assert positive.returncode == 0, positive.stdout + positive.stderr
    negative = subprocess.run(command + ["tests/typing/invalid.py"], cwd=root, capture_output=True, text=True)
    assert negative.returncode == 1, negative.stdout + negative.stderr
    assert negative.stdout.count("error:") == 9, negative.stdout
    for message in (
        "incompatible type",
        "Missing named argument",
        "Unexpected keyword argument",
        "Incompatible types in assignment",
        "Unknown store field",
        "must be annotated Prop[T]",
    ):
        assert message in negative.stdout, negative.stdout


def test_typed_component_fixture_executes_in_renderer(wyb, root_element):
    import runpy

    from conftest import collect_texts

    from wybthon import create_signal, flush

    fixture = runpy.run_path(str(Path(__file__).parent / "typing" / "valid.py"))
    name, rename = create_signal("Ada")
    count, set_count = create_signal(2)
    wyb["reconciler"].render(fixture["Greeting"](name=name, count=count), root_element)
    assert "AdaAda" in collect_texts(root_element.element)
    rename("Grace")
    set_count(1)
    flush()
    assert "Grace" in collect_texts(root_element.element)
