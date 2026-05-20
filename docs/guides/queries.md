# Query DSL

`session.query(Model)` builds a SPARQL SELECT from Python expressions on model fields.

## Basic filters

```python
with SPARQLSession() as session:
    session.query(Person).where(Person.name == "Odos").all()
    session.query(Person).where(Person.name != "Other").all()
```

| Operator | SPARQL style | Notes |
|----------|--------------|-------|
| `==` | BIND / pattern match | Strings compile as literals unless field is `IRI` |
| `!=` | inequality | See `use_not_exists_for_ne()` below |
| `&` | AND | Use parentheses: `(A & B) \| C` |
| `\|` | OR | `(A & B) \| C` compiles with correct precedence (0.2+) |
| `<`, `>`, `<=`, `>=` | comparison | Typed numeric literals use XSD datatypes |
| `.in_(tuple)` | IN / VALUES | Membership; lists and other sequences accepted |
| `None` in filter | — | Raises {class}`~sparqlmodel.exceptions.QueryError` |

## Boolean composition

```python
session.query(Person).where(
    (Person.name == "Odos") | (Person.name == "Ada")
).all()

session.query(Person).where(
    (Person.name == "Odos") & (Person.works_for.name == "Acme")
).all()
```

Parenthesize mixed `&` and `|` for clarity — Python binds `&` tighter than `|`, and the compiler follows that precedence (same as `(A & B) | C`).

To AND an OR group with another filter, pass **separate** arguments to `.where()` (not `&` between OR and AND)::

    session.query(Person).where(
        (Person.name == "Odos") | (Person.name == "Ada"),
        Person.name != "Other",
    ).all()

Using `((A | B) & C)` raises {class}`~sparqlmodel.exceptions.QueryError` — it would silently compile as `A ∧ B ∧ C` if allowed.

## Multi-hop paths

Traverse relationships in filters:

```python
session.query(Person).where(Person.works_for.name == "Acme Corp").all()
```

The related resource must have the expected `rdf:type` in the graph. Unknown compact prefixes in filter values stay literals unless the field type is `IRI`.

## Negation semantics

Default `!=` uses inequality filters and **excludes** resources with no value for the field. For SQL-style “no matching triple” semantics (implemented with ``FILTER NOT EXISTS``, not SPARQL ``OPTIONAL``):

```python
session.query(Person).where(Person.name != "X").use_not_exists_for_ne().all()
# equivalent convenience:
session.query(Person).where(Person.name != "X").use_optional_for_comparisons().all()
```

Call ``use_optional_for_comparisons(False)`` to turn that behavior off again.

Ordering (`<`, `>`, …) and `in_` still require a bound predicate value (SPARQL-native). Unique variables are generated per `!=` inside AND branches of OR expressions (0.2+).

Filter values on `IRI` fields (or unions including `IRI`) accept absolute `urn:` and `http(s)://` strings, not only `prefix:local` compact IRIs.

## Result helpers

```python
q = session.query(Person).where(Person.name == "Odos")
q.first()                    # one or None (always LIMIT 1, ignores prior .limit())
q.first(depth=1)             # eager-load one hop
q.limit(10).all()
q.limit(10).all(depth=1)
```

```{note}
`offset`, `order_by`, and `count()` are planned for **0.7–0.8**. Until then use `.limit()` only or raw `session.execute`.
```

## Raw SPARQL

When the DSL is insufficient:

```python
rows = session.execute("""
    PREFIX schema: <https://schema.org/>
    SELECT ?s ?name WHERE {
        ?s a schema:Person ; schema:name ?name .
    }
""")
```

Configured namespace prefixes on the session are applied where supported.

## Security

Filter **values** are serialized with SparqlModel N3 helpers (`rdf_n3`). **Predicates** and class IRIs come from model metadata (trusted code). Do not pass untrusted strings into raw `execute()` without parameterization patterns appropriate to your endpoint.

See {doc}`../SPECS` — Security (SPARQL generation).

## Next

- {doc}`sessions` — store and session lifecycle
- {doc}`../api/query` — `Query`, expressions, compiler modules
