### Performance

Tips:

- Prefer signals at the edges; derive with `computed` to minimize re-renders
- Use `key` on lists to help the diffing algorithm
- Batch updates with `batch()`

Keyed lists allow the reconciler to reorder elements in-place with minimal DOM operations. Prefer stable keys (IDs) over indices.

Micro-benchmarking

- A small test is included that measures reversing a list of 200 keyed items; it should complete well under a second in the stubbed test environment. Use it as a smoke check to catch regressions in the keyed children algorithm.
