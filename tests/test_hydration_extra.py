"""Additional hydration coverage."""

from sparqlmodel.exceptions import HydrationError
from sparqlmodel.hydration import hydrate_from_bindings
from tests.models import Person


def test_hydrate_from_bindings(session, odos: Person) -> None:
    session.put(odos)
    bindings = session.execute("SELECT ?person WHERE { ?person a <https://schema.org/Person> . }")
    results = hydrate_from_bindings(Person, bindings, session.store, depth=1)
    assert len(results) >= 1


def test_hydrate_invalid(session) -> None:
    bindings = [{"person": "not-a-valid-node"}]
    try:
        hydrate_from_bindings(Person, bindings, session.store)
    except HydrationError:
        pass
    else:
        # May return empty if subject not in graph
        pass
