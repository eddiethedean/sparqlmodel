"""Session identity map, cache, and flush."""

from __future__ import annotations

import pytest

from sparqlmodel import IRI, SPARQLSession
from sparqlmodel.exceptions import ConfigurationError, StaleTripleWarning
from sparqlmodel.graph import (
    cascade_subjects_for_removal,
    owned_triples_for_subjects,
    triples_to_graph,
)
from sparqlmodel.rdf_bridge import model_to_graph
from tests.models import Organization, Person


def test_identity_map_same_instance_on_get(session: SPARQLSession) -> None:
    from sparqlmodel import IRI

    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    session.put(plain)
    assert session.get(Person, plain.id) is plain
    a = session.get(Person, plain.id)
    b = session.get(Person, plain.id)
    assert a is not None
    assert a is b


def test_put_flush_false_get_before_flush_not_pending_instance(
    session: SPARQLSession,
) -> None:
    from sparqlmodel import IRI

    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    session.autoflush = False
    session.put(plain, flush=False)
    found = session.get(Person, plain.id)
    assert found is None or found is not plain
    session.flush()
    assert session.get(Person, plain.id) is plain


def test_put_flush_false_evicts_stale_identity(session: SPARQLSession) -> None:
    from sparqlmodel import IRI

    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    session.put(plain)
    plain.name = "Updated"
    session.autoflush = False
    session.put(plain, flush=False)
    found = session.get(Person, plain.id)
    assert found is None or found.name != "Updated"
    session.flush()
    loaded = session.get(Person, plain.id)
    assert loaded is not None
    assert loaded.name == "Updated"


def test_expire_drops_pending_put(session: SPARQLSession, odos: Person) -> None:
    session.autoflush = False
    session.put(odos, flush=False)
    session.expire(Person, odos.id)
    session.flush()
    assert session.get(Person, odos.id) is None


