# Runtime overhaul evaluation

These are local observations from September 5, 2026, on an Intel macOS machine using Chromium and Pyodide 314.0.6. Runs were serial, with one warmup and three measured samples. They aren't portable performance guarantees or cross-framework rankings. The baseline is commit `72bc523`.

## Comparable signal-array operations

The same exploratory instrumentation times direct Python operations, including their synchronous flush, JSON serialization, and kernel application. It excludes subsequent layout and paint. This is separate from the repaired delegated-event benchmark below.

| Operation | Baseline, ms | Overhaul, ms |
| --- | ---: | ---: |
| Create 1,000 | 106.7 | 109.2 |
| Create 10,000 | 889.5 | 1,019.8 |
| Update every tenth of 10,000 | 10.4 | 12.2 |
| Toggle selection among 10,000 | 3.0 | 0.4 |
| Swap two of 10,000 | 59.4 | 42.8 |
| Append 1,000 to 10,000 | 146.2 | 172.2 |

Selection and generic swaps improved. Large initial mounting and some updates remain slower in this run; this overhaul doesn't claim a universal speedup. Mounting 10,000 rows still spends most of its synchronous time in Python. Text-only hole anchors reduce initial commands from 80,010 to 70,000 and the measured live node handles from roughly 110,000 to 100,000. Toolbar handles differ between the harness versions, so the registry totals aren't exact one-for-one baselines.

## Transactional store paths

The repaired browser harness drives ordinary delegated events, profiles work, validates changed DOM, and records input-to-frame time separately. Store mode is a new workload and shouldn't be compared directly against the signal-array baseline above.

| Store operation on 10,000 rows | Synchronous commit, ms | Deterministic work |
| --- | ---: | --- |
| Select | 0.5 | Two DOM commands, no rows created, no full-list scan |
| Swap | 0.8 | Two range moves, no rows created, no full-list scan |
| Append 1,000 | 156.9 | 1,000 rows created, one commit, no full-list scan |
| Remove first row | 42.4 | Remaining index accessors update |

The command gate in `benchmarks/check_work.py` verifies selection, swap, and append counts. The unit suite also checks a one-row append and Repeat growth against a 1,000-row baseline. The browser suite checks 300 mount/dispose cycles for node/listener retention and a maximum of 256 template prototypes.

Virtualization bounds mounted work for large fixed-height lists. Arbitrary replacement lists still require matching, and general sequence splices can rebuild their persistent sequence.

See [the recorded samples and counters](runtime-overhaul.json) and [benchmark instructions](../README.md). Startup has separate loader timings and production browser tests; it isn't represented by these warmed updates.
