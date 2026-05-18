"""Tests for SPARQLSession context manager and close()."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sparqlmodel import SPARQLSession
from tests.models import Person

_CLOSED_MSG = "Cannot use a closed SPARQLSession"


def test_session_context_manager_flushes_pending(odos: Person) -> None:
    with SPARQLSession(autoflush=False) as session:
        session.put(odos, flush=False)
        assert len(session.graph) == 0
    assert len(session.graph) >= 2


def test_session_context_manager_rollback_on_error(odos: Person) -> None:
    with pytest.raises(RuntimeError), SPARQLSession(autoflush=False) as session:
        session.put(odos, flush=False)
        raise RuntimeError("boom")
    session = SPARQLSession()
    assert session.get(Person, odos.id) is None


def test_session_context_manager_keeps_pending_on_error_when_disabled(odos: Person) -> None:
    with (
        pytest.raises(RuntimeError),
        SPARQLSession(autoflush=False, rollback_on_error=False) as session,
    ):
        session.put(odos, flush=False)
        raise RuntimeError("boom")
    # Pending was not rolled back, but exit without flush means still not in a new session
    fresh = SPARQLSession()
    assert fresh.get(Person, odos.id) is None


def test_session_close_calls_store_close() -> None:
    store = MagicMock()
    store.graph = MagicMock()
    store.namespaces = None
    session = SPARQLSession(store=store, close_on_exit=False)
    session.close()
    store.close.assert_called_once()
    store.close.reset_mock()
    session.close()
    store.close.assert_not_called()


def test_session_context_manager_close_on_exit_false() -> None:
    store = MagicMock()
    store.graph = MagicMock()
    store.namespaces = None
    with SPARQLSession(store=store, close_on_exit=False) as session:
        assert session is not None
    store.close.assert_not_called()


def test_session_context_manager_closes_store_on_exit() -> None:
    store = MagicMock()
    store.graph = MagicMock()
    store.namespaces = None
    with SPARQLSession(store=store) as session:
        assert session is not None
    store.close.assert_called_once()


def test_session_enter_after_close_raises() -> None:
    session = SPARQLSession()
    session.close()
    with pytest.raises(RuntimeError, match=_CLOSED_MSG), session:
        pass


def test_session_operations_after_close_raise(odos: Person) -> None:
    session = SPARQLSession()
    session.close()
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.put(odos)
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.add(odos)
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.get(Person, odos.id)
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.query(Person).all()
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.execute("SELECT * WHERE { ?s ?p ?o }")
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.flush()
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.delete(odos)
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.expire(Person, odos.id)
    with pytest.raises(RuntimeError, match=_CLOSED_MSG):
        session.rollback_pending()
