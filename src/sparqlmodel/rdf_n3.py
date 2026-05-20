"""SPARQL N3 formatting for UPDATE bodies (INSERT/DELETE DATA)."""

from __future__ import annotations

from pyoxigraph import BlankNode, Literal, NamedNode, Triple
from triplemodel.store.terms import OxTerm, QuadPredicate, QuadSubject, term_str


def term_to_n3(term: OxTerm | QuadSubject | QuadPredicate | str) -> str:
    """Format a pyoxigraph term as an N3 term for SPARQL UPDATE."""
    if isinstance(term, str):
        if term.startswith("_:"):
            return term
        if term.startswith("<") and term.endswith(">"):
            return term
        return f"<{term}>"
    if isinstance(term, NamedNode):
        return f"<{term.value}>"
    if isinstance(term, BlankNode):
        raw = str(term)
        return raw if raw.startswith("_:") else f"_:{raw}"
    if isinstance(term, Literal):
        escaped = str(term.value).replace("\\", "\\\\").replace('"', '\\"')
        out = f'"{escaped}"'
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
