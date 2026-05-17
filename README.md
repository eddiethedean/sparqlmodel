# SparqlModel

**SPARQL-native object graph mapper for RDF triple stores.**

SparqlModel brings SQLModel-style ergonomics to RDF: typed Pydantic models, Pythonic queries that compile to SPARQL, in-memory persistence via RDFLib, and RDF export.

SparqlModel is the **ORM and SPARQL layer** (session, queries, stores, cascade policy). Stateless Pydantic ↔ RDF mapping and file I/O live in **[RDFModel](https://github.com/eddiethedean/rdfmodel)**. The two packages share a stack: SparqlModel will depend on `rdfmodel` once upstream sync and multi-value milestones land (see [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md)).

## Install

```bash
pip install sparqlmodel
```

For development:

```bash
pip install -e ".[dev]"
```

## Quickstart

```python
from sparqlmodel import Field, IRI, Relationship, SPARQLModel, SPARQLSession

class Organization(SPARQLModel):
    rdf_type = "schema:Organization"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")

class Person(SPARQLModel):
    rdf_type = "schema:Person"
    __prefixes__ = {"schema": "https://schema.org/"}

    id: IRI
    name: str = Field("schema:name")
    works_for: Organization | None = Relationship(
        "schema:worksFor", model=Organization
    )

acme = Organization(id=IRI("urn:org:acme"), name="Acme Corp")
odos = Person(id=IRI("urn:person:odos"), name="Odos", works_for=acme)

session = SPARQLSession()
session.put(odos)

# Query with Python expressions
found = session.query(Person).where(Person.name == "Odos").first()
print(found.name)  # Odos

# Nested filter (single relationship hop)
team = session.query(Person).where(Person.works_for.name == "Acme Corp").all()

# Hydrate relationships
full = session.get(Person, odos.id, depth=1)
print(full.works_for.name)  # Acme Corp

# Export RDF
from sparqlmodel.serializers import export_model

print(export_model(odos, format="turtle"))
```

## Features (0.1.x)

- `SPARQLModel` — Pydantic v2 models mapped to RDF predicates
- `SPARQLSession` — in-memory CRUD against an RDFLib graph
- Query builder — `session.query(Model).where(Model.field == value)`
- SPARQL compiler — scalar and single-hop nested filters
- Graph hydration — `session.get(Model, iri, depth=0|1|2)`
- Serializers — Turtle, N-Triples, RDF/XML, JSON-LD

### Persistence semantics

- **`put`** upserts the model and any **embedded** nested `SPARQLModel` values (composition). Owned triples are removed for the root, nested objects in the current tree, and relationship targets previously stored in the graph for that subject (orphan cleanup). Relationship values stored as **`IRI` only** are external references and are not cascade-deleted.
- **`add`** inserts triples without removing existing ones; re-`add`ing the same `id` can leave stale literal values.
- **`delete`** removes owned triples for the model and cascaded embedded resources (same rules as `put`). Shared resources linked only by `IRI` reference are kept.

### Query filters

- **`==`** — exact match on a predicate value.
- **`!=`** — matches subjects that have **some** value for the predicate that is not equal to the right-hand side (subjects with no value are excluded).
- Combine filters with `.where(a, b)` or `(a) & (b)`.
- Filter values cannot be `None` (raises `QueryError`).
- Nested filters require the related resource to have the expected `rdf:type` in the graph.

### Known limitations

- **Shared embedded resources** — If the same IRI is embedded from multiple parents, `put`/`delete` on one parent can remove that resource’s triples. Use `IRI` references for shared entities.
- **`add` vs `put`** — `add` never removes triples; duplicate `add` after in-place edits can leave stale literals. Prefer `put` for updates.
- **Multi-valued predicates** — Only the first object per predicate is loaded; multiple `!=` filters on multi-valued predicates follow RDF existential semantics (see SPECS).
- **Declared predicates only** — `put`/`delete` remove triples for mapped predicates plus `rdf:type`, not arbitrary extension triples on a subject.
- **JSON-LD** — `model_dump_jsonld()` / `model_validate_jsonld()` differ from `export_model(..., format="json-ld")` (RDFLib serialization). Typed literals and relationship lists are not fully supported in the custom JSON-LD path.
- **Export side effect** — RDF export may assign a `urn:uuid:…` id via `ensure_id()` when `id` is unset.

For development, run tests from the project virtualenv: `.venv/bin/pytest`.

## Roadmap

| Release | Focus |
|---------|--------|
| **0.2** | HTTP SPARQL store, richer query compiler (`OR`, comparisons), identity map, optional FastAPI — RDFModel dev pin only |
| **0.3** | Integrate `rdfmodel` for mapping/sync; thin `graph.py`; multi-value via upstream |
| **0.4+** | Delegate file parse/serialize to RDFModel; named graphs when upstream supports Dataset |

Full checklist: [docs/ROADMAP.md](docs/ROADMAP.md). Ecosystem boundaries: [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md).

## Documentation

- [Technical specification](docs/SPECS.md)
- [Project plan](docs/PLAN.md)
- [Roadmap](docs/ROADMAP.md)
- [Ecosystem guide (RDFModel alignment)](docs/ECOSYSTEM.md)
- [Changelog](CHANGELOG.md)

## License

MIT — see [LICENSE](https://github.com/eddiethedean/sqarqlmodel/blob/main/LICENSE).
