"""Measure native collection CPU costs, retained store memory, and bundle size.

Run each checkout in a fresh process with the same interpreter. Setup,
verification, disposal, and explicit garbage collection are outside timings.
These measurements complement the browser and native DOM benchmarks; they
aren't predictions of browser latency or memory usage.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path


def run(repo, iterations, warmup):
    sys.path.insert(0, str(repo / "src"))
    import wybthon
    from wybthon import create_effect, create_root, create_signal, create_store, flush, map_array
    from wybthon._vector import Vector
    from wybthon.build import _archive

    if not Path(wybthon.__file__).resolve().is_relative_to(repo / "src"):
        raise RuntimeError("Imported Wybthon doesn't belong to the selected checkout")

    values = list(range(10000))
    entities = [{"id": i, "n": 0} for i in values]
    vector = Vector(values)

    def check_vector(result, expected):
        assert list(result) == expected
        assert list(vector) == values

    def mapping(operation):
        source, write = create_signal(values, equals=False)
        mapped, dispose = create_root(lambda stop: (map_array(source, lambda item, index: (item, index)), stop))
        previous = mapped()[:]
        new = values + list(range(10000, 11000)) if operation == "append" else values[::-1]
        if operation == "same":
            new = values

        def update():
            write(new)
            flush()
            return mapped()

        def verify(result):
            assert [row[0] for row in result] == new
            assert [row[1]() for row in result] == list(range(len(new)))
            assert result[0] is previous[-1 if operation == "reverse" else 0]

        return update, verify, dispose

    def store_updates():
        store, write = create_store(entities)
        observed = {}

        def subscribe(dispose):
            def watch(index):
                create_effect(lambda: store[index].n, lambda value: observed.__setitem__(index, value))

            for index in range(0, len(values), 10):
                watch(index)
            return dispose

        dispose = create_root(subscribe)
        flush()

        def edit(draft):
            for index in range(0, len(values), 10):
                draft[index].n = 1

        def update():
            write(edit)
            flush()

        def verify(_):
            assert len(observed) == 1000 and all(value == 1 for value in observed.values())

        return update, verify, dispose

    def store_create():
        def verify(result):
            store, _ = result
            assert len(store) == len(entities) and store[-1].id == 9999

        return lambda: create_store(entities), verify, lambda: None

    def store_clear():
        store, write = create_store(entities)

        def clear():
            write(lambda draft: draft.clear())
            flush()

        def verify(_):
            assert len(store) == 0

        return clear, verify, lambda: None

    def map_create():
        result = []

        def create():
            source, _ = create_signal(values)
            mapped, dispose = create_root(lambda stop: (map_array(source, lambda item, index: item), stop))
            result.append(dispose)
            return mapped()

        def verify(mapped):
            assert mapped == values

        return create, verify, lambda: result.pop()()

    scenarios = {
        "vector_create_10k": lambda: (
            lambda: Vector(iter(values)),
            lambda result: check_vector(result, values),
            lambda: None,
        ),
        "vector_remove_first_10k": lambda: (
            lambda: vector.splice(0, 1, ()),
            lambda result: check_vector(result, values[1:]),
            lambda: None,
        ),
        "vector_truncate_10k_to_1k": lambda: (
            lambda: vector.splice(1000, 9000, ()),
            lambda result: check_vector(result, values[:1000]),
            lambda: None,
        ),
        "store_create_10k": store_create,
        "store_clear_draft_10k": store_clear,
        "store_update_1k_fields": store_updates,
        "map_create_10k": map_create,
        "map_append_1k": lambda: mapping("append"),
        "map_same_10k": lambda: mapping("same"),
        "map_reverse_10k": lambda: mapping("reverse"),
    }
    results = {}
    for name, setup in scenarios.items():
        samples = []
        for iteration in range(warmup + iterations):
            operation, verify, dispose = setup()
            gc.collect()
            started = time.process_time_ns()
            result = operation()
            elapsed = (time.process_time_ns() - started) / 1e6
            verify(result)
            dispose()
            del result, operation, verify, dispose
            gc.collect()
            if iteration >= warmup:
                samples.append(elapsed)
        results[name] = {"median_cpu_ms": statistics.median(samples), "samples_cpu_ms": samples}

    gc.collect()
    tracemalloc.start()
    store, write = create_store(entities)
    gc.collect()
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(store) == 10000

    package = repo / "src" / "wybthon"
    runtime = {
        "wybthon/" + path.relative_to(package).as_posix(): path.read_bytes()
        for path in package.rglob("*.py")
        if path.name not in {"build.py", "dev.py", "mypy_plugin.py"}
    }
    digest = hashlib.sha256()
    for name, data in sorted(runtime.items()):
        digest.update(name.encode())
        digest.update(data)
    return {
        "metadata": {
            "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
            "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repo)),
            "source_sha256": digest.hexdigest(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "iterations": iterations,
            "warmup": warmup,
        },
        "scenarios": results,
        "store_memory": {"retained_bytes": retained, "peak_bytes": peak},
        "bundle": {
            "runtime_source_bytes": sum(map(len, runtime.values())),
            "runtime_zip_bytes": len(_archive(runtime)),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--warmup", type=int, default=2)
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0:
        parser.error("iterations must be positive and warmup nonnegative")
    print(json.dumps(run(args.repo.resolve(), args.iterations, args.warmup), indent=2))


if __name__ == "__main__":
    main()
