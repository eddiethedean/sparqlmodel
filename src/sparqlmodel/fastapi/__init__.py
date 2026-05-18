"""FastAPI helpers (optional ``sparqlmodel[fastapi]`` extra)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rdflib import Graph

from sparqlmodel.fastapi.deps import (
    SessionDep,
    get_session,
    http_store_lifespan,
    init_app,
    session_dependency,
)
from sparqlmodel.graph import model_to_graph
from sparqlmodel.model import SPARQLModel

__all__ = [
    "SessionDep",
    "get_session",
    "http_store_lifespan",
    "init_app",
    "jsonld_response",
    "negotiated_response",
    "session_dependency",
    "turtle_response",
]

if TYPE_CHECKING:
    from fastapi import Request
    from fastapi.responses import Response


def _require_fastapi() -> tuple[Any, Any]:
    try:
        from fastapi import Request as FastAPIRequest
        from fastapi.responses import Response as FastAPIResponse
    except ImportError as exc:
        raise ImportError(
            "FastAPI support requires the optional extra: pip install 'sparqlmodel[fastapi]'"
        ) from exc
    return FastAPIRequest, FastAPIResponse


def _graph_from_model(model: SPARQLModel | Graph) -> Graph:
    if isinstance(model, Graph):
        return model
    return model_to_graph(model)


def _body_bytes(body: str | bytes) -> bytes:
    return body if isinstance(body, bytes) else body.encode("utf-8")


def turtle_response(
    model: SPARQLModel | Graph,
    *,
    status_code: int = 200,
) -> Response:
    """Return a Turtle ``Response`` for a model or graph."""
    _, ResponseCls = _require_fastapi()
    graph = _graph_from_model(model)
    content = _body_bytes(graph.serialize(format="turtle"))
    return ResponseCls(content=content, media_type="text/turtle", status_code=status_code)


def jsonld_response(
    model: SPARQLModel | Graph,
    *,
    status_code: int = 200,
) -> Response:
    """Return a JSON-LD ``Response`` for a model or graph."""
    _, ResponseCls = _require_fastapi()
    graph = _graph_from_model(model)
    content = _body_bytes(graph.serialize(format="json-ld"))
    return ResponseCls(
        content=content,
        media_type="application/ld+json",
        status_code=status_code,
    )


def negotiated_response(
    request: Request,
    model: SPARQLModel | Graph,
    *,
    formats: dict[str, str] | None = None,
) -> Response:
    """Return Turtle or JSON-LD based on ``Accept`` (defaults to Turtle)."""
    _require_fastapi()
    accept = request.headers.get("accept", "text/turtle")
    mapping = formats or {
        "text/turtle": "turtle",
        "application/ld+json": "jsonld",
    }
    for media_type, kind in mapping.items():
        if media_type in accept:
            if kind == "jsonld":
                return jsonld_response(model)
            return turtle_response(model)
    return turtle_response(model)