def test_exit_raises_flush_error_when_close_on_exit_false(
    session: SPARQLSession, odos: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sparqlmodel import session_core

    session.close_on_exit = False
    other = Person(id=IRI("urn:person:other"), name="Other")
    session.autoflush = False
    session.put(odos, flush=False)
    session.put(other, flush=False)
    calls = {"n": 0}
    orig = session_core.put_impl

    def failing_put(store: object, state: object, model: Person) -> Person:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("put failed")
        return orig(store, state, model)  # type: ignore[arg-type]

    monkeypatch.setattr(session_core, "put_impl", failing_put)
    with pytest.raises(RuntimeError, match="put failed"), session:
        pass
    assert not session._closed


def test_exit_preserves_flush_error_over_close_pending(
    session: SPARQLSession, odos: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sparqlmodel import session_core

    other = Person(id=IRI("urn:person:other"), name="Other")
    session.autoflush = False
    session.put(odos, flush=False)
    session.put(other, flush=False)
    calls = {"n": 0}
    orig = session_core.put_impl

    def failing_put(store: object, state: object, model: Person) -> Person:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("put failed")
        return orig(store, state, model)  # type: ignore[arg-type]

    monkeypatch.setattr(session_core, "put_impl", failing_put)
    with pytest.raises(RuntimeError, match="put failed") as exc_info, session:
        pass
    assert "pending" not in str(exc_info.value).lower()


def test_flush_requeues_on_failure(
    session: SPARQLSession, odos: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sparqlmodel import IRI

    other = Person(id=IRI("urn:person:other"), name="Other")
    session.autoflush = False
    session.put(odos, flush=False)
    session.put(other, flush=False)
    calls = {"n": 0}

    from sparqlmodel import session_core

    orig = session_core.put_impl

    def failing_put(store: object, state: object, model: Person) -> Person:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("put failed")
        return orig(store, state, model)  # type: ignore[arg-type]

    monkeypatch.setattr(session_core, "put_impl", failing_put)
    with pytest.raises(RuntimeError, match="put failed"):
        session.flush()
    assert len(session._state.pending) == 1
    assert session._state.pending[0] is other


def test_put_flush_false_queues_until_flush(session: SPARQLSession, odos: Person) -> None:
    session.autoflush = False
    session.put(odos, flush=False)
    assert len(session.graph) == 0
    session.flush()
    assert len(session.graph) >= 2


def test_rollback_pending_discards_queue(session: SPARQLSession, odos: Person) -> None:
    session.autoflush = False
    session.put(odos, flush=False)
    session.rollback_pending()
    session.flush()
    assert len(session.graph) == 0


def test_autoflush_before_query(session: SPARQLSession, odos: Person) -> None:
    session.autoflush = True
    session.put(odos, flush=False)
    found = session.query(Person).where(Person.name == "Odos").first()
    assert found is not None
    assert found.name == "Odos"


def test_autoflush_before_hydrate_bindings(session: SPARQLSession, odos: Person) -> None:
    session.autoflush = True
    session.put(odos, flush=False)
    bindings = [{"person": str(odos.id)}]
    results = session.hydrate_bindings(Person, bindings)
    assert len(results) == 1
    assert results[0].name == "Odos"


def test_expire_evicts_cache(session: SPARQLSession, odos: Person) -> None:
    session.put(odos)
    first = session.get(Person, odos.id)
    session.expire(Person, odos.id)
    second = session.get(Person, odos.id)
    assert first is not None
    assert second is not None
    assert first is not second


def test_hydrate_bindings_alt_binding_keys(session: SPARQLSession, odos: Person) -> None:
    session.put(odos)
    bindings = [{"?person": str(odos.id)}]
    results = session.hydrate_bindings(Person, bindings, depth=0)
    assert len(results) == 1
    bindings2 = [{"other": "x"}]
    assert session.hydrate_bindings(Person, bindings2) == []
    results3 = session.hydrate_bindings(Person, [{"person": str(odos.id)}])
    assert len(results3) == 1
    results3b = session.hydrate_bindings(
        Person,
        [{"person": str(odos.id)}, {"person": str(odos.id)}],
    )
    assert len(results3b) == 1
    results4 = session.hydrate_bindings(
        Person,
        [{"??person": str(odos.id)}],
    )
    assert len(results4) == 1


def test_stale_add_skips_field_without_metadata(
    session: SPARQLSession, odos: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sparqlmodel import fields as fields_mod

    session.put(odos)
    calls = {"n": 0}

    orig = fields_mod.get_field_metadata

    def fake_meta(field_info: object) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return orig(field_info)

    monkeypatch.setattr(fields_mod, "get_field_metadata", fake_meta)
    with pytest.warns(StaleTripleWarning, match="stale triples"):
        session.add(odos)


def test_session_state_unit() -> None:
    from sparqlmodel.session_state import SessionState, identity_key
    from tests.models import Person

    state = SessionState()
    assert state.get_identity(("x", "y")) is None  # type: ignore[arg-type]
    p = Person(id=IRI("urn:p:1"), name="A")
    state.set_identity(p)
    assert state.get_identity(identity_key(p)) is p
    state.invalidate_all_hydration()
    from sparqlmodel.session_state import _HYDRATION_MISS

    state.set_hydration((Person, "urn:p:1", 0), p)
    state.invalidate_hydration_for_iri("urn:p:1")
    assert state.get_hydration((Person, "urn:p:1", 0)) is _HYDRATION_MISS
    state.add_pending(p)
    assert state.pending == [p]
    state.clear_pending()
    state.expunge_all()
    assert state.get_identity(identity_key(p)) is None


def test_merge_returns_cached_identity(session: SPARQLSession) -> None:
    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    session.put(plain)
    session.expunge(plain)
    detached = Person(id=plain.id, name="Detached")
    merged = session.merge(detached)
    again = session.get(Person, plain.id)
    assert merged is again
    assert merged.name == "Detached"


def test_merge_updates_cached_instance(session: SPARQLSession) -> None:
    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    session.put(plain)
    cached = session.get(Person, plain.id)
    assert cached is not None
    detached = Person(id=plain.id, name="MergedName")
    result = session.merge(detached)
    assert result is cached
    assert cached.name == "MergedName"


def test_merge_preserves_unset_relationships(session: SPARQLSession, odos: Person) -> None:
    session.put(odos)
    cached = session.get(Person, odos.id, depth=1)
    assert cached is not None
    assert cached.works_for is not None
    session.merge(Person(id=odos.id, name="MergedName"))
    assert cached.name == "MergedName"
    assert cached.works_for is not None
    assert cached.works_for.name == "Acme Corp"


def test_get_none_when_mirror_lacks_person_rdf_type(session: SPARQLSession) -> None:
    from pyoxigraph import Literal

    from sparqlmodel.graph import _subject_pattern

    iri = IRI("urn:p:no-person-type")
    subj = _subject_pattern(iri, Person.get_prefixes())
    session.store.graph.add((subj, "https://schema.org/name", Literal("Orphan")))
    assert session.get(Person, iri) is None


def test_merge_registers_embedded_organization_identity(session: SPARQLSession) -> None:
    from sparqlmodel.session_state import identity_key_for_iri

    org = Organization(id=IRI("urn:org:acme"), name="Acme")
    detached = Person(id=IRI("urn:person:1"), name="Pat", works_for=org)
    session.merge(detached)
    org_key = identity_key_for_iri(Organization, org.id)
    assert session._state.get_identity(org_key) is detached.works_for


def test_add_drops_pending_put_for_same_subject(session: SPARQLSession) -> None:
    iri = IRI("urn:person:pending-add")
    session.autoflush = False
    session.put(Person(id=iri, name="Pending"), flush=False)
    session.add(Person(id=iri, name="Added"))
    session.flush()
    loaded = session.get(Person, iri)
    assert loaded is not None
    assert loaded.name == "Added"


def test_merge_drops_pending_put_for_same_subject(session: SPARQLSession) -> None:
    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    session.put(plain)
    pending = Person(id=plain.id, name="PendingName")
    session.autoflush = False
    session.put(pending, flush=False)
    session.merge(Person(id=plain.id, name="MergedName"))
    session.flush()
    loaded = session.get(Person, plain.id)
    assert loaded is not None
    assert loaded.name == "MergedName"


def test_remove_pending_for_does_not_assign_id() -> None:
    from sparqlmodel.session_state import SessionState

    state = SessionState()
    pending = Person(name="NoIdYet")
    assert pending.id is None
    state._pending.append(pending)
    state.remove_pending_for(Person, "urn:person:missing")
    assert pending.id is None
    assert state.pending == [pending]


def test_remove_pending_for_drops_matching_entry() -> None:
    from sparqlmodel.session_state import SessionState, identity_key_for_iri

    state = SessionState()
    pending = Person(id=IRI("urn:person:pending"), name="Pending")
    state._pending.append(pending)
    _, iri_key = identity_key_for_iri(Person, pending.id)
    state.remove_pending_for(Person, iri_key)
    assert state.pending == []


def test_get_same_depth_reloads_when_cached_hydration_too_shallow(
    session: SPARQLSession, odos: Person
) -> None:
    from sparqlmodel.session_state import identity_key_for_iri

    session.put(odos)
    shallow = session.get(Person, odos.id, depth=0)
    assert shallow is not None
    assert shallow.works_for is None
    _, iri_key = identity_key_for_iri(Person, odos.id)
    session._state.set_hydration((Person, iri_key, 1), shallow)
    deep = session.get(Person, odos.id, depth=1)
    assert deep is not None
    assert deep.works_for is not None


def test_get_deeper_depth_invalidates_shallow_hydration(
    session: SPARQLSession, odos: Person, acme: Organization
) -> None:
    from tests.models import Location

    loc = Location(id=IRI("urn:loc:hq"), name="HQ")
    org = Organization(id=acme.id, name="Acme Corp", located_in=loc)
    person = Person(id=odos.id, name="Odos", works_for=org)
    session.put(person)
    shallow = session.get(Person, odos.id, depth=1)
    assert shallow is not None
    deep = session.get(Person, odos.id, depth=2)
    assert deep is not None
    assert deep.works_for is not None
    assert deep.works_for.located_in is not None


def test_merge_does_not_modify_store(session: SPARQLSession, odos: Person) -> None:
    from pyoxigraph import Literal

    session.put(odos)
    cached = session.get(Person, odos.id)
    assert cached is not None
    subj = str(odos.id.expand(odos.get_prefixes()))
    pred = "https://schema.org/name"

    def name_in_graph() -> str | None:
        for _s, _p, o in session.graph.triples((subj, pred, None)):
            if isinstance(o, Literal):
                return o.value
        return None

    assert name_in_graph() == "Odos"
    session.merge(Person(id=odos.id, name="MergedName"))
    assert cached.name == "MergedName"
    assert name_in_graph() == "Odos"


def test_merge_invalidates_hydration_cache(
    session: SPARQLSession, odos: Person, acme: Organization
) -> None:
    session.put(odos)
    deep = session.get(Person, odos.id, depth=2)
    assert deep is not None
    assert deep.works_for is not None
    assert deep.works_for.name == "Acme Corp"
    session.merge(Person(id=odos.id, name="Merged"))
    renamed = Organization(id=acme.id, name="Renamed Corp")
    updated = Person(id=odos.id, name="Merged", works_for=renamed)
    subjects = cascade_subjects_for_removal(updated, session.graph, for_put=True)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, session.graph))
    add_g = model_to_graph(updated)
    session.store.update_graph(add=add_g, remove=remove_g if len(remove_g) else None)
    again = session.get(Person, odos.id, depth=2)
    assert again is deep
    assert again.works_for is not None
    assert again.works_for.name == "Renamed Corp"


def test_refresh_updates_identity_in_place(session: SPARQLSession) -> None:
    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    session.put(plain)
    cached = session.get(Person, plain.id)
    assert cached is plain
    updated = Person(id=plain.id, name="Refreshed")
    subjects = cascade_subjects_for_removal(updated, session.graph, for_put=True)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, session.graph))
    add_g = model_to_graph(updated)
    session.store.update_graph(add=add_g, remove=remove_g if len(remove_g) else None)
    assert cached.name == "Plain"
    refreshed = session.refresh(cached)
    assert refreshed is cached
    assert cached.name == "Refreshed"


