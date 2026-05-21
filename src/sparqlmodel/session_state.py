"""Session-level identity map, hydration cache, and pending writes."""

from __future__ import annotations

from sparqlmodel.graph import _expanded_iri_key
from sparqlmodel.model import SPARQLModel
from sparqlmodel.types import IRI

IdentityKey = tuple[type[SPARQLModel], str]
HydrationKey = tuple[type[SPARQLModel], str, int]


def identity_key(model: SPARQLModel) -> IdentityKey:
    model.ensure_id()
    prefixes = model.get_prefixes()
    iri = model.id
    assert iri is not None
    key = str(iri)
    if not key.startswith("_:"):
        key = _expanded_iri_key(iri, prefixes)
    return (type(model), key)


def identity_key_for_iri(model_cls: type[SPARQLModel], iri: str | IRI) -> IdentityKey:
    prefixes = model_cls.get_prefixes()
    raw = str(iri)
    key = raw if raw.startswith("_:") else _expanded_iri_key(iri, prefixes)
    return (model_cls, key)


class SessionState:
    """Identity map, hydration cache, and pending ``put`` queue for a session."""

    def __init__(self) -> None:
        self._identity: dict[IdentityKey, SPARQLModel] = {}
        self._hydration: dict[HydrationKey, SPARQLModel | None] = {}
        self._pending: list[SPARQLModel] = []

    def get_identity(self, key: IdentityKey) -> SPARQLModel | None:
        return self._identity.get(key)

    def set_identity(self, model: SPARQLModel) -> None:
        key = identity_key(model)
        self._identity[key] = model
        self.invalidate_hydration_for_iri(key[1])

    def pop_identity(self, key: IdentityKey) -> None:
        self._identity.pop(key, None)

    def evict_identity_prefix(self, model_cls: type[SPARQLModel], iri_key: str) -> None:
        self._identity.pop((model_cls, iri_key), None)

    def get_hydration(self, key: HydrationKey) -> SPARQLModel | None | _HydrationMiss:
        if key not in self._hydration:
            return _HYDRATION_MISS
        return self._hydration[key]

    def set_hydration(self, key: HydrationKey, value: SPARQLModel | None) -> None:
        self._hydration[key] = value

    def invalidate_hydration_for(self, model_cls: type[SPARQLModel], iri_key: str) -> None:
        to_drop = [k for k in self._hydration if k[0] is model_cls and k[1] == iri_key]
        for k in to_drop:
            del self._hydration[k]

    def invalidate_hydration_for_iri(self, iri_key: str) -> None:
        """Drop hydration cache entries for all model classes at ``iri_key``."""
        to_drop = [k for k in self._hydration if k[1] == iri_key]
        for k in to_drop:
            del self._hydration[k]

    def invalidate_all_hydration(self) -> None:
        self._hydration.clear()

    def add_pending(self, model: SPARQLModel) -> None:
        key = identity_key(model)
        self._pending = [m for m in self._pending if identity_key(m) != key]
        self._pending.append(model)

    @property
    def pending(self) -> list[SPARQLModel]:
        return self._pending

    def clear_pending(self) -> None:
        self._pending.clear()

    def remove_pending_for(self, model_cls: type[SPARQLModel], iri_key: str) -> None:
        """Drop queued ``put(..., flush=False)`` writes for ``(model_cls, iri_key)``."""
        target = (model_cls, iri_key)
        self._pending = [
            m for m in self._pending if identity_key_for_iri(type(m), m.ensure_id()) != target
        ]

    def expire_model(self, model: SPARQLModel) -> None:
        key = identity_key(model)
        self.pop_identity(key)
        self.invalidate_hydration_for_iri(key[1])

    def expire_keys(self, keys: list[IdentityKey]) -> None:
        for model_cls, iri_key in keys:
            self.evict_identity_prefix(model_cls, iri_key)
            self.invalidate_hydration_for_iri(iri_key)

    def expunge_all(self) -> None:
        """Clear identity map and hydration cache (pending queue unchanged)."""
        self._identity.clear()
        self._hydration.clear()


class _HydrationMiss:
    pass


_HYDRATION_MISS = _HydrationMiss()
