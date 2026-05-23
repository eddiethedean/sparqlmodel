"""SparqlModel — SPARQL ORM for RDF triple stores.

The SQLModel of SPARQL: typed models, :class:`~sparqlmodel.session.SPARQLSession`
as the main entry point, and Python queries that compile to SPARQL.

Requires ``triplemodel>=0.12`` and ``pyoxigraph`` for in-process graphs; SparqlModel owns the
session, query compiler, stores, and cascade policy.
"""

from triplemodel import BackPopulates, Lang, LangString, MultiLangString, OntologyRegistry
from triplemodel.fields import inverse_pair
from triplemodel.fields.resource_ref import ResourceRef
from triplemodel.terms.typed_literal import TypedLiteral

from sparqlmodel._version import __version__
from sparqlmodel.async_session import AsyncSPARQLSession
from sparqlmodel.exceptions import (
    ConfigurationError,
    HydrationError,
    QueryError,
    SparqlModelError,
    StaleTripleWarning,
)
from sparqlmodel.expressions import not_, property_eq, property_path
from sparqlmodel.fields import Field, Relationship
from sparqlmodel.model import SPARQLModel
from sparqlmodel.schema_registry import SchemaRegistry
from sparqlmodel.session import SPARQLSession
from sparqlmodel.stores.async_http import AsyncHttpStore
from sparqlmodel.stores.async_memory import AsyncMemoryStore
from sparqlmodel.stores.http import HttpStore
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.types import IRI

__all__ = [
    "AsyncHttpStore",
    "AsyncMemoryStore",
    "AsyncSPARQLSession",
    "BackPopulates",
    "ConfigurationError",
    "Field",
    "HydrationError",
    "HttpStore",
    "IRI",
    "Lang",
    "LangString",
    "MemoryStore",
    "MultiLangString",
    "OntologyRegistry",
    "QueryError",
    "Relationship",
    "ResourceRef",
    "SPARQLModel",
    "SPARQLSession",
    "SchemaRegistry",
    "SparqlModelError",
    "StaleTripleWarning",
    "TypedLiteral",
    "__version__",
    "inverse_pair",
    "not_",
    "property_eq",
    "property_path",
]
