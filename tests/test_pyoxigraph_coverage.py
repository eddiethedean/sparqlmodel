"""Coverage for pyoxigraph helpers (rdf_n3, sparql_json, memory term values)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pyoxigraph import BlankNode, Literal, NamedNode, Triple

from sparqlmodel import IRI, SPARQLSession
from sparqlmodel.exceptions import QueryError
from sparqlmodel.expressions import AndExpr, OrExpr, _flatten_and_parts
from sparqlmodel.graph import _term_subject_key
from sparqlmodel.rdf_n3 import term_to_n3, triple_to_n3
from sparqlmodel.serializers import export_graph
from sparqlmodel.stores.memory import MemoryStore
from sparqlmodel.stores.sparql_json import _term_value, parse_sparql_json_bindings
from tests.models import Organization, Person


def test_term_to_n3_string_and_iri_forms() -> None:
    assert term_to_n3("_:abc") == "_:abc"
    assert term_to_n3("<urn:already>") == "<urn:already>"
    assert term_to_n3("urn:plain") == "<urn:plain>"


def test_term_to_n3_named_node_blank_node_literal() -> None:
    assert term_to_n3(NamedNode("urn:n")) == "<urn:n>"
    bn = BlankNode()
    formatted = term_to_n3(bn)
    assert formatted.startswith("_:")
    lit = MagicMock(spec=Literal)
    lit.value = "say"
    lit.datatype = None
    lit.language = "en"
    assert term_to_n3(lit) == '"say"@en'
    typed = Literal("42", datatype=NamedNode("http://www.w3.org/2001/XMLSchema#integer"))
    assert "^^" in term_to_n3(typed)


def test_term_to_n3_fallback_term_str(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sparqlmodel.rdf_n3.term_str", lambda _t: "urn:fallback")
    assert term_to_n3(object()) == "<urn:fallback>"


def test_term_to_n3_rdf_star_triple() -> None:
    inner = Triple(
        NamedNode("urn:s"),
        NamedNode("urn:p"),
        NamedNode("urn:o"),
    )
    out = term_to_n3(inner)
    assert out.startswith("<< ")
    assert out.endswith(" >>")


def test_triple_to_n3() -> None:
    n3 = triple_to_n3("urn:s", "urn:p", Literal("x"))
    assert "urn:s" in n3 and "urn:p" in n3


def test_term_to_n3_literal_escapes_newline() -> None:
    lit = Literal("line\nbreak")
    n3 = term_to_n3(lit)
    assert r'"line\nbreak"' in n3


def test_parse_sparql_json_bindings_errors() -> None:
    with pytest.raises(ValueError, match="Invalid SPARQL JSON"):
        parse_sparql_json_bindings(b"{}")
    with pytest.raises(QueryError, match="ASK"):
        parse_sparql_json_bindings(b'{"head":{},"boolean":true}')
    with pytest.raises((ValueError, SyntaxError)):
        parse_sparql_json_bindings(
            json.dumps({"head": {"vars": []}, "results": {"bindings": {}}}).encode()
        )


def test_parse_sparql_json_bindings_unexpected_type(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Unexpected:
        pass

    def fake_parse(*_args: object, **_kwargs: object) -> object:
        return _Unexpected()

    monkeypatch.setattr(
        "sparqlmodel.stores.sparql_json.parse_query_results",
        fake_parse,
    )
    with pytest.raises(QueryError, match="Unexpected SPARQL result"):
        parse_sparql_json_bindings(b"{}")


def test_parse_sparql_json_bindings_typed_literal() -> None:
    payload = {
        "head": {"vars": ["age"]},
        "results": {
            "bindings": [
                {
                    "age": {
                        "type": "literal",
                        "value": "30",
                        "datatype": "http://www.w3.org/2001/XMLSchema#integer",
                    }
                },
            ],
        },
    }
    rows = parse_sparql_json_bindings(json.dumps(payload).encode())
    assert rows == [{"age": "30"}]


def test_term_value_variants() -> None:
    from pyoxigraph import BlankNode, Literal, NamedNode

    assert _term_value(None) is None
    assert _term_value(NamedNode("urn:u")) == "urn:u"
    assert _term_value(BlankNode("b1")).startswith("_:")
    assert _term_value(Literal("lit")) == "lit"
    assert _term_value(99) == "99"


def test_memory_store_unexpected_result_type() -> None:
    store = MemoryStore()
    store._graph = MagicMock()
    store._graph.query.return_value = object()
    with pytest.raises(QueryError, match="Unexpected SPARQL result"):
        store.query("SELECT ?s WHERE { ?s ?p ?o }")


def test_memory_store_query_failure() -> None:
    store = MemoryStore()
    store._graph = MagicMock()
    store._graph.query.side_effect = RuntimeError("bad sparql")
    with pytest.raises(QueryError, match="failed"):
        store.query("SELECT ?s WHERE { ?s ?p ?o }")


def test_memory_store_non_select_result() -> None:
    from triplemodel.store.sparql_result import SparqlResult

    store = MemoryStore()
    mock_result = MagicMock(spec=SparqlResult)
    mock_result.type = "ASK"
    store._graph = MagicMock()
    store._graph.query.return_value = mock_result
    with pytest.raises(QueryError, match="Expected SELECT"):
        store.query("SELECT ?s WHERE { ?s ?p ?o }")


def test_memory_term_value_coercion() -> None:
    from sparqlmodel.stores.memory import _term_value as memory_term_value

    assert memory_term_value(None) is None
    assert memory_term_value(NamedNode("urn:x")) == "urn:x"
    assert memory_term_value(Literal("hello")) == "hello"
    bn = BlankNode()
    assert memory_term_value(bn).startswith("_:")
    assert memory_term_value(99) == "99"


def test_term_subject_key_string_iri() -> None:
    prefixes = {"schema": "https://schema.org/"}
    assert _term_subject_key("urn:subject", prefixes) == "urn:subject"
    assert _term_subject_key("_:bnode", prefixes) == "_:bnode"
    assert _term_subject_key("schema:Person", prefixes) == "https://schema.org/Person"


def test_flatten_and_parts_nested_and() -> None:
    e1 = Person.name == "a"
    e2 = Person.name == "b"
    inner = AndExpr((e1, e2))
    flat = _flatten_and_parts((inner, Person.name == "c"))
    assert len(flat) == 3


def test_or_expr_and_with_and_expr_and_rand() -> None:
    from sparqlmodel.exceptions import QueryError

    e1 = Person.name == "a"
    e2 = Person.name == "b"
    e3 = Person.name == "c"
    or_expr = OrExpr((e1, e2))
    with pytest.raises(QueryError, match="Cannot combine OR and AND"):
        _ = or_expr & AndExpr((e3,))
    with pytest.raises(QueryError, match="Cannot combine OR and AND"):
        or_expr.__rand__(Person.name == "c")


def test_export_graph_bytes_decode() -> None:
    with patch("sparqlmodel.serializers.dump_graph", return_value=b"@prefix x: <> ."):
        assert export_graph(MemoryStore().graph, format="turtle").startswith("@prefix")


def test_export_graph_none_result() -> None:
    with patch("sparqlmodel.serializers.dump_graph", return_value=None):
        assert export_graph(MemoryStore().graph, format="turtle") == ""


def test_session_exit_suppresses_close_error_when_original_exception(
    odos: Person,
) -> None:
    with (
        pytest.raises(ValueError, match="original"),
        SPARQLSession(autoflush=False, rollback_on_error=False) as session,
    ):
        session.put(odos, flush=False)
        raise ValueError("original")


def test_session_exit_reraises_close_error() -> None:
    with (
        patch.object(SPARQLSession, "close", side_effect=RuntimeError("close failed")),
        pytest.raises(RuntimeError, match="close failed"),
        SPARQLSession(),
    ):
        pass


def test_get_depth_two_not_satisfied_when_nested_lacks_embed(session) -> None:
    org = Organization(id=IRI("urn:org:shallow"), name="Shallow", located_in=None)
    person = Person(id=IRI("urn:p:shallow"), name="Pat", works_for=org)
    session.put(person)
    shallow = session.get(Person, person.id, depth=1)
    assert shallow is not None
    assert shallow.works_for is not None
    deep = session.get(Person, person.id, depth=2)
    assert deep is not None
    assert deep.works_for is not None
    assert deep.works_for.name == "Shallow"
