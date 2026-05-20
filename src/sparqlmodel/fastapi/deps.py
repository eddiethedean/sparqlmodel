"""FastAPI session dependency (SQLModel / SQLAlchemy style)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from sparqlmodel.async_session import AsyncSPARQLSession
from sparqlmodel.session import SPARQLSession
from sparqlmodel.stores.async_base import AsyncStoreProtocol
from sparqlmodel.stores.async_memory import AsyncMemoryStore
from sparqlmodel.stores.base import Store
from sparqlmodel.stores.memory import MemoryStore

Depends: Any = None
FastAPI: Any
Request: Any

try:
    from fastapi import Depends as _Depends
    from fastapi import FastAPI as _FastAPI
    from fastapi import Request as _Request

    Depends = _Depends
    FastAPI = _FastAPI
    Request = _Request
except ImportError:  # pragma: no cover - optional extra
    pass


def _require_fastapi_depends() -> None:
    if Depends is None:
        raise ImportError(
            "FastAPI session dependencies require: pip install 'sparqlmodel[fastapi]'"
        )


def init_app(
    app: FastAPI,
    store: Store,
    *,
    prefixes: dict[str, str] | None = None,
    autoflush: bool = True,
    rollback_on_error: bool = True,
) -> None:
    """Attach a shared store and session options to ``app.state`` (like a SQLAlchemy engine)."""
    _require_fastapi_depends()
    app.state.sparql_store = store
    app.state.sparql_session_options = {
        "prefixes": prefixes,
        "autoflush": autoflush,
        "rollback_on_error": rollback_on_error,
        "close_on_exit": False,
    }


def _session_options(app: FastAPI) -> dict[str, Any]:
    options = getattr(app.state, "sparql_session_options", None)
    if isinstance(options, dict):
        return dict(options)
    return {}


def _resolve_store(app: FastAPI) -> tuple[Store, bool]:
    """Return ``(store, close_store_on_session_exit)``."""
    shared = getattr(app.state, "sparql_store", None)
    if shared is not None:
        return shared, False
    factory = getattr(app.state, "sparql_store_factory", None)
    if callable(factory):
        return factory(), True
    return MemoryStore(), True


def get_session(request: Request) -> Generator[SPARQLSession, None, None]:
    """Yield one :class:`~sparqlmodel.session.SPARQLSession` per request (use with ``Depends``).

    Mirrors SQLModel / SQLAlchemy::

        def get_session():
            with Session(engine) as session:
                yield session

    The shared store comes from :func:`init_app` or :func:`http_store_lifespan`.
    When neither is configured, each request gets an isolated in-memory store.
    """
    _require_fastapi_depends()
    store, should_close_store = _resolve_store(request.app)
    options = _session_options(request.app)
    options.setdefault("close_on_exit", should_close_store)
    with SPARQLSession(store=store, **options) as session:
        yield session


if Depends is not None:
    SessionDep = Annotated[SPARQLSession, Depends(get_session)]
else:  # pragma: no cover
    SessionDep = SPARQLSession  # type: ignore[assignment,misc]


@asynccontextmanager
async def http_store_lifespan(
    app: FastAPI,
    endpoint: str,
    *,
    auth: tuple[str, str] | None = None,
    headers: dict[str, str] | None = None,
    prefixes: dict[str, str] | None = None,
    **http_kwargs: Any,
) -> AsyncIterator[None]:
    """HttpStore lifespan: :func:`init_app` on startup, close the store on shutdown."""
    _require_fastapi_depends()
    from sparqlmodel.stores.http import HttpStore

    with HttpStore(
        endpoint,
        auth=auth,
        headers=headers,
        prefixes=prefixes,
        **http_kwargs,
    ) as store:
        init_app(app, store, prefixes=prefixes)
        yield


def session_dependency(
    store: Store | None = None,
    *,
    store_factory: Callable[[], Store] | None = None,
    prefixes: dict[str, str] | None = None,
    autoflush: bool = True,
    rollback_on_error: bool = True,
    close_on_exit: bool | None = None,
) -> Callable[[Request], Generator[SPARQLSession, None, None]]:
    """Build a custom ``get_session`` for ``app.dependency_overrides`` or multi-store apps."""
    _require_fastapi_depends()

    def _get(request: Request) -> Generator[SPARQLSession, None, None]:
        if store is not None:
            resolved = store
            close = False if close_on_exit is None else close_on_exit
        elif store_factory is not None:
            resolved = store_factory()
            close = True if close_on_exit is None else close_on_exit
        else:
            resolved, close = _resolve_store(request.app)
            if close_on_exit is not None:
                close = close_on_exit
        kwargs: dict[str, Any] = {
            "prefixes": prefixes,
            "autoflush": autoflush,
            "rollback_on_error": rollback_on_error,
            "close_on_exit": close,
        }
        with SPARQLSession(store=resolved, **kwargs) as session:
            yield session

    return _get


def init_async_app(
    app: FastAPI,
    store: AsyncStoreProtocol,
    *,
    prefixes: dict[str, str] | None = None,
    autoflush: bool = True,
    rollback_on_error: bool = True,
) -> None:
    """Attach a shared async store and session options to ``app.state``."""
    _require_fastapi_depends()
    app.state.sparql_async_store = store
    app.state.sparql_async_session_options = {
        "prefixes": prefixes,
        "autoflush": autoflush,
        "rollback_on_error": rollback_on_error,
        "close_on_exit": False,
    }


def _async_session_options(app: FastAPI) -> dict[str, Any]:
    options = getattr(app.state, "sparql_async_session_options", None)
    if isinstance(options, dict):
        return dict(options)
    return {}


def _resolve_async_store(app: FastAPI) -> tuple[AsyncStoreProtocol, bool]:
    shared = getattr(app.state, "sparql_async_store", None)
    if shared is not None:
        return shared, False
    factory = getattr(app.state, "sparql_async_store_factory", None)
    if callable(factory):
        return factory(), True
    return AsyncMemoryStore(), True


async def get_async_session(request: Request) -> AsyncIterator[AsyncSPARQLSession]:
    """Yield one :class:`~sparqlmodel.async_session.AsyncSPARQLSession` per request."""
    _require_fastapi_depends()
    store, should_close_store = _resolve_async_store(request.app)
    options = _async_session_options(request.app)
    options.setdefault("close_on_exit", should_close_store)
    async with AsyncSPARQLSession(store=store, **options) as session:
        yield session


if Depends is not None:
    AsyncSessionDep = Annotated[AsyncSPARQLSession, Depends(get_async_session)]
else:  # pragma: no cover
    AsyncSessionDep = AsyncSPARQLSession  # type: ignore[assignment,misc]


@asynccontextmanager
async def async_http_store_lifespan(
    app: FastAPI,
    endpoint: str,
    *,
    auth: tuple[str, str] | None = None,
    headers: dict[str, str] | None = None,
    prefixes: dict[str, str] | None = None,
    **http_kwargs: Any,
) -> AsyncIterator[None]:
    """AsyncHttpStore lifespan: :func:`init_async_app` on startup, ``aclose`` on shutdown."""
    _require_fastapi_depends()
    from sparqlmodel.stores.async_http import AsyncHttpStore

    async with AsyncHttpStore(
        endpoint,
        auth=auth,
        headers=headers,
        prefixes=prefixes,
        **http_kwargs,
    ) as store:
        init_async_app(app, store, prefixes=prefixes)
        yield


def async_session_dependency(
    store: AsyncStoreProtocol | None = None,
    *,
    store_factory: Callable[[], AsyncStoreProtocol] | None = None,
    prefixes: dict[str, str] | None = None,
    autoflush: bool = True,
    rollback_on_error: bool = True,
    close_on_exit: bool | None = None,
) -> Callable[[Request], AsyncIterator[AsyncSPARQLSession]]:
    """Build a custom async ``get_session`` for dependency overrides."""
    _require_fastapi_depends()

    async def _get(request: Request) -> AsyncIterator[AsyncSPARQLSession]:
        if store is not None:
            resolved = store
            close = False if close_on_exit is None else close_on_exit
        elif store_factory is not None:
            resolved = store_factory()
            close = True if close_on_exit is None else close_on_exit
        else:
            resolved, close = _resolve_async_store(request.app)
            if close_on_exit is not None:
                close = close_on_exit
        kwargs: dict[str, Any] = {
            "prefixes": prefixes,
            "autoflush": autoflush,
            "rollback_on_error": rollback_on_error,
            "close_on_exit": close,
        }
        async with AsyncSPARQLSession(store=resolved, **kwargs) as session:
            yield session

    return _get
