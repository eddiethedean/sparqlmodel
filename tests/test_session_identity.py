"""Session identity map, cache, and flush."""

from __future__ import annotations

import pytest

from sparqlmodel import IRI, SPARQLSession
from tests.models import Person


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


def test_flush_requeues_on_failure(
    session: SPARQLSession, odos: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sparqlmodel import IRI

    other = Person(id=IRI("urn:person:other"), name="Other")
    session.autoflush = False
    session.put(odos, flush=False)
    session.put(other, flush=False)
    calls = {"n": 0}

    def failing_put(model: Person) -> Person:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("put failed")
        return SPARQLSession._put_impl(session, model)  # type: ignore[arg-type]

    monkeypatch.setattr(session, "_put_impl", failing_put)
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
    state.add_pending(p)
    assert state.pending == [p]
    state.clear_pending()


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


def test_get_shallow_after_deep_does_not_replace_identity(
    session: SPARQLSession, odos: Person
) -> None:
    session.put(odos)
    deep = session.get(Person, odos.id, depth=1)
    shallow = session.get(Person, odos.id, depth=0)
    assert shallow is not deep
    assert shallow.works_for is None
    assert session.get(Person, odos.id, depth=1) is deep