def test_refresh_attaches_when_not_in_identity_map(session: SPARQLSession) -> None:
    plain = Person(id=IRI("urn:person:plain"), name="Plain")
    session.put(plain)
    detached = Person(id=plain.id, name="Plain")
    session.expunge(detached)
    loaded = session.refresh(detached)
    assert loaded is not detached
    assert loaded.name == "Plain"
    assert session.get(Person, plain.id) is loaded


def test_refresh_missing_subject_raises(session: SPARQLSession) -> None:
    orphan = Person(id=IRI("urn:person:orphan"), name="Nobody")
    with pytest.raises(ConfigurationError, match="not in store"):
        session.refresh(orphan)


def test_refresh_shallow_then_get_deep_reloads_relationships(
    session: SPARQLSession, odos: Person
) -> None:
    session.put(odos)
    deep = session.get(Person, odos.id, depth=2)
    assert deep.works_for is not None
    assert deep.works_for.name == "Acme Corp"
    session.refresh(deep, depth=0)
    assert deep.works_for is None
    again = session.get(Person, odos.id, depth=2)
    assert again is deep
    assert again.works_for is not None
    assert again.works_for.name == "Acme Corp"


def test_expunge_then_get_returns_new_instance(session: SPARQLSession, odos: Person) -> None:
    session.put(odos)
    first = session.get(Person, odos.id)
    session.expunge(first)
    second = session.get(Person, odos.id)
    assert first is not None
    assert second is not None
    assert first is not second


