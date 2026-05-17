"""Persistence stores for SparqlModel."""

from sparqlmodel.stores.base import Store
from sparqlmodel.stores.memory import MemoryStore

__all__ = ["MemoryStore", "Store"]
