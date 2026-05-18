"""SparqlModel — SPARQL ORM for RDF triple stores.

The SQLModel of SPARQL: typed models, :class:`~sparqlmodel.session.SPARQLSession`
as the main entry point, and Python queries that compile to SPARQL.

Requires ``triplemodel>=0.9`` for Pydantic ↔ RDF mapping; SparqlModel owns the
session, query compiler, stores, and cascade policy.
"""

from sparqlmodel._version import __version__
from sparqlmodel.exceptions import ConfigurationError, HydrationError, QueryError, SparqlModelError
from sparqlmodel.fields import Field, Relationship
from sparqlmodel.model import SPARQLModel
from sparqlmodel.session import SPARQLSession
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.types import IRI

__all__ = [
    "ConfigurationError",
    "Field",
    "HydrationError",
    "IRI",
    "MemoryStore",
    "QueryError",
    "Relationship",
    "SPARQLModel",
    "SPARQLSession",
    "SparqlModelError",
    "__version__",
]
