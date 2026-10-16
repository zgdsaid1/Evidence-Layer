from __future__ import annotations

import builtins
import importlib
import io
import os
import socket

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

import uvicorn
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import evidence_service.__main__ as service_entrypoint
import evidence_service.app as service_app
import evidence_service.healthcheck as healthcheck


def test_health_route_has_exact_response_contract() -> None:
    with TestClient(service_app.create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.content == b'{"status":"ok"}'


def test_service_routes_are_limited_and_docs_are_disabled() -> None:
    routes = {
        (method, route.path)
        for route in service_app.app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }
    assert routes == {
        ("GET", "/healthz"),
        ("GET", "/v1/me"),
        ("GET", "/v1/workspaces/{workspace_id}"),
    }

    with TestClient(service_app.app) as client:
        for path in ("/", "/docs", "/redoc", "/openapi.json", "/retrieve_evidence"):
            assert client.get(path).status_code == 404
        assert client.get("/v1/me").status_code == 401
        assert client.post("/healthz").status_code in {404, 405}
        assert client.head("/healthz").status_code in {404, 405}


def test_startup_needs_no_credentials_and_does_not_load_integrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_JWT_ISSUER",
        "SUPABASE_JWT_AUDIENCE",
        "SUPABASE_JWT_ALGORITHMS",
        "SUPABASE_JWKS_CACHE_TTL_SECONDS",
        "SUPABASE_SERVICE_ROLE_KEY",
        "JEV_API_KEY",
        "TYPESAFE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PORT", "9123")

    blocked_roots = {"evidence_layer", "supabase", "typesafe_sdk", "openai"}
    original_import = builtins.__import__
    attempted_imports: list[str] = []

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name.split(".", 1)[0] in blocked_roots:
            attempted_imports.append(name)
            raise AssertionError("health service attempted an integration import")
        return original_import(name, *args, **kwargs)

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("health service attempted a network connection")

    def guard_corpus_open(file: object, *args: object, **kwargs: object) -> object:
        try:
            path = os.fsdecode(os.fspath(file))
        except TypeError:
            path = ""
        if "data/corpus/" in path.replace("\\", "/"):
            raise AssertionError("health service attempted to open corpus content")
        return original_open(file, *args, **kwargs)

    original_open = builtins.open
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(builtins, "open", guard_corpus_open)
    monkeypatch.setattr(io, "open", guard_corpus_open)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)

    reloaded_app = importlib.reload(service_app)
    with TestClient(reloaded_app.app) as client:
        assert client.get("/healthz").status_code == 200

    assert attempted_imports == []


def test_entrypoint_uses_configured_port_and_public_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    service_entrypoint.main()

    assert calls == [
        (
            ("evidence_service.app:app",),
            {"host": "0.0.0.0", "port": 9123, "access_log": False},
        )
    ]


def test_entrypoint_defaults_and_rejects_invalid_port() -> None:
    assert service_entrypoint.configured_port({}) == 8000
    assert service_entrypoint.configured_port({"PORT": "9001"}) == 9001
    with pytest.raises(SystemExit, match="PORT must be an integer"):
        service_entrypoint.configured_port({"PORT": "70000"})
    with pytest.raises(SystemExit, match="PORT must be an integer"):
        service_entrypoint.configured_port({"PORT": "not-a-port"})


def test_healthcheck_uses_local_endpoint_and_exact_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, float]] = []

    class Response:
        status = 200

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    class Connection:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            calls.append((host, port, timeout))

        def request(self, method: str, path: str) -> None:
            assert (method, path) == ("GET", "/healthz")

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            return None

    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setattr(healthcheck.http.client, "HTTPConnection", Connection)

    assert healthcheck.is_healthy()
    assert calls == [("127.0.0.1", 9123, 2)]
