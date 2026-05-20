"""Shared session CRUD, hydration, and graph-sync logic (sync and async)."""

from __future__ import annotations

import re
import warnings
from typing import Any, cast

from triplemodel import Store

from sparqlmodel.fields import get_field_metadata, relationship_allows_iri
from sparqlmodel.graph import (
    _predicate_pattern,
    _subject_pattern,
    cascade_subjects_for_removal,
    owned_triples_for_subjects,
    triples_to_graph,
)
from sparqlmodel.hydration import hydrate_one, validate_depth
from sparqlmodel.model import SPARQLModel
from sparqlmodel.rdf_bridge import model_to_graph
from sparqlmodel.session_state import (
    _HYDRATION_MISS,
    SessionState,
    identity_key_for_iri,
)
from sparqlmodel.stores.async_base import AsyncStoreProtocol
from sparqlmodel.stores.base import StoreProtocol
from sparqlmodel.types import IRI

CLOSED_SESSION_MSG = "Cannot use a closed SPARQLSession"
CLOSED_ASYNC_SESSION_MSG = "Cannot use a closed AsyncSPARQLSession"
_PREFIX_DECL_RE = re.compile(r"^\s*PREFIX\b", re.IGNORECASE | re.MULTILINE)


def sparql_has_prefix_declarations(sparql: str) -> bool:
    """Return True if ``sparql`` already declares at least one PREFIX."""
    return _PREFIX_DECL_RE.search(sparql) is not None


def relationships_materialized(model: SPARQLModel) -> bool:
    for name, _field_info, _related in model.get_relationship_fields():
        if isinstance(getattr(model, name, None), SPARQLModel):
            return True
    return False


def _subject_exists_in_store(
    store_graph: Store,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
) -> bool:
    """Return whether ``iri`` still has any triples in ``store_graph``."""
    prefixes = model_cls.get_prefixes()
    subj_ref = _subject_pattern(iri, prefixes)
    return any(store_graph.triples((subj_ref, None, None)))


def depth_satisfied(model: SPARQLModel, depth: int) -> bool:
    """Return whether ``model`` has relationships loaded through ``depth``."""
    if depth <= 0:
        return True
    rel_fields = list(model.get_relationship_fields())
    if depth == 1:
        if not rel_fields:
            return True
        return relationships_materialized(model)
    for name, field_info, _related_cls in rel_fields:
        value = getattr(model, name, None)
        if value is None:
            continue
        if isinstance(value, IRI):
            if relationship_allows_iri(field_info.annotation):
                continue
            return False
        if not isinstance(value, SPARQLModel):
            return False
        if not depth_satisfied(value, depth - 1):
            return False
    return True


def remove_pending_for_subjects(
    state: SessionState,
    subjects: list[tuple[type[SPARQLModel], str | IRI]],
) -> None:
    for model_cls, subj_iri in subjects:
        key = identity_key_for_iri(model_cls, subj_iri)
        state.remove_pending_for(key[0], key[1])


def invalidate_cascade_keys(
    state: SessionState,
    store_graph: Store,
    model: SPARQLModel,
    *,
    for_put: bool,
) -> None:
    subjects = cascade_subjects_for_removal(model, store_graph, for_put=for_put)
    keys = [identity_key_for_iri(cls, iri) for cls, iri in subjects]
    state.expire_keys(keys)


def put_impl(
    store: StoreProtocol,
    state: SessionState,
    model: SPARQLModel,
) -> SPARQLModel:
    model.ensure_id()
    subjects = cascade_subjects_for_removal(model, store.graph, for_put=True)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, store.graph))
    add_g = model_to_graph(model)
    store.update_graph(add=add_g, remove=remove_g if len(remove_g) else None)
    invalidate_cascade_keys(state, store.graph, model, for_put=True)
    state.set_identity(model)
    return model


def check_stale_add(store_graph: Store, model: SPARQLModel) -> None:
    """Warn when ``add`` may duplicate triples for an existing subject."""
    from sparqlmodel.exceptions import StaleTripleWarning

    model.ensure_id()
    subject = model.id
    assert subject is not None
    prefixes = model.get_prefixes()
    subj_ref = _subject_pattern(subject, prefixes)
    if not any(store_graph.triples((subj_ref, None, None))):
        return
    for _name, field_info in model.get_scalar_fields():
        meta = get_field_metadata(field_info)
        if meta is None:  # pragma: no cover — scalars from get_scalar_fields always have metadata
            continue
        pred = _predicate_pattern(meta.predicate, prefixes)
        if any(store_graph.triples((subj_ref, pred, None))):
            warnings.warn(
                f"add() on {type(model).__name__} subject {subject!s} may leave stale "
                f"triples for predicate {meta.predicate!r}; use put() for upsert.",
                StaleTripleWarning,
                stacklevel=2,
            )
            return


