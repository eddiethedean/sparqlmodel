"""RDF helpers for tests (pyoxigraph + triplemodel.Store)."""

from __future__ import annotations

from pyoxigraph import BlankNode, Literal, NamedNode
from triplemodel import Store

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
XSD_BOOLEAN = "http://www.w3.org/2001/XMLSchema#boolean"
XSD_INTEGER = "http://www.w3.org/2001/XMLSchema#integer"
XSD_DOUBLE = "http://www.w3.org/2001/XMLSchema#double"


def store() -> Store:
    return Store()


def iri(value: str) -> str:
    return value


def bnode(label: str = "") -> BlankNode:
    return BlankNode(label)


def typed_literal(
    value: str | int | float | bool,
    datatype: str,
) -> Literal:
    return Literal(value, datatype=NamedNode(datatype))


def plain_literal(value: str) -> Literal:
    return Literal(value)
