"""Shared session CRUD, hydration, and graph-sync logic (sync and async)."""

from __future__ import annotations

import re
import warnings
from typing import Any, cast

from triplemodel import Store

from sparqlmodel.exceptions import ConfigurationError
from sparqlmodel.fields import get_field_metadata, relationship_allows_iri
from sparqlmodel.graph import (
    _predicate_pattern,
    _subject_pattern,
    cascade_subjects_for_removal,
    owned_triples_for_subjects,
    subject_has_rdf_type,
    triples_to_graph,
)
from sparqlmodel.hydration import hydrate_one, validate_depth
from sparqlmodel.model import SPARQLModel
from sparqlmodel.rdf_bridge import model_to_graph
from sparqlmodel.session_state import (
    _HYDRATION_MISS,
    SessionState,
    identity_key,
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
    from sparqlmodel.fields import iter_relationship_values

    for name, _field_info, _related in model.get_relationship_fields():
        value = getattr(model, name, None)
        for item in iter_relationship_values(value):
            if isinstance(item, SPARQLModel):
                return True
    return False


def _should_pull_subject_for_read(
    store: StoreProtocol | AsyncStoreProtocol,
    store_graph: Store,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
) -> bool:
    """Return whether to CONSTRUCT-pull ``iri`` before hydrating from the mirror."""
    if getattr(store, "pull_subjects_into_mirror", None) is None:
        return False
    if getattr(store, "mirror_mode", "writer") == "remote_authoritative":
        return True
    return not subject_has_rdf_type(model_cls, iri, store_graph)


def _evict_read_cache_for_pull(
    state: SessionState,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
    store: StoreProtocol | AsyncStoreProtocol,
) -> None:
    if getattr(store, "mirror_mode", "writer") != "remote_authoritative":
        return
    id_key = identity_key_for_iri(model_cls, iri)
    state.evict_identity_prefix(model_cls, id_key[1])
    state.invalidate_hydration_for(model_cls, id_key[1])


def _pull_subject_for_read_sync(
    state: SessionState,
    store: StoreProtocol,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
) -> None:
    if not _should_pull_subject_for_read(store, store.graph, model_cls, iri):
        return
    _evict_read_cache_for_pull(state, model_cls, iri, store)
    pull = getattr(store, "pull_subjects_into_mirror", None)
    if pull is not None:
        pull([iri])


async def _pull_subject_for_read_async(
    state: SessionState,
    store: AsyncStoreProtocol,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
) -> None:
    if not _should_pull_subject_for_read(store, store.graph, model_cls, iri):
        return
    _evict_read_cache_for_pull(state, model_cls, iri, store)
    pull = getattr(store, "pull_subjects_into_mirror", None)
    if pull is not None:
        result = pull([iri])
        if hasattr(result, "__await__"):
            await result


def _subject_loadable_in_store(
    store_graph: Store,
    model_cls: type[SPARQLModel],
    iri: str | IRI,
) -> bool:
    """Return whether ``iri`` has the expected ``rdf:type`` in ``store_graph``."""
    return subject_has_rdf_type(model_cls, iri, store_graph)


def depth_satisfied(model: SPARQLModel, depth: int) -> bool:
    """Return whether ``model`` has relationships loaded through ``depth``."""
    if depth <= 0:
        return True
    rel_fields = list(model.get_relationship_fields())
    if not rel_fields:
        return True
    saw_relationship = False
    from sparqlmodel.fields import iter_relationship_values

    for name, field_info, _related_cls in rel_fields:
        value = getattr(model, name, None)
        if value is None:
            continue
        items = iter_relationship_values(value)
        if not items:
            continue
        saw_relationship = True
        for item in items:
            if isinstance(item, IRI):
                if relationship_allows_iri(field_info.annotation):
                    continue
                return False
            if not isinstance(item, SPARQLModel):
                return False
            if not depth_satisfied(item, depth - 1):
                return False
    return saw_relationship


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
    invalidate_subjects(state, subjects)


def invalidate_subjects(
    state: SessionState,
    subjects: list[tuple[type[SPARQLModel], str | IRI]],
) -> None:
    """Expire identity and hydration cache entries for cascade subjects."""
    keys = [identity_key_for_iri(cls, iri) for cls, iri in subjects]
    state.expire_keys(keys)


def put_impl(
    store: StoreProtocol,
    state: SessionState,
    model: SPARQLModel,
) -> SPARQLModel:
    model.ensure_id()
    subjects = cascade_subjects_for_removal(model, store.graph, for_put=True)
    remove_pending_for_subjects(state, subjects)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, store.graph))
    add_g = model_to_graph(model)
    store.update_graph(add=add_g, remove=remove_g if len(remove_g) else None)
    invalidate_subjects(state, subjects)
    state.set_identity(model)
    _register_embedded_identities(state, model)
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
    _pull_subject_for_read_sync(state, store, model_cls, iri)
    hydrated = state.get_hydration(hkey)
    if hydrated is not _HYDRATION_MISS:
        if hydrated is None:
            if not _subject_loadable_in_store(store.graph, model_cls, iri):
                return None
        elif _subject_loadable_in_store(store.graph, model_cls, iri):
            cached = cast("SPARQLModel", hydrated)
            if depth_satisfied(cached, depth):
                return cached
            state.invalidate_hydration_for(id_key[0], id_key[1])
        else:
            state.evict_identity_prefix(id_key[0], id_key[1])
            state.invalidate_hydration_for(id_key[0], id_key[1])

    identity = state.get_identity(id_key)
    if identity is not None and depth_satisfied(identity, depth):
        if depth == 0 and relationships_materialized(identity):
            pass
        elif _subject_loadable_in_store(store.graph, model_cls, iri):
            state.set_hydration(hkey, identity)
            return identity
        else:
            state.evict_identity_prefix(id_key[0], id_key[1])
            state.invalidate_hydration_for(id_key[0], id_key[1])

    loaded = hydrate_one(model_cls, iri, store, depth=depth)
    if loaded is not None:
        identity = state.get_identity(id_key)
        if identity is not None:
            identity = _reconcile_identity_from_loaded(state, store.graph, identity, loaded)
            state.set_hydration(hkey, identity)
            return identity
        state.set_identity(loaded)
        _register_embedded_identities(state, loaded)
        state.set_hydration(hkey, loaded)
        return loaded
    state.evict_identity_prefix(id_key[0], id_key[1])
    state.invalidate_hydration_for(id_key[0], id_key[1])
    return None


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


