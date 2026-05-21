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
from sparqlmodel.serializers import _resolve_rdf_format, export_graph

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

_DEFAULT_TURTLE = "text/turtle"
_DEFAULT_JSONLD = "application/ld+json"


def _require_fastapi() -> tuple[Any, Any]:
    try:
        from fastapi import Request as FastAPIRequest
        from starlette.responses import Response as FastAPIResponse
    except ImportError as exc:
        raise ImportError(
            "FastAPI support requires the optional extra: pip install 'sparqlmodel[fastapi]'"
        ) from exc
    return FastAPIRequest, FastAPIResponse


def _body_bytes(body: str | bytes) -> bytes:
    return body if isinstance(body, bytes) else body.encode("utf-8")


def _serialize_rdf_body(model: SPARQLModel | Store, fmt: str) -> bytes:
    if isinstance(model, SPARQLModel):
        result = model.serialize(format=fmt)
        if result is None:
            return b""
        return _body_bytes(result)
    return _body_bytes(export_graph(model, format=fmt))


def _negotiate_rdf_format(accept: str, media_types: tuple[str, ...]) -> str:
    """Pick the highest-q media type from ``Accept`` and resolve via ``infer_format``."""
    if not accept.strip() or accept.strip() == "*/*":
        return _resolve_rdf_format(_DEFAULT_TURTLE)

    best_q = -1.0
    best_media = _DEFAULT_TURTLE
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
                best_media = _DEFAULT_TURTLE
            continue
        for candidate in media_types:
            if media == candidate and q > best_q:
                best_q = q
                best_media = candidate
    return _resolve_rdf_format(best_media)


def turtle_response(
    model: SPARQLModel | Store,
    *,
    status_code: int = 200,
) -> Response:
    """Return a Turtle HTTP response for a model or graph."""
    _, ResponseCls = _require_fastapi()
    fmt = _resolve_rdf_format(_DEFAULT_TURTLE)
    content = _serialize_rdf_body(model, fmt)
    return ResponseCls(content=content, media_type=_DEFAULT_TURTLE, status_code=status_code)


def jsonld_response(
    model: SPARQLModel | Store,
    *,
    status_code: int = 200,
) -> Response:
    """Return a JSON-LD HTTP response for a model or graph."""
    _, ResponseCls = _require_fastapi()
    fmt = _resolve_rdf_format(_DEFAULT_JSONLD)
    content = _serialize_rdf_body(model, fmt)
    return ResponseCls(
        content=content,
        media_type=_DEFAULT_JSONLD,
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
    accept = request.headers.get("accept", _DEFAULT_TURTLE)
    if formats is not None:
        media_types = tuple(formats.keys())
    else:
        media_types = (_DEFAULT_TURTLE, _DEFAULT_JSONLD)
    resolved = _negotiate_rdf_format(accept, media_types)
    if resolved.replace("_", "-") == "json-ld":
        return jsonld_response(model)
    return turtle_response(model)
