"""SparqlModel — SPARQL ORM for RDF triple stores.

The SQLModel of SPARQL: typed models, :class:`~sparqlmodel.session.SPARQLSession`
as the main entry point, and Python queries that compile to SPARQL.

Requires ``triplemodel>=0.10`` and ``pyoxigraph`` for in-process graphs; SparqlModel owns the
session, query compiler, stores, and cascade policy.
"""

from sparqlmodel._version import __version__
from sparqlmodel.exceptions import (
    ConfigurationError,
    HydrationError,
    QueryError,
    SparqlModelError,
    StaleTripleWarning,
)
from sparqlmodel.fields import Field, Relationship
from sparqlmodel.model import SPARQLModel
from sparqlmodel.session import SPARQLSession
from sparqlmodel.stores.http import HttpStore
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.types import IRI

__all__ = [
    "ConfigurationError",
    "Field",
    "HydrationError",
    "HttpStore",
    "IRI",
    "MemoryStore",
    "QueryError",
    "Relationship",
    "SPARQLModel",
    "SPARQLSession",
    "SparqlModelError",
    "StaleTripleWarning",
    "__version__",
]
