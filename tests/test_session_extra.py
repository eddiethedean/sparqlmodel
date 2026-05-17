"""Additional session tests."""

import pytest

from sparqlmodel.exceptions import ConfigurationError
from tests.models import Person


def test_get_invalid_depth(session, odos: Person) -> None:
    session.put(odos)
    with pytest.raises(ConfigurationError):
        session.get(Person, odos.id, depth=5)
