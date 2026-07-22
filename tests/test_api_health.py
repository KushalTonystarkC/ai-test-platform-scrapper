"""Health endpoint smoke test (no DB required for /health)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "32")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://kushal:0000@localhost:5433/question_bank")
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
