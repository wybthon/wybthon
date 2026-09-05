"""Gate deterministic collection work, independent of CI wall-clock noise."""

import json
import sys
from pathlib import Path


def check(report):
    scenarios = report["benchmarks"]["scenarios"]
    for name in ("select_10k", "swap_10k"):
        counts = scenarios[name]["counts"]
        assert counts.get("rows_created", 0) == 0, (name, counts)
        assert counts.get("list_scanned", 0) == 0, (name, counts)
        assert counts.get("dom_ops", 0) <= 2, (name, counts)
    append = scenarios["append_to_10k"]["counts"]
    assert append["rows_created"] == 1000, append
    assert append.get("list_scanned", 0) == 0, append
    assert append["commits"] == 1, append
    assert append["dom_ops"] <= 8000, append


if __name__ == "__main__":
    check(json.loads(Path(sys.argv[1]).read_text()))
    print("Collection work contracts passed.")