def test_expunge_all_clears_cache_keeps_pending(session: SPARQLSession, odos: Person) -> None:
    other = Person(id=IRI("urn:person:other"), name="Other")
    session.autoflush = False
    session.put(odos)
    session.get(Person, odos.id)
    session.put(other, flush=False)
    assert len(session._state.pending) == 1
    session.expunge_all()
    assert len(session._state.pending) == 1
    from sparqlmodel.session_state import identity_key_for_iri

    assert session._state.get_identity(identity_key_for_iri(Person, odos.id)) is None
    session.flush()
    assert session.get(Person, odos.id) is not None
    assert session.get(Person, other.id) is not None


def test_delete_expires_identity(session: SPARQLSession, odos: Person) -> None:
    session.put(odos)
    session.get(Person, odos.id)
    session.delete(odos)
    assert session.get(Person, odos.id) is None


def test_get_deep_load_reuses_identity(session: SPARQLSession, odos: Person) -> None:
    session.put(odos)
    session.get(Person, odos.id, depth=0)
    deep1 = session.get(Person, odos.id, depth=1)
    deep2 = session.get(Person, odos.id, depth=1)
    assert deep1 is deep2
    assert deep1.works_for is not None


def test_get_deep_reload_reconciles_nested_identity(
    session: SPARQLSession, odos: Person, acme: Organization
) -> None:
    session.put(odos)
    stale_org = session.get(Organization, acme.id)
    assert stale_org is not None
    renamed = Organization(id=acme.id, name="Renamed Corp")
    session.put(Person(id=odos.id, name="Odos", works_for=renamed))
    person = session.get(Person, odos.id, depth=1)
    assert person is not None
    assert person.works_for is not None
    assert person.works_for.name == "Renamed Corp"
    assert session.get(Organization, acme.id) is person.works_for


