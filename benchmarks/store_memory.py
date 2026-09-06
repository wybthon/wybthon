"""Measure native Python allocations retained by an unobserved entity store.

Input data and imports are outside the measurement. This reports tracemalloc
allocations, not browser memory or process RSS. Run each checkout in a fresh
process with the same Python interpreter.
"""

import argparse
import gc
import json
import platform
import subprocess
import sys
import tracemalloc
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--rows", type=int, default=10000)
    args = parser.parse_args()
    if args.rows < 1:
        parser.error("rows must be positive")
    repo = args.repo.resolve()
    if not (repo / "src" / "wybthon" / "__init__.py").is_file():
        parser.error("repo must contain a Wybthon source checkout")
    sys.path.insert(0, str(repo / "src"))
    import wybthon
    from wybthon import create_store

    if not Path(wybthon.__file__).resolve().is_relative_to(repo / "src"):
        parser.error("the imported Wybthon package doesn't belong to the selected checkout")
    data = [{"id": i, "label": f"row {i}"} for i in range(args.rows)]
    gc.collect()
    tracemalloc.start()
    store, write = create_store(data)
    gc.collect()
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(store) == args.rows
    print(
        json.dumps(
            {
                "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
                "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repo)),
                "python": platform.python_version(),
                "rows": args.rows,
                "retained_bytes": retained,
                "peak_bytes": peak,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
