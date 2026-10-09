from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_contract(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["x-request-id"]
        schema = client.get("/openapi.json").json()
        assert schema["components"]["schemas"]["HealthResponse"]["properties"]["status"]["const"] == "ok"


def test_application_isolation(settings: Settings) -> None:
    app = create_app(settings)
    assert app is not create_app(settings)
    assert app.debug is False
    assert app.state.environment == "test"
    assert "/health" in app.openapi()["paths"]


def test_safe_errors(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/failure")
    def failure() -> None:
        raise RuntimeError("private-password")

    with TestClient(app, raise_server_exceptions=False) as client:
        for path, status, code in [("/missing", 404, "RESOURCE_NOT_FOUND"), ("/failure", 500, "INTERNAL_ERROR")]:
            response = client.get(path)
            assert response.status_code == status
            assert response.json()["code"] == code
            assert response.json()["request_id"] == response.headers["x-request-id"]
            assert response.json()["field_errors"] == []
            assert "private-password" not in response.text


def test_cors_is_explicit(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/health", headers={"Origin": "https://untrusted.example"}).headers.get("access-control-allow-origin") is None
        assert client.get("/health", headers={"Origin": "http://localhost:3000"}).headers["access-control-allow-origin"] == "http://localhost:3000"