def _copy_validated_state(
    target: SPARQLModel,
    source: SPARQLModel,
    *,
    exclude_unset: bool = False,
) -> SPARQLModel:
    """Copy validated field values from ``source`` onto ``target`` (same object id)."""
    model_cls = type(target)
    validated = model_cls.model_validate(source.model_dump(exclude_unset=exclude_unset))
    for name in model_cls.model_fields:
        if exclude_unset and name not in source.model_fields_set:
            continue
        setattr(target, name, getattr(validated, name))
    return target


def _register_embedded_identities(state: SessionState, model: SPARQLModel) -> None:
    """Register composed ``SPARQLModel`` instances from relationship fields."""
    for name, _field_info, _related in model.get_relationship_fields():
        value = getattr(model, name, None)
        if isinstance(value, SPARQLModel):
            state.set_identity(value)
            _register_embedded_identities(state, value)


def _reconcile_identity_from_loaded(
    state: SessionState,
    store_graph: Store,
    identity: SPARQLModel,
    loaded: SPARQLModel,
    *,
    exclude_unset: bool = False,
) -> SPARQLModel:
    """Expire cascade identity entries, copy ``loaded`` onto ``identity``, re-register root."""
    subjects = cascade_subjects_for_removal(loaded, store_graph, for_put=True)
    invalidate_subjects(state, subjects)
    _copy_validated_state(identity, loaded, exclude_unset=exclude_unset)
    state.set_identity(identity)
    _register_embedded_identities(state, identity)
    return identity


def expunge_impl(state: SessionState, model: SPARQLModel) -> None:
    """Remove ``model`` from the identity map and hydration cache."""
    if model.id is not None:
        cls, iri_key = identity_key_for_iri(type(model), model.id)
        state.remove_pending_for(cls, iri_key)
    state.expire_model(model)


def expunge_all_impl(state: SessionState) -> None:
    """Clear identity map and hydration cache (pending queue unchanged)."""
    state.expunge_all()


def _apply_refresh_loaded(
    state: SessionState,
    store_graph: Store,
    model: SPARQLModel,
    loaded: SPARQLModel,
    *,
    depth: int,
) -> SPARQLModel:
    model_cls = type(model)
    id_key = identity_key(model)
    identity = state.get_identity(id_key)
    if identity is not None:
        identity = _reconcile_identity_from_loaded(state, store_graph, identity, loaded)
        state.invalidate_hydration_for(model_cls, id_key[1])
        hkey = (model_cls, id_key[1], depth)
        state.set_hydration(hkey, identity)
        return identity
    state.set_identity(loaded)
    _register_embedded_identities(state, loaded)
    state.set_hydration((model_cls, id_key[1], depth), loaded)
    return loaded


