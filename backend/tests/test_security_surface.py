"""Docs gating + CORS origin configuration (security audit Group E).

No database or lifespan: every app here is built with a pre-built state and
never entered as a context manager, so these tests run without infrastructure.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import config
from app.main import create_app


def _client(monkeypatch, *, api_key="", docs="auto", origins=None) -> TestClient:
    monkeypatch.setattr(config, "KYRO_API_KEY", api_key)
    monkeypatch.setattr(config, "KYRO_DOCS", docs)
    if origins is not None:
        monkeypatch.setattr(config, "CORS_ORIGINS", origins)
    return TestClient(create_app())


# ------------------------------------------------------------------- docs
def test_docs_enabled_in_dev(monkeypatch):
    client = _client(monkeypatch, api_key="")
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "paths" in schema.json()


def test_docs_disabled_when_api_key_set(monkeypatch):
    client = _client(monkeypatch, api_key="prod-secret")
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_env_override_on_in_production(monkeypatch):
    client = _client(monkeypatch, api_key="prod-secret", docs="on")
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_env_override_off_in_dev(monkeypatch):
    client = _client(monkeypatch, api_key="", docs="off")
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# -------------------------------------------------------------------- CORS
def test_cors_default_local_origin_allowed(monkeypatch):
    client = _client(monkeypatch)
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_foreign_origin_blocked(monkeypatch):
    client = _client(monkeypatch)
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") is None


def test_cors_origins_env_driven(monkeypatch):
    client = _client(monkeypatch, origins=["https://app.example.com"])
    allowed = client.get("/health", headers={"Origin": "https://app.example.com"})
    assert (
        allowed.headers.get("access-control-allow-origin") == "https://app.example.com"
    )
    # the previous default is no longer allowed once overridden
    blocked = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert blocked.headers.get("access-control-allow-origin") is None