def test_register_embedded_identities_collection() -> None:
    from unittest.mock import patch

    from pydantic.fields import FieldInfo

    from sparqlmodel.session_core import _register_embedded_identities
    from sparqlmodel.session_state import SessionState, identity_key_for_iri

    acme = Organization(id=IRI("urn:org:acme"), name="Acme")
    beta = Organization(id=IRI("urn:org:beta"), name="Beta")
    root = Person(id=IRI("urn:p:1"), name="P", works_for=None)
    object.__setattr__(root, "members", [acme, beta])

    state = SessionState()
    field_info = FieldInfo()
    with patch.object(
        Person,
        "get_relationship_fields",
        return_value=[("members", field_info, Organization)],
    ):
        _register_embedded_identities(state, root)

    assert state.get_identity(identity_key_for_iri(Organization, acme.id)) is acme
    assert state.get_identity(identity_key_for_iri(Organization, beta.id)) is beta


def test_get_shallow_after_deep_updates_identity_map(session: SPARQLSession, odos: Person) -> None:
    from sparqlmodel.session_state import identity_key_for_iri

    session.put(odos)
    deep = session.get(Person, odos.id, depth=1)
    shallow = session.get(Person, odos.id, depth=0)
    assert shallow is deep
    assert shallow.works_for is None
    key = identity_key_for_iri(Person, odos.id)
    assert session._state.get_identity(key) is deep
    again = session.get(Person, odos.id, depth=1)
    assert again is deep
    assert again.works_for is not None


def test_get_none_expires_identity_when_removed_from_graph(
    session: SPARQLSession, odos: Person
) -> None:
    from sparqlmodel.graph import owned_triples_for_subjects, triples_to_graph
    from sparqlmodel.session_state import identity_key_for_iri

    session.put(odos)
    session.get(Person, odos.id, depth=1)
    key = identity_key_for_iri(Person, odos.id)
    assert session._state.get_identity(key) is not None
    from sparqlmodel.graph import cascade_subjects_for_removal

    subjects = cascade_subjects_for_removal(odos, session.graph, for_put=False)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, session.graph))
    session.store.update_graph(remove=remove_g)
    assert session.get(Person, odos.id) is None
    assert session._state.get_identity(key) is None


def test_get_same_depth_not_stale_after_graph_remove(session: SPARQLSession, odos: Person) -> None:
    from sparqlmodel.graph import (
        cascade_subjects_for_removal,
        owned_triples_for_subjects,
        triples_to_graph,
    )

    session.put(odos)
    loaded = session.get(Person, odos.id, depth=1)
    assert loaded is not None
    subjects = cascade_subjects_for_removal(odos, session.graph, for_put=False)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, session.graph))
    session.store.update_graph(remove=remove_g)
    assert session.get(Person, odos.id, depth=1) is None


def test_get_cached_none_when_subject_still_missing(session: SPARQLSession) -> None:
    from sparqlmodel.graph import (
        cascade_subjects_for_removal,
        owned_triples_for_subjects,
        triples_to_graph,
    )
    from sparqlmodel.session_state import identity_key_for_iri

    plain = Person(id=IRI("urn:p:gone"), name="Gone")
    session.put(plain)
    subjects = cascade_subjects_for_removal(plain, session.graph, for_put=False)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, session.graph))
    session.store.update_graph(remove=remove_g)
    id_key = identity_key_for_iri(Person, plain.id)
    session._state.set_hydration((Person, id_key[1], 0), None)
    assert session.get(Person, plain.id) is None


