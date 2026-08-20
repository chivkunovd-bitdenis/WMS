from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_ok() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version_reports_release_environment(monkeypatch) -> None:
    monkeypatch.setenv("WMS_GIT_SHA", "a" * 40)
    monkeypatch.setenv("WMS_ARTIFACT_DIGEST", "sha256:artifact")
    app = create_app()
    client = TestClient(app)

    resp = client.get("/version")
    assert resp.status_code == 200
    assert resp.json() == {
        "git_sha": "a" * 40,
        "artifact_digest": "sha256:artifact",
    }
