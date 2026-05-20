"""FastAPI helpers (optional ``sparqlmodel[fastapi]`` extra)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from triplemodel import Store

from sparqlmodel.fastapi.deps import (
    AsyncSessionDep,
    SessionDep,
    async_http_store_lifespan,
    async_session_dependency,
    get_async_session,
    get_session,
    http_store_lifespan,
    init_app,
    init_async_app,
    session_dependency,
)
from sparqlmodel.model import SPARQLModel
from sparqlmodel.rdf_bridge import model_to_graph
from sparqlmodel.serializers import export_graph

__all__ = [
    "AsyncSessionDep",
    "SessionDep",
    "async_http_store_lifespan",
    "async_session_dependency",
    "get_async_session",
    "get_session",
    "http_store_lifespan",
    "init_app",
    "init_async_app",
    "jsonld_response",
    "negotiated_response",
    "session_dependency",
    "turtle_response",
]

if TYPE_CHECKING:
    from fastapi import Request
    from starlette.responses import Response


def _require_fastapi() -> tuple[Any, Any]:
    try:
        from fastapi import Request as FastAPIRequest
        from starlette.responses import Response as FastAPIResponse
    except ImportError as exc:
        raise ImportError(
            "FastAPI support requires the optional extra: pip install 'sparqlmodel[fastapi]'"
        ) from exc
    return FastAPIRequest, FastAPIResponse


def _graph_from_model(model: SPARQLModel | Store) -> Store:
    if isinstance(model, Store):
        return model
    return model_to_graph(model)


def _body_bytes(body: str | bytes) -> bytes:
    return body if isinstance(body, bytes) else body.encode("utf-8")


def _negotiate_format_kind(accept: str, mapping: dict[str, str]) -> str:
    """Pick the highest-q format kind from an Accept header (defaults to Turtle)."""
    if not accept.strip() or accept.strip() == "*/*":
        return "turtle"

    best_q = -1.0
    best_kind = "turtle"
    for part in accept.split(","):
        piece = part.strip()
        if not piece:
            continue
        if ";q=" in piece:
            media, _, q_part = piece.partition(";q=")
            media = media.strip()
            try:
                q = float(q_part.strip())
            except ValueError:
                q = 0.0
        else:
            media = piece
            q = 1.0
        if media == "*/*":
            if q > best_q:
                best_q = q
                best_kind = "turtle"
            continue
        for media_type, kind in mapping.items():
            if media == media_type and q > best_q:
                best_q = q
                best_kind = kind
    return best_kind


def turtle_response(
    model: SPARQLModel | Store,
    *,
    status_code: int = 200,
) -> Response:
    """Return a Turtle HTTP response for a model or graph."""
    _, ResponseCls = _require_fastapi()
    graph = _graph_from_model(model)
    content = _body_bytes(export_graph(graph, format="turtle"))
    return ResponseCls(content=content, media_type="text/turtle", status_code=status_code)


def jsonld_response(
    model: SPARQLModel | Store,
    *,
    status_code: int = 200,
) -> Response:
    """Return a JSON-LD HTTP response for a model or graph."""
    _, ResponseCls = _require_fastapi()
    graph = _graph_from_model(model)
    content = _body_bytes(export_graph(graph, format="json-ld"))
    return ResponseCls(
        content=content,
        media_type="application/ld+json",
        status_code=status_code,
    )


def negotiated_response(
    request: Request,
    model: SPARQLModel | Store,
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
    if _negotiate_format_kind(accept, mapping) == "jsonld":
        return jsonld_response(model)
    return turtle_response(model)
