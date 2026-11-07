# Stores

A store wraps a dataclass instance, a dict, or a list, and `create_store` types it as that same data. A dataclass store ([`StoreObject`][wybthon.StoreObject]) reads its fields as tracked attributes; dict and list stores ([`Store`][wybthon.Store] and [`StoreList`][wybthon.StoreList]) implement Python's read-only `Mapping` and `Sequence` protocols, and their synchronous scoped drafts implement the mutable counterparts. See the [store guide](../concepts/stores.md) for versions, identity, snapshots, shallow stores, projections, and optimistic rebasing.

::: wybthon.store