def test_get_iri_ref_identity_not_stale_after_graph_remove(session: SPARQLSession) -> None:
    from sparqlmodel.graph import (
        cascade_subjects_for_removal,
        owned_triples_for_subjects,
        triples_to_graph,
    )

    by_ref = Person(id=IRI("urn:p:ref-only"), name="Ref", works_for=IRI("urn:org:acme"))
    session.put(by_ref)
    subjects = cascade_subjects_for_removal(by_ref, session.graph, for_put=False)
    remove_g = triples_to_graph(owned_triples_for_subjects(subjects, session.graph))
    session.store.update_graph(remove=remove_g)
    assert session.get(Person, by_ref.id) is None


def test_depth_satisfied_leaf_and_iri_branches() -> None:
    from tests.models import DualRelPerson, Location, Organization, Person, TeamLead

    loc = Location(id=IRI("urn:loc:boston"), name="Boston")
    assert SPARQLSession._depth_satisfied(loc, 1)

    by_ref = Person(id=IRI("urn:p:ref"), name="Ref", works_for=IRI("urn:org:acme"))
    assert SPARQLSession._depth_satisfied(by_ref, 2)

    loc = Location(id=IRI("urn:loc:2"), name="Here")
    org = Organization(id=IRI("urn:org:2"), name="Org", located_in=loc)
    optional_mgr = DualRelPerson(
        id=IRI("urn:p:opt"),
        name="Opt",
        works_for=org,
        manager=None,
    )
    assert SPARQLSession._depth_satisfied(optional_mgr, 2)

    dept_iri = TeamLead(id=IRI("urn:lead:iri"), name="Lead", department=None)
    object.__setattr__(dept_iri, "department", IRI("urn:org:dept"))
    assert not SPARQLSession._depth_satisfied(dept_iri, 2)

    bad = TeamLead(id=IRI("urn:lead:bad"), name="Lead", department=None)
    object.__setattr__(bad, "department", "not-a-model")  # type: ignore[arg-type]
    assert not SPARQLSession._depth_satisfied(bad, 2)


def test_depth_satisfied_requires_all_relationship_branches() -> None:
    from tests.models import DualRelPerson, Location, Organization, TeamLead

    loc = Location(id=IRI("urn:loc:boston"), name="Boston")
    org = Organization(id=IRI("urn:org:acme"), name="Acme", located_in=loc)
    lead = TeamLead(id=IRI("urn:lead:1"), name="Lead", department=org)
    complete = DualRelPerson(
        id=IRI("urn:p:dual"),
        name="Pat",
        works_for=org,
        manager=lead,
    )
    assert SPARQLSession._depth_satisfied(complete, 2)

    # manager present but not a loaded SPARQLModel (depth 2 requires materialized hops)
    incomplete = DualRelPerson(
        id=IRI("urn:p:dual"),
        name="Pat",
        works_for=org,
        manager=None,
    )
    object.__setattr__(incomplete, "manager", "not-a-model")  # type: ignore[arg-type]
    assert not SPARQLSession._depth_satisfied(incomplete, 2)

    partial = DualRelPerson(
        id=IRI("urn:p:partial"),
        name="Pat",
        works_for=org,
        manager=None,
    )
    assert SPARQLSession._depth_satisfied(partial, 1)
    only_works = DualRelPerson(
        id=IRI("urn:p:one"),
        name="Pat",
        works_for=org,
        manager=None,
    )
    object.__setattr__(only_works, "manager", IRI("urn:lead:missing"))
    assert not SPARQLSession._depth_satisfied(only_works, 1)


def test_get_depth_two_multi_relationship_loads_all_branches(
    session: SPARQLSession,
) -> None:
    from tests.models import DualRelPerson, Location, Organization, TeamLead

    loc = Location(id=IRI("urn:loc:boston"), name="Boston")
    org = Organization(id=IRI("urn:org:acme"), name="Acme", located_in=loc)
    dept = Organization(id=IRI("urn:org:dept"), name="Dept")
    lead = TeamLead(id=IRI("urn:lead:1"), name="Lead", department=dept)
    person = DualRelPerson(
        id=IRI("urn:p:dual"),
        name="Pat",
        works_for=org,
        manager=lead,
    )
    session.put(person)
    shallow = session.get(DualRelPerson, person.id, depth=1)
    assert shallow is not None
    deep = session.get(DualRelPerson, person.id, depth=2)
    assert deep is not None
    assert deep.works_for is not None
    assert deep.works_for.located_in is not None
    assert deep.manager is not None
    assert deep.manager.department is not None
    assert session.get(DualRelPerson, person.id, depth=2) is deep