def get_impl(
    state: SessionState,
    store: StoreProtocol,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
    *,
    depth: int,
) -> SPARQLModel | None:
    validate_depth(depth)
    id_key = identity_key_for_iri(model_cls, iri)
    hkey = (model_cls, id_key[1], depth)
    hydrated = state.get_hydration(hkey)
    if hydrated is not _HYDRATION_MISS:
        if hydrated is None:
            if not _subject_exists_in_store(store.graph, model_cls, iri):
                return None
        elif _subject_exists_in_store(store.graph, model_cls, iri):
            return cast("SPARQLModel | None", hydrated)
        state.evict_identity_prefix(id_key[0], id_key[1])
        state.invalidate_hydration_for(id_key[0], id_key[1])

    identity = state.get_identity(id_key)
    if identity is not None and depth_satisfied(identity, depth):
        if depth == 0 and relationships_materialized(identity):
            pass
        elif _subject_exists_in_store(store.graph, model_cls, iri):
            state.set_hydration(hkey, identity)
            return identity
        else:
            state.evict_identity_prefix(id_key[0], id_key[1])
            state.invalidate_hydration_for(id_key[0], id_key[1])

    model = hydrate_one(model_cls, iri, store, depth=depth)
    if model is not None:
        state.set_identity(model)
        state.set_hydration(hkey, model)
    else:
        state.evict_identity_prefix(id_key[0], id_key[1])
        state.invalidate_hydration_for(id_key[0], id_key[1])
    return model


def hydrate_bindings_impl(
    state: SessionState,
    store: StoreProtocol,
    model_cls: type[SPARQLModel],
    bindings: list[dict[str, Any]],
    *,
    depth: int,
    get_fn: Any,
) -> list[SPARQLModel]:
    validate_depth(depth)
    results: list[SPARQLModel] = []
    seen: set[str] = set()
    var_name = model_cls.__name__.lower()

    for binding in bindings:
        iri_value = binding.get(var_name) or binding.get(f"?{var_name}")
        if iri_value is None:
            for key, val in binding.items():
                if key.lstrip("?") == var_name:
                    iri_value = val
                    break
        if iri_value is None:
            continue
        iri_str = str(iri_value)
        if iri_str in seen:
            continue
        seen.add(iri_str)
        model = get_fn(model_cls, IRI(iri_str), depth=depth)
        if model is not None:
            results.append(model)
    return results


async def hydrate_bindings_impl_async(
    state: SessionState,
    store: AsyncStoreProtocol,
    model_cls: type[SPARQLModel],
    bindings: list[dict[str, Any]],
    *,
    depth: int,
    get_fn: Any,
) -> list[SPARQLModel]:
    validate_depth(depth)
    results: list[SPARQLModel] = []
    seen: set[str] = set()
    var_name = model_cls.__name__.lower()

    for binding in bindings:
        iri_value = binding.get(var_name) or binding.get(f"?{var_name}")
        if iri_value is None:
            for key, val in binding.items():
                if key.lstrip("?") == var_name:
                    iri_value = val
                    break
        if iri_value is None:
            continue
        iri_str = str(iri_value)
        if iri_str in seen:
            continue
        seen.add(iri_str)
        model = await get_fn(model_cls, IRI(iri_str), depth=depth)
        if model is not None:
            results.append(model)
    return results


def expire_impl(
    state: SessionState,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
) -> None:
    key = identity_key_for_iri(model_cls, iri)
    state.evict_identity_prefix(key[0], key[1])
    state.invalidate_hydration_for(key[0], key[1])
    state.remove_pending_for(key[0], key[1])


async def put_impl_async(
    store: AsyncStoreProtocol,
    state: SessionState,
    model: SPARQLModel,
) -> SPARQLModel:
    model.ensure_id()
    subjects = cascade_subjects_for_removal(model, store.graph, for_put=True)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, store.graph))
    add_g = model_to_graph(model)
    await store.update_graph(add=add_g, remove=remove_g if len(remove_g) else None)
    invalidate_cascade_keys(state, store.graph, model, for_put=True)
    state.set_identity(model)
    return model


class _AsyncStoreReader:
    """Adapter so :func:`hydrate_one` can read from an async store mirror."""

    def __init__(self, store: AsyncStoreProtocol) -> None:
        self.graph = store.graph


async def get_impl_async(
    state: SessionState,
    store: AsyncStoreProtocol,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
    *,
    depth: int,
) -> SPARQLModel | None:
    reader = _AsyncStoreReader(store)
    validate_depth(depth)
    id_key = identity_key_for_iri(model_cls, iri)
    hkey = (model_cls, id_key[1], depth)
    hydrated = state.get_hydration(hkey)
    if hydrated is not _HYDRATION_MISS:
        if hydrated is None:
            if not _subject_exists_in_store(store.graph, model_cls, iri):
                return None
        elif _subject_exists_in_store(store.graph, model_cls, iri):
            return cast("SPARQLModel | None", hydrated)
        state.evict_identity_prefix(id_key[0], id_key[1])
        state.invalidate_hydration_for(id_key[0], id_key[1])

    identity = state.get_identity(id_key)
    if identity is not None and depth_satisfied(identity, depth):
        if depth == 0 and relationships_materialized(identity):
            pass
        elif _subject_exists_in_store(store.graph, model_cls, iri):
            state.set_hydration(hkey, identity)
            return identity
        else:
            state.evict_identity_prefix(id_key[0], id_key[1])
            state.invalidate_hydration_for(id_key[0], id_key[1])

    model = hydrate_one(model_cls, iri, reader, depth=depth)
    if model is not None:
        state.set_identity(model)
        state.set_hydration(hkey, model)
    else:
        state.evict_identity_prefix(id_key[0], id_key[1])
        state.invalidate_hydration_for(id_key[0], id_key[1])
    return model
