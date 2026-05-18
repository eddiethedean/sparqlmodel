"""SparqlModel exception types."""


class SparqlModelError(Exception):
    """Base exception for SparqlModel."""


class ConfigurationError(SparqlModelError):
    """Raised when a model or session is misconfigured."""


class QueryError(SparqlModelError):
    """Raised when a query cannot be compiled or executed."""


class HydrationError(SparqlModelError):
    """Raised when query results cannot be hydrated into models."""


class StaleTripleWarning(UserWarning):
    """Warn when ``add()`` may leave stale triples on an existing subject."""