def refresh_impl(
    state: SessionState,
    store: StoreProtocol,
    model: SPARQLModel,
    *,
    depth: int,
) -> SPARQLModel:
    """Reload ``model`` from the store graph at ``depth``."""
    validate_depth(depth)
    model.ensure_id()
    model_cls = type(model)
    assert model.id is not None
    _pull_subject_for_read_sync(state, store, model_cls, model.id)
    loaded = hydrate_one(model_cls, model.id, store, depth=depth)
    if loaded is None:
        raise ConfigurationError(
            f"Cannot refresh {model_cls.__name__} {model.id!s}: subject not in store"
        )
    return _apply_refresh_loaded(state, store.graph, model, loaded, depth=depth)


async def refresh_impl_async(
    state: SessionState,
    store: AsyncStoreProtocol,
    model: SPARQLModel,
    *,
    depth: int,
) -> SPARQLModel:
    """Reload ``model`` from the async store mirror at ``depth``."""
    validate_depth(depth)
    model.ensure_id()
    model_cls = type(model)
    assert model.id is not None
    reader = _AsyncStoreReader(store)
    await _pull_subject_for_read_async(state, store, model_cls, model.id)
    loaded = hydrate_one(model_cls, model.id, reader, depth=depth)
    if loaded is None:
        raise ConfigurationError(
            f"Cannot refresh {model_cls.__name__} {model.id!s}: subject not in store"
        )
    return _apply_refresh_loaded(state, store.graph, model, loaded, depth=depth)


def merge_impl(state: SessionState, model: SPARQLModel) -> SPARQLModel:
    """Attach or reconcile ``model`` with the session identity map (no store write)."""
    model.ensure_id()
    id_key = identity_key(model)
    model_cls = type(model)
    state.remove_pending_for(model_cls, id_key[1])
    identity = state.get_identity(id_key)
    if identity is not None:
        _copy_validated_state(identity, model, exclude_unset=True)
        state.invalidate_hydration_for(model_cls, id_key[1])
        _register_embedded_identities(state, identity)
        return identity
    state.set_identity(model)
    _register_embedded_identities(state, model)
    return model


async def put_impl_async(
    store: AsyncStoreProtocol,
    state: SessionState,
    model: SPARQLModel,
) -> SPARQLModel:
    model.ensure_id()
    subjects = cascade_subjects_for_removal(model, store.graph, for_put=True)
    remove_pending_for_subjects(state, subjects)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, store.graph))
    add_g = model_to_graph(model)
    await store.update_graph(add=add_g, remove=remove_g if len(remove_g) else None)
    invalidate_subjects(state, subjects)
    state.set_identity(model)
    _register_embedded_identities(state, model)
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
    await _pull_subject_for_read_async(state, store, model_cls, iri)
    hydrated = state.get_hydration(hkey)
    if hydrated is not _HYDRATION_MISS:
        if hydrated is None:
            if not _subject_loadable_in_store(store.graph, model_cls, iri):
                return None
        elif _subject_loadable_in_store(store.graph, model_cls, iri):
            cached = cast("SPARQLModel", hydrated)
            if depth_satisfied(cached, depth):
                return cached
            state.invalidate_hydration_for(id_key[0], id_key[1])
        else:
            state.evict_identity_prefix(id_key[0], id_key[1])
            state.invalidate_hydration_for(id_key[0], id_key[1])

    identity = state.get_identity(id_key)
    if identity is not None and depth_satisfied(identity, depth):
        if depth == 0 and relationships_materialized(identity):
            pass
        elif _subject_loadable_in_store(store.graph, model_cls, iri):
            state.set_hydration(hkey, identity)
            return identity
        else:
            state.evict_identity_prefix(id_key[0], id_key[1])
            state.invalidate_hydration_for(id_key[0], id_key[1])

    loaded = hydrate_one(model_cls, iri, reader, depth=depth)
    if loaded is not None:
        identity = state.get_identity(id_key)
        if identity is not None:
            identity = _reconcile_identity_from_loaded(state, store.graph, identity, loaded)
            state.set_hydration(hkey, identity)
            return identity
        state.set_identity(loaded)
        _register_embedded_identities(state, loaded)
        state.set_hydration(hkey, loaded)
        return loaded
    state.evict_identity_prefix(id_key[0], id_key[1])
    state.invalidate_hydration_for(id_key[0], id_key[1])
    return None
