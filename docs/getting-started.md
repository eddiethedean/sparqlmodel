# Getting started

A minimal path from install to your first query. For installation options and extras see {doc}`installation`.

## Install

```bash
pip install sparqlmodel
```

## Define models

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
```

## Persist and query

```python
acme = Organization(id=IRI("urn:org:acme"), name="Acme Corp")
odos = Person(id=IRI("urn:person:odos"), name="Odos", works_for=acme)

with SPARQLSession() as session:
    session.put(odos)

    found = session.query(Person).where(Person.name == "Odos").first()
    team = session.query(Person).where(Person.works_for.name == "Acme Corp").all()
    full = session.get(Person, odos.id, depth=1)
```

```{important}
Use `put()` for upserts (cascade + orphan cleanup). Use `add()` only when you will not overwrite existing subject data.
```

## What's next

| Guide | Topics |
|-------|--------|
| {doc}`guides/sessions` | Flush queue, stores, identity map, composition |
| {doc}`guides/queries` | Boolean filters, `!=`, limits, raw SPARQL |

| Topic | Document |
|-------|----------|
| Full ORM concepts | {doc}`ORM` |
| HttpStore / deployment | {doc}`PRODUCTION` |
| FastAPI | {doc}`guides/fastapi` |
| Python API | {doc}`api/index` |
| Problems | {doc}`troubleshooting` |
