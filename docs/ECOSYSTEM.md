# SparqlModel ecosystem guide (for SparqlModel development)

How **SparqlModel** (`sparqlmodel`) relates to **RDFModel** (`rdfmodel`) from the SparqlModel maintainer perspective.

Aligned docs in this repo: [PLAN.md](PLAN.md), [ROADMAP.md](ROADMAP.md), [SPECS.md](SPECS.md), [README.md](../README.md).

The canonical two-sided summary also lives in the RDFModel repo:  
[github.com/eddiethedean/rdfmodel/blob/main/docs/ECOSYSTEM.md](https://github.com/eddiethedean/rdfmodel/blob/main/docs/ECOSYSTEM.md)  
(adjust URL if your RDFModel remote differs.)

---

## Stack position

```text
┌──────────────────────────────────────────┐
│  SparqlModel  ← you work here            │
│  Session · Query · Compiler · Stores     │
└────────────────────┬─────────────────────┘
                     │  add dependency when ready
┌────────────────────▼─────────────────────┐
│  RDFModel                                │
│  Mapping · terms · parse/serialize       │
└────────────────────┬─────────────────────┘
                     │
┌────────────────────▼─────────────────────┐
│  rdflib · pydantic                       │
└──────────────────────────────────────────┘
```

**Rules for SparqlModel:**

1. **May** depend on `rdfmodel` (future); **must not** reimplement mapping logic that belongs there.
2. **Must not** expect RDFModel to import SparqlModel.
3. **Prefer** opening RDFModel issues/PRs for term/graph bugs; fix compiler/session bugs in SparqlModel.

---

## What SparqlModel is for

**Tagline:** SPARQL-native object graph mapper for RDF triple stores.

**Answers:** “How do I run an app with CRUD, filters, and updates over RDF?”

| Layer | SparqlModel owns it |
|-------|---------------------|
| `SPARQLSession` | `add`, `put`, `delete`, `get`, `execute` |
| Stores | `MemoryStore`, future `HttpStore` |
| Query DSL | `session.query(Model).where(...)` |
| SPARQL compiler | `==`, `!=`, `&`, nested hops → SPARQL |
| Hydration | `get(..., depth=0\|1\|2)` |
| Persistence policy | Owned triples, orphan cleanup, `add` vs `put` |
| App extras | FastAPI, HTTP SPARQL (roadmap) |

**Not SparqlModel’s job:** canonical literal/datatype conversion, subject-URI prefix safety, Turtle/JSON-LD format registry, or a stateless “dump this model to a file” API without a session — that is **RDFModel**.

---

## What RDFModel is for

**Tagline:** Pydantic models ↔ RDF graphs (library-first, stateless).

**Repo:** [github.com/eddiethedean/rdfmodel](https://github.com/eddiethedean/rdfmodel) (or RDFModel org) · PyPI: `rdfmodel`

| Layer | RDFModel owns it |
|-------|------------------|
| `RdfModel`, `rdf_field`, `Predicate` | Field ↔ predicate metadata |
| `Rdf` config | `namespace`, `type_uri`, `id_field` |
| `to_graph` / `from_graph` | Stateless round-trip |
| Terms | `python_to_term`, `term_to_python` |
| Files | `parse` / `serialize` (roadmap 0.4) |
| rdflib matrix | Namespaces, Dataset, etc. ([ROADMAP](https://github.com/eddiethedean/rdfmodel/blob/main/ROADMAP.md)) |

**Direct users:** ETL, tests, other libraries — including SparqlModel after integration.

```python
# RDFModel shape (stateless) — not SparqlModel’s primary API
person = Person(slug="alice", name="Alice")
g = person.to_graph()
restored = Person.from_graph(g, person.subject_uri())
```

---

## Where to implement a change

Use this before opening a PR in either repo.

| Symptom or feature | Repo | SparqlModel module (today) |
|--------------------|------|----------------------------|
| Wrong XSD type on export | **RDFModel** | `graph.py` → retire after integration |
| Subject IRI prefix collision | **RDFModel** | — |
| `put` left stale `foaf:age` triple | **RDFModel** sync + **SparqlModel** `put` policy | `graph.py`, `session.py` |
| Orphan embedded IRI after relationship change | **SparqlModel** | `graph.py` (`cascade_subjects_for_removal`) |
| `!=` filter semantics | **SparqlModel** | `compiler.py` |
| Nested `Person.works_for.name` filter | **SparqlModel** | `compiler.py` |
| Multi-valued field round-trip | **RDFModel** first | `hydration.py` consumes result |
| Turtle prefixes in export | **RDFModel** | `serializers.py` → thin wrapper |
| Remote Fuseki endpoint | **SparqlModel** | `stores/` (future `HttpStore`) |
| SHACL on save | **RDFModel** optional extra | hook from `session.put` optional |

**Heuristic:** if the fix would help a script that never creates a `SPARQLSession`, it belongs in **RDFModel**.

---

## Current overlap (technical debt)

Until `rdfmodel` is a declared dependency, SparqlModel duplicates RDFModel concerns:

| SparqlModel module | Overlaps RDFModel | Integration plan |
|------------------|-------------------|------------------|
| `graph.py` | `model_to_graph`, triple ownership | Call `rdfmodel` sync APIs; keep cascade/orphan here |
| `fields.py` | `rdf_field`, predicate metadata | Adapter or subclass; preserve `Field("curie")` UX |
| `types.py` (`IRI`, prefixes) | namespaces, subject IRIs | Keep `IRI` in SparqlModel; expand via RDFModel registry |
| `serializers.py` | `parse` / `serialize` | Delegate to `RdfModel` / graph helpers |
| `hydration.py` | `from_graph` | Build on `graph_to_model`; add depth + relationships |
| `compiler.py` | — | **Stay in SparqlModel** |
| `session.py`, `query.py` | — | **Stay in SparqlModel** |
| `stores/*` | — | **Stay in SparqlModel** |

Do **not** grow `graph.py` with new format parsers or datatype registries — add them upstream in RDFModel instead.

---

## Public API: keep vs converge

SparqlModel’s public API can stay familiar to SQLModel users. Internal implementation should call RDFModel.

| Concept | SparqlModel (keep for users) | RDFModel (implementation target) |
|---------|------------------------------|----------------------------------|
| Base class | `SPARQLModel` | Compose or subclass `RdfModel` |
| Type | `rdf_type = "schema:Person"` | `Rdf.type_uri` + prefixes |
| Fields | `Field("schema:name")` | `rdf_field` / `Predicate` + CURIE expand |
| Id | `id: IRI` | Explicit IRI field or `id_field` + namespace |
| Prefixes | `__prefixes__` | `Rdf.prefixes` |
| Write | `session.put(model)` | RDFModel sync + SparqlModel cascade |
| Read | `session.get`, `query` | RDFModel load + SparqlModel compiler/hydration |
| File export | `export_model(...)` | `model.to_graph().serialize(...)` |

Breaking SparqlModel field/session APIs is avoidable; breaking **duplicate** internal graph code is the goal.

---

## RDFModel releases to wait for (dependency gate)

Declare `dependencies = ["rdfmodel>=X"]` only when these exist in RDFModel (versions indicative — check RDFModel ROADMAP):

| RDFModel milestone | SparqlModel unblocks |
|--------------------|----------------------|
| **0.2** | Remove/replace triples on sync; namespaces/`bind`; nested embedded models; multi-value |
| **0.3** | Blank nodes / RDF lists (if still embedding as BNodes) |
| **0.4** | `parse` / `serialize`, base URI — replace most of `serializers.py` |
| **0.5** | `Dataset` / named graphs — if models gain `@graph` |

**Stay in SparqlModel regardless:** `compiler.py`, `query.py`, cascade rules, `HttpStore`, FastAPI, identity map.

Track RDFModel: [ROADMAP.md](https://github.com/eddiethedean/rdfmodel/blob/main/ROADMAP.md)

---

## Suggested integration steps

1. **Pin RDFModel in dev** — `pip install -e ../rdfmodel` locally; no runtime dep yet.
2. **Adapter module** — e.g. `sparqlmodel/_rdf.py`: map `SPARQLModel` → `RdfModel` config for one model as proof of concept.
3. **Replace `model_to_graph` / load path** — single code path through RDFModel; keep `put`/`delete` orchestration in `session.py`.
4. **Tests** — keep SparqlModel integration tests; add contract tests that RDFModel round-trip matches legacy graph output.
5. **Release** — `sparqlmodel` depends on `rdfmodel>=0.3,<0.4` (example); document in README and CHANGELOG.
6. **Delete dead code** — remove duplicated term conversion from `graph.py` once coverage is green.

---

## Dependencies policy

| Package | When |
|---------|------|
| `pydantic`, `rdflib`, `typing-extensions` | Always (today) |
| `rdfmodel` | After integration gate (above) |
| `httpx` | SparqlModel extra / 0.2 store (`sparqlmodel[http]` or dev) |
| `fastapi` | SparqlModel extra only |
| `pyshacl` | Do **not** bundle; use `rdfmodel[shacl]` if validation hooks are added |

**Do not** add SQLAlchemy/BerkeleyDB to SparqlModel core — those are RDFModel store extras if a `Store` implementation needs them.

---

## Testing strategy

| Test type | Where |
|-----------|--------|
| Literal, subject URI, parse round-trip | RDFModel (upstream); SparqlModel smoke imports |
| `put` / orphan / cascade | SparqlModel `test_graph_cascade.py`, `test_ownership.py` |
| Compiler / `!=` / nested filters | SparqlModel `test_compiler*.py` |
| Session CRUD | SparqlModel `test_session_*.py` |
| Cross-package contract | Optional CI job: install released `rdfmodel` + SparqlModel main |

When RDFModel fixes a term bug, **drop** the duplicate SparqlModel test if it only asserted the same mapping.

---

## Documentation split

| Document | Audience | Location |
|----------|----------|----------|
| SparqlModel README | App developers using session/query | SparqlModel repo |
| SparqlModel SPECS / ROADMAP / PLAN | SparqlModel features and releases | SparqlModel `docs/` |
| RDFModel README | Mapping and files | RDFModel repo |
| RDFModel ECOSYSTEM | Both maintainers | RDFModel `docs/ECOSYSTEM.md` |
| **This file** | SparqlModel maintainers | SparqlModel `docs/ECOSYSTEM.md` |

---

## Anti-patterns (SparqlModel PRs)

- Copy-pasting `python_to_term` logic from RDFModel into `graph.py`
- Adding Turtle/JSON-LD parsers only in SparqlModel
- Pushing session or query-compiler code into RDFModel
- Taking a dependency on RDFModel before sync/remove and nested models exist (you will fight the adapter)
- Circular re-exports that make `rdfmodel` import `sparqlmodel`

---

## Summary for maintainers

| | RDFModel | SparqlModel |
|---|----------|-------------|
| **Metaphor** | Schema + serialization library | Database session + query language |
| **State** | Stateless | Stateful session |
| **Killer feature** | Correct triples from Pydantic | `where(Model.field == x)` |
| **Grow here** | Terms, files, Dataset | Compiler, stores, cascade, FastAPI |

SparqlModel should get **thinner** as RDFModel matures, not wider. New rdflib mapping features go upstream; SparqlModel focuses on what RDFModel will never do: **application persistence and SPARQL ergonomics**.
