# Getting started

## Install

```bash
pip install sparqlmodel
```

Optional extras:

```bash
pip install "sparqlmodel[http]"      # HttpStore (httpx)
pip install "sparqlmodel[fastapi]"   # FastAPI session + RDF responses
```

Requires **Python 3.10+**.

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

with SPARQLSession() as session:
    session.put(odos)

    found = session.query(Person).where(Person.name == "Odos").first()
    team = session.query(Person).where(Person.works_for.name == "Acme Corp").all()
    full = session.get(Person, odos.id, depth=1)
```

## Query example

```python
with SPARQLSession() as session:
    session.query(Person).where(Person.name == "Odos").all()
    session.query(Person).where(
        (Person.name == "Odos") | (Person.name == "Ada")
    ).all()
    session.query(Person).where(Person.name.in_(("Odos", "Ada"))).limit(10).all()
```

## Remote store

```python
from sparqlmodel import HttpStore, SPARQLSession

with SPARQLSession(store=HttpStore("http://localhost:3030/ds/sparql")) as session:
    session.put(odos)
```

See {doc}`PRODUCTION` for HttpStore mirror semantics and deployment.

## Next steps

- {doc}`ORM` — session lifecycle, cascade, hydration
- {doc}`SPECS` — technical specification
- {doc}`api/index` — Python API reference
