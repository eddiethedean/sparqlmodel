"""SPARQL N3 formatting for UPDATE bodies (INSERT/DELETE DATA)."""

from __future__ import annotations

from pyoxigraph import BlankNode, Literal, NamedNode, Triple
from triplemodel.store.terms import OxTerm, QuadPredicate, QuadSubject, term_str

from sparqlmodel.exceptions import QueryError
from sparqlmodel.sparql_escape import escape_sparql_string


def validate_iri_token(iri: str) -> str:
    """Reject IRIs that would break angle-bracket tokens in SPARQL."""
    if not iri or any(c in iri for c in " \n\r\t<>"):
        raise QueryError(f"Invalid IRI for SPARQL: {iri!r}")
    return iri


def term_to_n3(term: OxTerm | QuadSubject | QuadPredicate | str) -> str:
    """Format a pyoxigraph term as an N3 term for SPARQL UPDATE."""
    if isinstance(term, str):
        if term.startswith("_:"):
            return term
        if term.startswith("<") and term.endswith(">"):
            validate_iri_token(term[1:-1])
            return term
        return f"<{validate_iri_token(term)}>"
    if isinstance(term, NamedNode):
        return f"<{validate_iri_token(term.value)}>"
    if isinstance(term, BlankNode):
        raw = str(term)
        return raw if raw.startswith("_:") else f"_:{raw}"  # pragma: no cover
    if isinstance(term, Literal):
        out = f'"{escape_sparql_string(str(term.value))}"'
        if term.datatype is not None:
            out += f"^^{term_to_n3(term.datatype)}"
        elif term.language is not None:
            out += f"@{term.language}"
        return out
    if isinstance(term, Triple):
        s, p, o = term_to_n3(term.subject), term_to_n3(term.predicate), term_to_n3(term.object)
        return f"<< {s} {p} {o} >>"
    return f"<{term_str(term)}>"


def triple_to_n3(
    subject: QuadSubject | str,
    predicate: QuadPredicate | str,
    obj: OxTerm | str,
) -> str:
    return f"{term_to_n3(subject)} {term_to_n3(predicate)} {term_to_n3(obj)}"
