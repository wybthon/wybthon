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
    assert negative.stdout.count("error:") == 7, negative.stdout
    for message in (
        "incompatible type",
        "Missing named argument",
        "Unexpected keyword argument",
        "Incompatible types in assignment",
        "Unknown store field",
    ):
        assert message in negative.stdout, negative.stdout
