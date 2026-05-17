"""Tests for MemoryStore."""

import pytest

from sparqlmodel.exceptions import QueryError
from sparqlmodel.stores.memory import MemoryStore


def test_non_select_query() -> None:
    store = MemoryStore()
    with pytest.raises(QueryError):
        store.query("ASK { ?s ?p ?o }")
