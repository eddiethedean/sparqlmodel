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
| `==` | Triple pattern match | Strings compile as literals unless field is `IRI` |
| `!=` | NOT EXISTS (default since 0.5.2) | See `use_inequality_for_ne()` for legacy inequality |
| `&` | AND | Use parentheses: `(A & B) \| C` |
| `\|` | OR | `(A & B) \| C` compiles with correct precedence (0.2+) |
| `<`, `>`, `<=`, `>=` | comparison | Typed numeric literals use XSD datatypes |
| `.in_(tuple)` | IN / VALUES | Membership; lists and other sequences accepted — not a bare `str` (use `("value",)` or `["value"]`) |
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

Default ``!=`` uses ``FILTER NOT EXISTS`` (since 0.5.2): resources with no value for the field match, and multi-valued predicates are handled correctly. For pre-0.5.2 inequality semantics (excludes unbound values):

```python
session.query(Person).where(Person.name != "X").use_inequality_for_ne().all()
```

``.use_optional_for_comparisons()`` toggles NOT EXISTS vs inequality for ``!=`` (historical name). Nullable relationship hops still use real ``OPTIONAL`` blocks when the field annotation includes ``None``.

Ordering (`<`, `>`, …) and `in_` still require a bound predicate value (SPARQL-native). Unique variables are generated per `!=` inside AND branches of OR expressions (0.2+).

Filter values on `IRI` fields (or unions including `IRI`) accept absolute `urn:` and `http(s)://` strings, not only `prefix:local` compact IRIs.

## Pagination, sorting, and count

```python
with SPARQLSession() as session:
    page = (
        session.query(Person)
        .where(Person.name != "Other")
        .order_by(Person.name)
        .offset(20)
        .limit(10)
        .all()
    )
    total = session.query(Person).where(Person.name != "Other").count()
```

| Method | Behavior |
|--------|----------|
| `.offset(n)` | `OFFSET n` (after `ORDER BY`, before `LIMIT`) |
| `.order_by(field, *, desc=False)` | `ORDER BY` on a scalar field; repeatable for tie-breakers |
| `.count()` | `COUNT(DISTINCT ?root)`; ignores `.limit()`, `.offset()`, and `.order_by()` |
| `.first()` | Always `LIMIT 1`; ignores prior `.limit()` and `.offset()` |

## Nullable relationships

For `Relationship | None` (or unions including `None`), the compiler wraps each nullable hop in SPARQL `OPTIONAL`. That keeps resources without a link in the result set when filters use `!=` on nested scalars.

Explicit absence or presence:

```python
session.query(Person).where(Person.works_for.is_(None)).all()
session.query(Person).where(Person.works_for.is_not(None)).all()
```

``use_optional_for_comparisons()`` only toggles default ``!=`` / NOT EXISTS semantics (historical name); it does not emit ``OPTIONAL`` blocks.

## Result helpers

```python
q = session.query(Person).where(Person.name == "Odos")
q.first()                    # one or None (always LIMIT 1, ignores prior .limit() / .offset())
q.first(depth=1)             # eager-load one hop
q.limit(10).all()
q.limit(10).all(depth=1)
```

```{warning}
On {class}`~sparqlmodel.stores.http.HttpStore` / {class}`~sparqlmodel.stores.async_http.AsyncHttpStore`, `.all()` and `.first()` run a remote SELECT but hydrate each row with `get()` from the **local mirror**. Rows for IRIs this store has not written are omitted. See {doc}`../troubleshooting` — `query().all()` returns fewer rows.
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
