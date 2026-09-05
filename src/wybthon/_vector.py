"""An immutable, structurally shared vector used by staged store lists.

The 32-way tree copies at most one tuple per level for append, pop, or
indexed replacement. General splices rebuild the sequence; callers retain
explicit splice records so observers and renderers can process only the edit.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any, overload

_BITS = 5
_WIDTH = 1 << _BITS
_MASK = _WIDTH - 1


def _put(tree: tuple[Any, ...], shift: int, index: int, value: Any) -> tuple[Any, ...]:
    slot = (index >> shift) & _MASK
    if shift:
        child = tree[slot] if slot < len(tree) else ()
        value = _put(child, shift - _BITS, index, value)
    if slot == len(tree):
        return (*tree, value)
    return (*tree[:slot], value, *tree[slot + 1 :])


def _trim(tree: tuple[Any, ...], shift: int, index: int) -> tuple[Any, ...]:
    slot = (index >> shift) & _MASK
    if not shift:
        return tree[:slot]
    child = _trim(tree[slot], shift - _BITS, index)
    return (*tree[:slot], child) if child else tree[:slot]


class Vector[T](Sequence[T]):
    __slots__ = ("_tree", "_shift", "_size")

    def __init__(self, values: Iterable[T] = ()) -> None:
        self._tree: tuple[Any, ...] = ()
        self._shift = 0
        self._size = 0
        for value in values:
            self._append_initial(value)

    @classmethod
    def _from(cls, tree: tuple[Any, ...], shift: int, size: int) -> Vector[Any]:
        obj = cls.__new__(cls)
        obj._tree, obj._shift, obj._size = tree, shift, size
        return obj

    def _append_initial(self, value: T) -> None:
        if self._size == 1 << (self._shift + _BITS):
            self._tree = (self._tree,)
            self._shift += _BITS
        self._tree = _put(self._tree, self._shift, self._size, value)
        self._size += 1

    def append(self, value: T) -> Vector[T]:
        result = self._from(self._tree, self._shift, self._size)
        result._append_initial(value)
        return result

    def set(self, index: int, value: T) -> Vector[T]:
        index = self._index(index)
        return self._from(_put(self._tree, self._shift, index, value), self._shift, self._size)

    def pop(self) -> Vector[T]:
        if not self._size:
            raise IndexError("pop from empty list")
        tree = _trim(self._tree, self._shift, self._size - 1)
        shift = self._shift
        while shift and len(tree) == 1:
            tree, shift = tree[0], shift - _BITS
        if not tree:
            shift = 0
        return self._from(tree, shift, self._size - 1)

    def splice(self, start: int, delete: int, values: Iterable[T]) -> Vector[T]:
        added = tuple(values)
        if start == self._size and not delete:
            result = self
            for value in added:
                result = result.append(value)
            return result
        if start + delete == self._size and not added:
            result = self
            for _ in range(delete):
                result = result.pop()
            return result
        return Vector((*self[:start], *added, *self[start + delete :]))

    def _index(self, index: int) -> int:
        if index < 0:
            index += self._size
        if not 0 <= index < self._size:
            raise IndexError("list index out of range")
        return index

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> list[T]: ...

    def __getitem__(self, index: int | slice) -> T | list[T]:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self._size))]
        index = self._index(index)
        node = self._tree
        for shift in range(self._shift, 0, -_BITS):
            node = node[(index >> shift) & _MASK]
        return node[index & _MASK]

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[T]:
        def walk(tree: tuple[Any, ...], shift: int) -> Iterator[T]:
            if not shift:
                yield from tree
            else:
                for child in tree:
                    yield from walk(child, shift - _BITS)

        return walk(self._tree, self._shift)
